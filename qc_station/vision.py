"""CPU-only inspection, calibrated against a known-good, fixed-pose product."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def hsv_mask(hsv, bounds):
    lo, hi = (np.asarray(x, dtype=np.uint8) for x in bounds)
    if lo[0] <= hi[0]:
        return cv2.inRange(hsv, lo, hi)
    return cv2.bitwise_or(
        cv2.inRange(hsv, np.array([0, lo[1], lo[2]], np.uint8), hi),
        cv2.inRange(hsv, lo, np.array([179, hi[1], hi[2]], np.uint8)),
    )


def learn_color(pixels):
    if len(pixels) < 25:
        raise ValueError("Too few interior pixels for color calibration")
    angles = pixels[:, 0].astype(float) * (2 * np.pi / 180)
    center = (np.angle(np.mean(np.exp(1j * angles))) * 180 / (2 * np.pi)) % 180
    offsets = (pixels[:, 0].astype(float) - center + 90) % 180 - 90
    h0, h1 = np.percentile(offsets, [2, 98]) + [-5, 5]
    if h1 - h0 > 100:
        raise ValueError("Color sample too heterogeneous; select a uniform surface")
    sv0 = np.maximum(0, np.percentile(pixels[:, 1:], 2, axis=0) - [25, 35])
    sv1 = np.minimum(255, np.percentile(pixels[:, 1:], 98, axis=0) + [25, 35])
    return [[int((center + h0) % 180), *sv0.astype(int).tolist()],
            [int((center + h1) % 180), *sv1.astype(int).tolist()]]


def interior_mask(shape, contour):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    return cv2.erode(mask, np.ones((5, 5), np.uint8))


def repair_mask(mask, segmentation=None):
    """Close small gaps; optional short bridges require observed color at both ends."""
    config = segmentation or {}
    size = config.get("close_kernel", 3)
    repaired = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((size, size), np.uint8))
    if config.get("bridges"):
        if config["frame_size"] != [mask.shape[1], mask.shape[0]]:
            raise ValueError("Bridge calibration requires the original image resolution")
        support = cv2.dilate(mask, np.ones((5, 5), np.uint8))
        for a, b in config["bridges"]:
            if support[a[1], a[0]] and support[b[1], b[0]]:
                cv2.line(repaired, tuple(a), tuple(b), 255, 3)
    return repaired


def extract(frame, base_hsv, min_base_fraction=0.03, segmentation=None):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = hsv_mask(hsv, base_hsv)
    mask = repair_mask(mask, segmentation)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return None, [], mask
    index = max(range(len(contours)), key=lambda i: cv2.contourArea(contours[i]))
    base = contours[index]
    if cv2.contourArea(base) < frame.shape[0] * frame.shape[1] * min_base_fraction:
        return None, [], mask
    x, y, w, h = cv2.boundingRect(base)
    if x <= 0 or y <= 0 or x + w >= frame.shape[1] or y + h >= frame.shape[0]:
        return None, [], mask  # a clipped product must never pass
    parts = [c for i, c in enumerate(contours)
             if hierarchy[0][i][3] == index and cv2.contourArea(c) > w * h * 0.005]
    return base, parts, mask


def normalized(contour, box):
    x, y, w, h = box
    return (contour.astype(np.float32) - [x, y]) / [w, h]


def raster(contour):
    mask = np.zeros((256, 256), np.uint8)
    cv2.drawContours(mask, [np.rint(np.asarray(contour) * 255).astype(np.int32)], -1, 255, -1)
    return mask


def overlap(a, b):
    a, b = raster(a) > 0, raster(b) > 0
    return float(np.count_nonzero(a & b) / max(1, np.count_nonzero(a | b)))


def create_profile(frame, bounds, name="tangram", expected_count=7, segmentation=None):
    base, parts, _ = extract(frame, bounds, segmentation=segmentation)
    if base is None or len(parts) != expected_count:
        raise ValueError(f"Need a complete base and exactly {expected_count} separate parts; found {len(parts)}")
    box = cv2.boundingRect(base)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    parts.sort(key=lambda c: (cv2.boundingRect(c)[1], cv2.boundingRect(c)[0]))
    profile = {"schema_version": 1, "name": name, "base_hsv": bounds,
               "aspect_ratio": box[2] / box[3], "base_contour": normalized(base, box).tolist(),
               "thresholds": {"area_relative": 0.25, "position": 0.08,
                              "shape": 0.20, "overlap": 0.65, "color_fraction": 0.65},
               "parts": []}
    if segmentation is not None:
        profile["segmentation"] = segmentation
    for i, c in enumerate(parts):
        pixels = hsv[interior_mask(frame.shape, c) > 0]
        profile["parts"].append({"name": f"part_{i + 1}",
                                 "contour": normalized(c, box).tolist(),
                                 "hsv": learn_color(pixels)})
    return profile


def validate_profile(p):
    if p.get("schema_version") == 2:
        from .variants import validate_variant_profile
        return validate_variant_profile(p)
    if p.get("schema_version") != 1 or not p.get("name") or len(p.get("parts", [])) != 7:
        raise ValueError("Expected a version 1 profile with seven parts")

    def bounds(value):
        a = np.asarray(value)
        if a.shape != (2, 3) or not np.isfinite(a).all() or (a < 0).any() or (a > [179, 255, 255]).any() or (a != np.floor(a)).any():
            raise ValueError("Invalid HSV bounds")
        if (a[0, 1:] > a[1, 1:]).any():
            raise ValueError("Invalid saturation/value interval")
    bounds(p["base_hsv"])
    config = p.get("segmentation", {})
    size = config.get("close_kernel", 3)
    if type(size) is not int or size not in range(1, 16, 2):
        raise ValueError("Closing kernel must be odd and between 1 and 15")
    bridges = config.get("bridges", [])
    if not isinstance(bridges, list) or len(bridges) > 20:
        raise ValueError("At most 20 repair bridges allowed")
    if bridges:
        dims = config.get("frame_size", [])
        if len(dims) != 2 or any(type(v) is not int or not 1 <= v <= 4096 for v in dims):
            raise ValueError("Invalid bridge frame size")
        for bridge in bridges:
            a = np.asarray(bridge)
            if a.shape != (2, 2) or not np.isfinite(a).all() or (a != np.floor(a)).any() or (a < 0).any() or (a >= dims).any() or not 0 < np.linalg.norm(a[0] - a[1]) <= 40:
                raise ValueError("Repair bridges must be inside the image and at most 40 pixels long")
    if not np.isfinite(p["aspect_ratio"]) or p["aspect_ratio"] <= 0:
        raise ValueError("Invalid base aspect ratio")
    for c in [p["base_contour"]] + [item["contour"] for item in p["parts"]]:
        a = np.asarray(c, np.float32)
        if a.ndim != 3 or a.shape[1:] != (1, 2) or len(a) < 3 or not np.isfinite(a).all() or (a < 0).any() or (a > 1).any() or cv2.contourArea(a) <= 0:
            raise ValueError("Invalid normalized contour")
    if len({item["name"] for item in p["parts"]}) != 7:
        raise ValueError("Part names must be unique")
    for item in p["parts"]:
        bounds(item["hsv"])
    for key in ("area_relative", "position", "shape", "overlap", "color_fraction"):
        value = p["thresholds"][key]
        if not np.isfinite(value) or not 0 < value <= 1:
            raise ValueError(f"Invalid threshold: {key}")


def load_profile(path):
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_profile(p)
    return p


def profile_id(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:16]


def inspect(frame, profile, expected_variant=None):
    if profile.get("schema_version") == 2:
        from .variants import inspect_variants
        return inspect_variants(frame, profile, expected_variant)
    if expected_variant is not None:
        raise ValueError("Variant recognition requires a new version 2 calibration")
    base, candidates, mask = extract(frame, profile["base_hsv"], segmentation=profile.get("segmentation"))
    result = {"base_present": base is not None, "passed": False,
              "found_count": len(candidates), "parts": [], "reasons": []}
    if base is None:
        result["reasons"] = ["base_missing_or_clipped"]
        return result, mask
    box = cv2.boundingRect(base)
    if abs(box[2] / box[3] / profile["aspect_ratio"] - 1) > 0.15 or overlap(normalized(base, box), profile["base_contour"]) < 0.8:
        result["reasons"].append("base_pose_or_shape")
    if len(candidates) != len(profile["parts"]):
        result["reasons"].append("part_count")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    remaining = set(range(len(candidates)))
    thresholds = profile["thresholds"]
    for expected in profile["parts"]:
        reference = np.asarray(expected["contour"], np.float32)
        # Position-constrained assignment prevents one detection serving two parts.
        index = max(remaining, key=lambda i: overlap(normalized(candidates[i], box), reference), default=None)
        part = {"name": expected["name"], "passed": False, "reasons": []}
        if index is None:
            part["reasons"] = ["missing"]
        else:
            remaining.remove(index)
            c = candidates[index]
            n = normalized(c, box).astype(np.float32)

            def center(contour):
                m = cv2.moments(contour)
                return np.array([m["m10"], m["m01"]]) / max(m["m00"], 1e-12)
            interior = interior_mask(frame.shape, c) > 0
            metrics = {"area_relative": abs(cv2.contourArea(n) / cv2.contourArea(reference) - 1),
                       "position": float(np.linalg.norm(center(n) - center(reference))),
                       "shape": float(cv2.matchShapes(n, reference, cv2.CONTOURS_MATCH_I1, 0)),
                       "overlap": overlap(n, reference),
                       "color_fraction": float(np.count_nonzero((hsv_mask(hsv, expected["hsv"]) > 0) & interior) / max(1, np.count_nonzero(interior)))}
            part["metrics"] = metrics
            part["reasons"] = [k for k, v in metrics.items() if
                               (v < thresholds[k] if k in ("overlap", "color_fraction") else v > thresholds[k])]
            part["passed"] = not part["reasons"]
        result["parts"].append(part)
    result["passed"] = not result["reasons"] and all(x["passed"] for x in result["parts"])
    return result, mask
