"""On-demand evidence for debugging recognition without changing a QC result."""
import json
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from .variants import detect_parts


def save_detection(frame, profile, result, mask, output):
    folder = Path(output) / "diagnostics" / str(uuid4())
    folder.mkdir(parents=True)
    overlay = frame.copy()
    if profile.get("schema_version") == 2:
        candidates, _ = detect_parts(frame, profile)
        offset = np.asarray(profile["roi"][:2])
        for i, candidate in enumerate(candidates):
            contour = (candidate["contour"] + offset).astype(np.int32)
            cv2.drawContours(overlay, [contour], -1, (0, 255, 0), 1)
            x, y, _, _ = cv2.boundingRect(contour)
            cv2.putText(overlay, f"{i+1}:{candidate['color']}", (x, y), 0, .4, (255, 255, 255), 1)
    for name, image in (("frame", frame), ("mask", mask), ("candidates", overlay)):
        if not cv2.imwrite(str(folder / f"{name}.png"), image):
            raise OSError("Cannot write detection diagnostics")
    for name, data in (("profile", profile), ("result", result)):
        (folder / f"{name}.json").write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    return folder
