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


def camera_source(value):
    return int(value) if value.isdecimal() else value


def run(args):
    profile = load_profile(args.profile)
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
            result, mask = inspect(frame, profile)
            new_cycle = window.started is None and result["base_present"] and not window.finished
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
                    cv2.imshow("Base mask", mask)
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
            "video_path": video_path, "result": result}


def main():
    parser = argparse.ArgumentParser(description="Tangram QC station")
    commands = parser.add_subparsers(dest="command", required=True)
    calibration = commands.add_parser("calibrate", help="Learn shapes/colors from a good product")
    calibration.add_argument("--camera", default="0")
    calibration.add_argument("--image")
    calibration.add_argument("--output", default="profiles/tangram.json")
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
            calibrate(camera_source(args.camera), args.output, args.image)
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
