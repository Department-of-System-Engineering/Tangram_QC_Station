"""Interactive calibration: freeze a good product, sample base color, preview/save."""
import json
from pathlib import Path
import cv2
import numpy as np

from .vision import create_profile, extract, learn_color, validate_profile


def calibrate(source, output, image=None):
    cap = None
    try:
        if image:
            frame = cv2.imread(image)
            if frame is None:
                raise ValueError(f"Cannot read image: {image}")
        else:
            cap = cv2.VideoCapture(source)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            print("Place a known-good product. SPACE: freeze; Q: cancel.")
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                cv2.imshow("Calibration", frame)
                key = cv2.waitKey(1) & 255
                if key == ord("q"):
                    return
                if key == 32:
                    break
        print("Select a small uniform rectangle on the PINK BASE (not a part). ENTER confirms.")
        x, y, w, h = map(int, cv2.selectROI("Calibration", frame, False))
        if not w or not h:
            return
        bounds = learn_color(cv2.cvtColor(frame[y: y + h, x: x + w], cv2.COLOR_BGR2HSV).reshape(-1, 3))
        cv2.namedWindow("HSV")
        names = ["H low", "S low", "V low", "H high", "S high", "V high"]
        for i, name in enumerate(names):
            cv2.createTrackbar(name, "HSV", bounds[i // 3][i % 3], 179 if i % 3 == 0 else 255, lambda _: None)
        cv2.createTrackbar("Gap closing", "HSV", 1, 7, lambda _: None)
        segmentation = {"close_kernel": 3, "frame_size": [frame.shape[1], frame.shape[0]], "bridges": []}
        pending = []

        def click(event, x, y, flags, param):
            if event != cv2.EVENT_LBUTTONDOWN:
                return
            if not (0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]):
                return
            pending.append([x, y])
            if len(pending) == 2:
                distance = np.linalg.norm(np.asarray(pending[0]) - pending[1])
                if 0 < distance <= 40 and len(segmentation["bridges"]) < 20:
                    segmentation["bridges"].append(pending.copy())
                else:
                    print("Bridge rejected: select gap endpoints <=40 pixels apart (max 20 bridges).")
                pending.clear()

        cv2.setMouseCallback("Calibration", click)
        print("Tune HSV and Gap closing (smallest value giving 7 separate parts).")
        print("For a broken pink boundary: click its two ends in Calibration (max 40px).")
        print("U: undo bridge; R: clear bridges; S: save; Q: cancel. Do not draw new part edges.")
        while True:
            values = [cv2.getTrackbarPos(name, "HSV") for name in names]
            bounds = [values[:3], values[3:]]
            segmentation["close_kernel"] = 2 * cv2.getTrackbarPos("Gap closing", "HSV") + 1
            base, parts, mask = extract(frame, bounds, segmentation=segmentation)
            preview = frame.copy()
            if base is not None:
                cv2.drawContours(preview, [base], -1, (255, 0, 0), 2)
            parts.sort(key=lambda c: (cv2.boundingRect(c)[1], cv2.boundingRect(c)[0]))
            for i, contour in enumerate(parts):
                cv2.drawContours(preview, [contour], -1, (0, 255, 0), 2)
                px, py, _, _ = cv2.boundingRect(contour)
                cv2.putText(preview, f"{i+1}", (px, py), 0, 0.6, (0, 255, 0), 2)
            for a, b in segmentation["bridges"]:
                cv2.line(preview, tuple(a), tuple(b), (255, 255, 0), 1)
            for point in pending:
                cv2.circle(preview, tuple(point), 4, (255, 255, 0), -1)
            cv2.putText(preview, f"Close: {segmentation['close_kernel']}px | bridges: {len(segmentation['bridges'])} | U: undo R: clear",
                        (10, frame.shape[0] - 12), 0, 0.5, (255, 255, 255), 1)
            cv2.putText(preview, f"Parts: {len(parts)}/7 | S: save | Q: cancel", (10, 25), 0, 0.6, (255, 255, 255), 2)
            cv2.imshow("Calibration", preview)
            cv2.imshow("HSV", mask)
            key = cv2.waitKey(30) & 255
            if key == ord("q"):
                return
            if key == ord("u"):
                if pending:
                    pending.clear()
                elif segmentation["bridges"]:
                    segmentation["bridges"].pop()
            if key == ord("r"):
                segmentation["bridges"].clear()
                pending.clear()
            if key == ord("s"):
                if pending:
                    print("Finish the bridge with a second click, or U to cancel it.")
                    continue
                try:
                    profile = create_profile(frame, bounds, Path(output).stem, segmentation=segmentation)
                    validate_profile(profile)
                except ValueError as error:
                    print(error)
                    continue
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(profile, indent=2), encoding="utf-8")
                temporary.replace(target)
                print(f"Saved shape, position and color calibration: {target}")
                return
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
