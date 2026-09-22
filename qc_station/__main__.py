import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import cv2

from .calibrate import calibrate
from .session import InspectionWindow
from .storage import ResultStore
from .vision import inspect, load_profile, profile_id
from .variant_calibration import calibrate_variants
from .order_context import load_order_context


def camera_source(value):
    return int(value) if value.isdecimal() else value


def run(args):
    if getattr(args, "order_context", None):
        if not args.once:
            raise ValueError("Use --once with --order-context; each product requires a fresh order input")
        context = load_order_context(args.order_context)
        if args.product_instance_id not in (None, context.product_instance_id) or getattr(args, "expected_variant", None) not in (None, context.expected_variant):
            raise ValueError("Command line conflicts with order context")
        args.product_instance_id = context.product_instance_id
        args.expected_variant = context.expected_variant
        args.order_id = context.order_id
    profile = load_profile(args.profile)
    expected_variant = getattr(args, "expected_variant", None)
    if expected_variant and profile.get("schema_version") != 2:
        raise ValueError("Expected variant requires a new part-based calibration")
    if not 1 <= args.fps <= 30 or not 160 <= args.width <= 1920 or not 120 <= args.height <= 1080:
        raise ValueError("FPS must be 1..30; resolution 160x120..1920x1080")
    if args.product_instance_id is not None and not args.once:
        raise ValueError("Use --once with --product-instance-id to avoid reusing an identity")
    window = InspectionWindow(args.seconds, args.min_samples)
    cv2.setNumThreads(2)
    cap = cv2.VideoCapture(camera_source(args.camera))
    writer = None
    store = None
    identifier = None
    video_path = None
    last_analysis = float("-inf")
    status = "WAITING"
    cycle_saved = False
    try:
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        store = ResultStore(Path(args.output) / "results.sqlite3")
        while True:
            ok, frame = cap.read()
            if not ok:
                if identifier and not window.finished:
                    if writer:
                        writer.release()
                        writer = None
                    store.save(make_event(args, profile, identifier, {
                        "status": "INCONCLUSIVE", "reason": "camera_read_failed",
                        "samples": window.samples}, video_path))
                    cycle_saved = True
                raise RuntimeError("Camera read failed; no PASS result produced")
            now = time.monotonic()
            if now - last_analysis < 1 / args.fps:
                continue
            last_analysis = now
            # Bound processing cost even when a camera ignores the requested size.
            scale = min(1, args.width / frame.shape[1], args.height / frame.shape[0])
            if scale < 1:
                frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            started = time.perf_counter()
            result, mask = inspect(frame, profile, expected_variant)
            new_cycle = window.started is None and result.get("object_present", result["base_present"]) and not window.finished
            if new_cycle:
                identifier = str(uuid.uuid4())
                cycle_saved = False
                video_path = None
                status = "INSPECTING"
                if not args.no_video:
                    folder = Path(args.output) / "videos"
                    folder.mkdir(parents=True, exist_ok=True)
                    if sum(1 for _ in folder.glob("*.avi")) >= args.max_videos:
                        raise RuntimeError("Video retention limit reached; archive old clips before continuing")
                    video_path = str(folder / f"{identifier}.avi")
                    writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"MJPG"), args.fps,
                                             (frame.shape[1], frame.shape[0]))
                    if not writer.isOpened():
                        raise RuntimeError("Cannot create safety video")
            if writer is not None:
                writer.write(frame)
            final = window.update(result, now)
            if final:
                if writer is not None:
                    writer.release()
                    writer = None
                status = final["status"]
                event = make_event(args, profile, identifier, final, video_path)
                store.save(event)
                cycle_saved = True
                print(json.dumps(event, allow_nan=False), flush=True)
                if args.once:
                    return
            if window.started is None:
                status = "WAITING"
            if not args.headless:
                cv2.putText(frame, f"{status} | parts {result['found_count']}/7 | {(time.perf_counter()-started)*1000:.0f}ms", (10, 25), 0, 0.6,
                            (0, 255, 0) if status == "PASS" else (0, 200, 255), 2)
                cv2.imshow("Tangram QC", frame)
                if args.debug:
                    cv2.imshow("Detection mask", mask)
                if profile.get("schema_version") == 2:
                    # A separate line exposes identity independently of PASS/FAIL.
                    cv2.putText(frame, f"Variant: {result['detected_variant'] or '?'} | expected: {expected_variant or 'auto'} | score: {result['quality_score']:.1f}",
                                (10, 48), 0, .5, (255, 255, 255), 1)
                    cv2.imshow("Tangram QC", frame)
                if cv2.waitKey(1) & 255 == ord("q"):
                    if identifier and not window.finished and window.started is not None:
                        store.save(make_event(args, profile, identifier, {
                            "status": "INCONCLUSIVE", "reason": "operator_cancelled",
                            "samples": window.samples}, video_path))
                        cycle_saved = True
                    return
    finally:
        if writer is not None:
            writer.release()
        cap.release()
        if store is not None:
            try:
                if identifier and not cycle_saved:
                    store.save(make_event(args, profile, identifier, {
                        "status": "INCONCLUSIVE", "reason": "inspection_interrupted",
                        "samples": window.samples}, video_path))
            finally:
                store.close()
        if not args.headless:
            cv2.destroyAllWindows()


