"""Preset geometry recipe; product pose is detected and only colors are sampled."""
import json
from pathlib import Path
import cv2
import numpy as np

from .color_model import LABELS, palette_from_samples
from .variants import PART_NAMES, VARIANTS, make_relations, validate_variant_profile, inspect_variants
from .vision import learn_color

# Colored surfaces in the user's fixed 640x480 view (2026-09-25).
# Left/right names refer to the upright cat, independently of camera rotation.
CAT_LAYOUT = {
    "name": "cat-camera-20260925", "frame_size": [640, 480], "roi": [95, 5, 475, 470],
    "polygons": [
        [[123, 160], [180, 108], [231, 168]],
        [[139, 35], [246, 36], [187, 91]],
        [[199, 101], [264, 50], [313, 111], [250, 163]],
        [[220, 211], [311, 135], [307, 213], [213, 294]],
        [[232, 306], [312, 234], [389, 322]],
        [[236, 323], [459, 338], [336, 437]],
        [[363, 442], [539, 296], [519, 449]],
    ],
}


def create_color_profile(frame, samples, layout=None, name="tangram"):
    layout = layout or CAT_LAYOUT
    if [frame.shape[1], frame.shape[0]] != layout["frame_size"]:
        raise ValueError("Fixed layout requires its configured camera resolution")
    polygons = [np.asarray(p, np.float32).reshape(-1, 1, 2) for p in layout["polygons"]]
    if len(polygons) != 7:
        raise ValueError("Fixed layout needs seven named polygons")
    scale = max(layout["frame_size"])
    normalized = [p/scale for p in polygons]
    bgr = {label: np.asarray(samples[label], np.uint8).reshape(-1, 1, 3) for label in LABELS}
    model = palette_from_samples({label: cv2.cvtColor(pixels, cv2.COLOR_BGR2LAB).reshape(-1, 3)
                                  for label, pixels in bgr.items()})
    profile = {
        "schema_version": 2, "name": name, "frame_size": layout["frame_size"], "roi": layout["roi"],
        "geometry_mode": "fixed", "layout_name": layout["name"], "search_margin_pixels": 12,
        "colors": {label: learn_color(cv2.cvtColor(bgr[label], cv2.COLOR_BGR2HSV).reshape(-1, 3))
                   for label in LABELS[:-1]}, "color_model": model,
        "parts": [{"name": label, "contour": p.tolist()} for label, p in zip(PART_NAMES, normalized)],
        "variants": {key: dict(zip(PART_NAMES, values)) for key, values in VARIANTS.items()},
        "thresholds": {"position": .025, "area_relative": .3, "shape": .2,
                       "angle_degrees": 10.0, "color_fraction": .65},
        "relations": make_relations(normalized),
        "min_candidate_area_pixels": max(30.0, .25*min(cv2.contourArea(p) for p in polygons)),
    }
    validate_variant_profile(profile)
    return profile


def sample_colors(source, output, image=None, layout_path=None):
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8")) if layout_path else CAT_LAYOUT
    cap = None
    try:
        if image:
            frame = cv2.imread(image)
            if frame is None:
                raise ValueError(f"Cannot read image: {image}")
        else:
            cap = cv2.VideoCapture(source)
            width, height = layout["frame_size"]
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            print("SPACE: freeze image for color sampling; Q: cancel.")
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                cv2.imshow("Color samples", frame)
                key = cv2.waitKey(30) & 255
                if key == ord("q"):
                    return
                if key == 32:
                    break
        if [frame.shape[1], frame.shape[0]] != layout["frame_size"]:
            raise ValueError("Camera/image resolution differs from fixed layout; do not stretch the image")
        samples = {}
        for label in LABELS:
            print(f"{label}: select one or more uniform color patches. ENTER accepts each; ESC finishes this color.")
            if label == "background":
                print("Include dark AND bright blue board patches and neutral base. Do not include colored parts.")
            regions = cv2.selectROIs(f"Sample {label}", frame, showCrosshair=True, fromCenter=False)
            pixels = [frame[y:y+h, x:x+w].reshape(-1, 3) for x, y, w, h in regions if w*h >= 25]
            cv2.destroyWindow(f"Sample {label}")
            if not pixels:
                print("Sampling cancelled: each color/background needs at least 25 pixels.")
                return
            samples[label] = np.concatenate(pixels)
        profile = create_color_profile(frame, samples, layout, Path(output).stem)
        result, mask = inspect_variants(frame, profile)
        preview = frame.copy()
        for name, polygon in zip(PART_NAMES, layout["polygons"]):
            c = np.asarray(polygon, np.int32)
            cv2.polylines(preview, [c], True, (0, 255, 0), 1)
            cv2.putText(preview, name, tuple(c[0]), 0, .4, (255, 255, 255), 1)
        print(f"Fixed template preview. Detected {result['found_count']}/7; current frame: {'PASS' if result['passed'] else 'FAIL'}.")
        print("Template shows reference orientation; product rotation is detected automatically.")
        print("S: save color settings (does NOT accept the product). Q: cancel.")
        cv2.imshow("Fixed template (not detected contours)", preview)
        cv2.imshow("Actual detection mask", mask)
        while True:
            key = cv2.waitKey(30) & 255
            if key == ord("q"):
                return
            if key == ord("s"):
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(profile, indent=2), encoding="utf-8")
                temporary.replace(target)
                print(f"Saved colors and fixed template: {target}")
                return
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
