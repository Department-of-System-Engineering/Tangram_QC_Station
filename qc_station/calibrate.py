"""Interactive calibration: freeze a good product, sample base color, preview/save."""
import json
from pathlib import Path
import cv2

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
        print("Tune HSV until all 7 parts have separate green contours. S: save; Q: cancel.")
        while True:
            values = [cv2.getTrackbarPos(name, "HSV") for name in names]
            bounds = [values[:3], values[3:]]
            base, parts, mask = extract(frame, bounds)
            preview = frame.copy()
            if base is not None:
                cv2.drawContours(preview, [base], -1, (255, 0, 0), 2)
            parts.sort(key=lambda c: (cv2.boundingRect(c)[1], cv2.boundingRect(c)[0]))
            for i, contour in enumerate(parts):
                cv2.drawContours(preview, [contour], -1, (0, 255, 0), 2)
                px, py, _, _ = cv2.boundingRect(contour)
                cv2.putText(preview, f"{i+1}", (px, py), 0, 0.6, (0, 255, 0), 2)
            cv2.putText(preview, f"Parts: {len(parts)}/7 | S: save | Q: cancel", (10, 25), 0, 0.6, (255, 255, 255), 2)
            cv2.imshow("Calibration", preview)
            cv2.imshow("HSV", mask)
            key = cv2.waitKey(30) & 255
            if key == ord("q"):
                return
            if key == ord("s"):
                try:
                    profile = create_profile(frame, bounds, Path(output).stem)
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