def make_event(args, profile, identifier, result, video_path):
    return {"schema_version": 1, "inspection_id": identifier,
            "station_id": args.station_id, "product_instance_id": args.product_instance_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "calibration_id": profile_id(profile), "profile_name": profile["name"],
            "expected_variant": getattr(args, "expected_variant", None),
            "order_id": getattr(args, "order_id", None),
            "video_path": video_path, "result": result}


def main():
    parser = argparse.ArgumentParser(description="Tangram QC station")
    commands = parser.add_subparsers(dest="command", required=True)
    calibration = commands.add_parser("calibrate", help="Learn shapes/colors from a good product")
    calibration.add_argument("--camera", default="0")
    calibration.add_argument("--image")
    calibration.add_argument("--resume", help="Resume a saved calibration selection.json with its raw frame")
    calibration.add_argument("--output", default="profiles/tangram.json")
    calibration.add_argument("--variant", choices=list("ABCD"), help="Known variant of the good calibration sample")
    calibration.add_argument("--legacy-base", action="store_true", help="Use old base-color calibration")
    station = commands.add_parser("run")
    station.add_argument("--profile", default="profiles/tangram.json")
    station.add_argument("--camera", default="0")
    station.add_argument("--width", type=int, default=640)
    station.add_argument("--height", type=int, default=480)
    station.add_argument("--fps", type=float, default=10)
    station.add_argument("--seconds", type=float, default=3)
    station.add_argument("--min-samples", type=int, default=15)
    station.add_argument("--station-id", default="tangram-qc-01")
    station.add_argument("--product-instance-id", type=int)
    station.add_argument("--expected-variant", choices=list("ABCD"))
    station.add_argument("--order-context", help="JSON order input; requires --once")
    station.add_argument("--output", default="runtime")
    station.add_argument("--max-videos", type=int, default=500)
    for flag in ("headless", "debug", "once", "no-video"):
        station.add_argument("--" + flag, action="store_true")
    sender = commands.add_parser("flush", help="Send saved results to an implemented QC receiver")
    sender.add_argument("--endpoint", required=True)
    sender.add_argument("--database", default="runtime/results.sqlite3")
    args = parser.parse_args()
    try:
        if args.command == "calibrate":
            if args.legacy_base:
                calibrate(camera_source(args.camera), args.output, args.image)
            elif not args.variant and not args.resume:
                raise ValueError("Specify the good sample's variant: --variant A, B, C or D")
            else:
                if args.resume and args.image:
                    raise ValueError("Use either --resume or --image")
                calibrate_variants(camera_source(args.camera), args.output, args.variant, args.image, args.resume)
        elif args.command == "run":
            if args.max_videos < 1 or (args.product_instance_id is not None and args.product_instance_id < 1):
                raise ValueError("Video limit and product ID must be positive")
            run(args)
        else:
            store = ResultStore(args.database)
            try:
                print(f"Delivered: {store.flush(args.endpoint)}")
            finally:
                store.close()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
