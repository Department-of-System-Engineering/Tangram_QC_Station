"""Corner-click calibration of seven physical pieces; independent of base color."""
import json
from pathlib import Path
import cv2
import numpy as np

from .variants import PART_NAMES, VARIANTS, create_variant_profile


LABELS = ("LEFT ear (in upright diagram)", "RIGHT ear (in upright diagram)",
          "HEAD square", "NECK parallelogram", "MIDDLE red triangle",
          "BODY large triangle", "FOOT bottom large triangle")
VERTICES = (3, 3, 4, 4, 3, 3, 3)


def calibrate_variants(source, output, variant, image=None):
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
            print("Place a complete good product; SPACE: freeze; Q: cancel.")
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                # Match runtime defaults even if the driver ignores requested resolution.
                scale = min(1, 640/frame.shape[1], 480/frame.shape[0])
                if scale < 1:
                    frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                cv2.imshow("Variant calibration", frame)
                key = cv2.waitKey(1) & 255
                if key == ord("q"):
                    return
                if key == 32:
                    break
        if image:
            scale = min(1, 640/frame.shape[1], 480/frame.shape[0])
            if scale < 1:
                frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        print("Select work area enclosing ALL pieces with background margin. ENTER confirms.")
        roi = list(map(int, cv2.selectROI("Variant calibration", frame, False)))
        x, y, w, h = roi
        if not w or not h:
            return
        points, polygons = [], []

        def click(event, px, py, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(polygons) < 7 and x < px < x+w-1 and y < py < y+h-1:
                if len(points) < VERTICES[len(polygons)]:
                    points.append([px, py])

        cv2.setMouseCallback("Variant calibration", click)
        print("Click each piece's corners in perimeter order, then ENTER. U: undo; Q: cancel.")
        print("Use actual colored piece corners, not the base border. Left/right refer to the upright drawing.")
        print("After seven pieces: S saves only if automatic detection passes; U redoes the last piece.")
        previous = -1
        error_message = ""
        while True:
            index = len(polygons)
            if index != previous:
                if index < 7:
                    print(f"{index+1}/7: {LABELS[index]} | {VARIANTS[variant][index]} | {VERTICES[index]} corners")
                previous = index
            preview = frame.copy()
            cv2.rectangle(preview, (x, y), (x+w-1, y+h-1), (200, 200, 200), 1)
            for i, polygon in enumerate(polygons):
                cv2.polylines(preview, [polygon], True, (0, 255, 0), 2)
                px, py = polygon[0, 0]
                cv2.putText(preview, PART_NAMES[i], (int(px), int(py)), 0, .4, (255, 255, 255), 1)
            if points:
                cv2.polylines(preview, [np.array(points, np.int32)], False, (0, 255, 255), 2)
            title = f"{index+1}/7 {LABELS[index]} ({VARIANTS[variant][index]})" if index < 7 else "7/7 | S: validate/save | U: undo"
            cv2.putText(preview, title, (10, 24), 0, .5, (255, 255, 255), 2)
            if error_message:
                cv2.putText(preview, "Save rejected: see terminal. U: redo or Q: cancel", (10, frame.shape[0]-12), 0, .45, (0, 0, 255), 1)
            cv2.imshow("Variant calibration", preview)
            key = cv2.waitKey(30) & 255
            if key == ord("q"):
                return
            if key in (ord("u"), 8):
                error_message = ""
                if points:
                    points.pop()
                elif polygons:
                    points.extend(polygons.pop().reshape(-1, 2).tolist())
            if key in (10, 13) and index < 7:
                if len(points) != VERTICES[index]:
                    print(f"Need {VERTICES[index]} corners")
                    continue
                polygon = np.asarray(points, np.int32).reshape(-1, 1, 2)
                if not cv2.isContourConvex(polygon) or cv2.contourArea(polygon) < 40:
                    print("Invalid polygon; U to undo corners. Click corners in perimeter order.")
                    continue
                selected = np.zeros(frame.shape[:2], np.uint8)
                cv2.drawContours(selected, [polygon], -1, 255, -1)
                occupied = np.zeros_like(selected)
                cv2.drawContours(occupied, polygons, -1, 255, -1)
                if np.count_nonzero((selected > 0) & (occupied > 0)) > 10:
                    print("Pieces overlap; outline each physical piece once.")
                    continue
                polygons.append(polygon)
                points.clear()
            if key == ord("s") and len(polygons) == 7:
                try:
                    profile = create_variant_profile(frame, polygons, variant, roi, Path(output).stem)
                except ValueError as error:
                    error_message = str(error)
                    print(error)
                    print("Check corners/work area/variant. Touching same-color pieces must have a visible separating edge.")
                    continue
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(profile, indent=2), encoding="utf-8")
                temporary.replace(target)
                print(f"Saved all four variant recipes: {target}")
                return
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
