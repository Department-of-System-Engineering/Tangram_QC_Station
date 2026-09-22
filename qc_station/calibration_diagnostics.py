"""Capture unannotated input and selections without accepting a rejected profile."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
import cv2
import numpy as np

from .variants import VARIANTS, detect_parts


def save_diagnostics(output, frame, polygons, variant, roi, error):
    folder = Path(output).parent / "calibration_diagnostics" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    if not cv2.imwrite(str(folder / "frame.png"), frame):
        raise OSError("Could not save raw calibration frame")
    selection = {"variant": variant, "roi": list(roi), "polygons": [c.tolist() for c in polygons]}
    (folder / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    report = {"accepted": False, "error": str(error), "candidate_profile": error.profile,
              "result": error.result}
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    detected, mask = detect_parts(frame, error.profile)
    preview = frame.copy()
    x, y, _, _ = roi
    for i, part in enumerate(detected):
        contour = np.rint(part["contour"] + [x, y]).astype(np.int32)
        cv2.drawContours(preview, [contour], -1, (0, 255, 0), 1)
        px, py = contour[0, 0]
        cv2.putText(preview, f"{i+1}:{part['color']}", (int(px), int(py)), 0, .4, (255, 255, 255), 1)
    for filename, image in (("detected.png", preview), ("mask.png", mask)):
        if not cv2.imwrite(str(folder / filename), image):
            raise OSError(f"Could not save {filename}")
    return folder


def load_selection(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    frame = cv2.imread(str(path.parent / "frame.png"))
    if frame is None or data.get("variant") not in VARIANTS:
        raise ValueError("Invalid calibration capture: frame.png and known variant required")
    roi = data.get("roi", [])
    if len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError("Invalid captured work area")
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) < 20 or x+w > frame.shape[1] or y+h > frame.shape[0]:
        raise ValueError("Captured work area outside image")
    polygons = []
    if len(data.get("polygons", [])) != 7:
        raise ValueError("Capture requires seven selections")
    for values, vertices in zip(data["polygons"], (3, 3, 4, 4, 3, 3, 3)):
        a = np.asarray(values)
        if a.shape != (vertices, 1, 2) or not np.isfinite(a).all() or (a != np.floor(a)).any() or (a < [x, y]).any() or (a >= [x+w, y+h]).any():
            raise ValueError("Invalid captured corners")
        polygons.append(a.astype(np.int32))
    return frame, polygons, data["variant"], roi
