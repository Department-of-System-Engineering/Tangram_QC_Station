"""Part-based recipes. No base color, base contour or repaired boundary is used."""
import itertools
import cv2
import numpy as np

from .vision import hsv_mask, interior_mask, learn_color
from .color_model import learn_palette, palette_masks, validate_palette


class ReferenceValidationError(ValueError):
    def __init__(self, message, profile, result, mask):
        super().__init__(message)
        self.profile, self.result, self.mask = profile, result, mask


PART_NAMES = ("left_ear", "right_ear", "head", "neck", "middle", "body", "foot")
# Left/right are named in the upright reference drawing, not current camera pixels.
VARIANTS = {
    "A": ("blue", "yellow", "red", "yellow", "red", "blue", "blue"),
    "B": ("yellow", "blue", "red", "blue", "red", "blue", "blue"),
    "C": ("blue", "blue", "red", "yellow", "red", "blue", "blue"),
    "D": ("yellow", "yellow", "red", "yellow", "red", "yellow", "blue"),
}


def center(c):
    m = cv2.moments(np.asarray(c, np.float32))
    return np.array([m["m10"], m["m01"]]) / max(m["m00"], 1e-12)


def normalize(contours):
    points = np.concatenate(contours).reshape(-1, 2)
    origin = points.min(axis=0)
    scale = max(float(np.ptp(points, axis=0).max()), 1)
    return [(c.astype(np.float32) - origin) / scale for c in contours]


def edges(c):
    c = np.asarray(c, np.float32)
    polygon = cv2.approxPolyDP(c, 0.025 * cv2.arcLength(c, True), True).reshape(-1, 2)
    delta = np.roll(polygon, -1, axis=0) - polygon
    return [(float(np.degrees(np.arctan2(d[1], d[0])) % 180), float(np.linalg.norm(d)))
            for d in delta]


def angle_difference(a, b):
    """Undirected lines: parallel=0, perpendicular=90 (never modulo 90)."""
    return abs((a - b + 90) % 180 - 90)


def edge_correspondence(reference, observed):
    a, b = edges(reference), edges(observed)
    if len(a) != len(b) or len(a) not in (3, 4):
        return None
    # Convex polygon edges stay cyclic; cyclic offset also handles contour start changes.
    options = []
    for sequence in (b, list(reversed(b))):
        for shift in range(len(b)):
            mapped = sequence[shift:] + sequence[:shift]
            error = sum(angle_difference(x[0], y[0]) + 20 * abs(x[1] - y[1])
                        for x, y in zip(a, mapped))
            options.append((error, mapped))
    return min(options, key=lambda pair: pair[0])[1]


def make_relations(contours):
    relations = []
    for i, j in itertools.combinations(range(7), 2):
        for ei, (ai, _) in enumerate(edges(contours[i])):
            for ej, (aj, _) in enumerate(edges(contours[j])):
                difference = angle_difference(ai, aj)
                if difference <= 6 or difference >= 84:
                    relations.append({"a": i, "b": j, "edge_a": ei, "edge_b": ej,
                                      "kind": "parallel" if difference <= 6 else "perpendicular"})
    return relations


def create_variant_profile(frame, polygons, variant, roi, name="tangram"):
    if variant not in VARIANTS or len(polygons) != 7:
        raise ValueError("Select a known A-D variant and outline all seven named parts")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    normalized = normalize(polygons)
    colors = {}
    for color in ("red", "yellow", "blue"):
        samples = [hsv[interior_mask(frame.shape, c) > 0]
                   for c, label in zip(polygons, VARIANTS[variant]) if label == color]
        colors[color] = learn_color(np.concatenate(samples))
    p = {"schema_version": 2, "name": name, "calibration_variant": variant,
         "frame_size": [frame.shape[1], frame.shape[0]], "roi": list(roi), "colors": colors,
         "parts": [{"name": name, "contour": c.tolist()} for name, c in zip(PART_NAMES, normalized)],
         "variants": {key: dict(zip(PART_NAMES, values)) for key, values in VARIANTS.items()},
         "thresholds": {"position": 0.06, "area_relative": 0.3, "shape": 0.2,
                        "angle_degrees": 10.0, "color_fraction": 0.65},
         "relations": make_relations(normalized)}
    p["color_model"] = learn_palette(frame, polygons, VARIANTS[variant], roi)
    validate_variant_profile(p)
    # Refuse a saved recipe that cannot inspect its own reference with real segmentation.
    result, mask = inspect_variants(frame, p, variant)
    if not result["passed"]:
        failures = result["reasons"] + [f"{part['name']}: {','.join(part['reasons'])}"
                                        for part in result["parts"] if part["reasons"]]
        raise ReferenceValidationError("Reference does not pass automatic detection: " + "; ".join(failures), p, result, mask)
    return p


def validate_variant_profile(p):
    if p.get("schema_version") != 2 or not p.get("name"):
        raise ValueError("Invalid variant profile")
    dims = p.get("frame_size", [])
    if len(dims) != 2 or any(type(v) is not int or not 120 <= v <= 4096 for v in dims):
        raise ValueError("Invalid calibration resolution")
    roi = p.get("roi", [])
    if len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError("Invalid work area")
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) < 20 or x+w > dims[0] or y+h > dims[1]:
        raise ValueError("Work area outside image")
    if [part.get("name") for part in p.get("parts", [])] != list(PART_NAMES):
        raise ValueError("Seven named parts required in reference order")
    for part, vertices in zip(p["parts"], (3, 3, 4, 4, 3, 3, 3)):
        a = np.asarray(part["contour"], np.float32)
        if a.shape != (vertices, 1, 2) or not np.isfinite(a).all() or (a < 0).any() or (a > 1).any() or cv2.contourArea(a) <= 0 or not cv2.isContourConvex(a):
            raise ValueError("Each part must be a convex triangle or quadrilateral")
    for color in ("red", "yellow", "blue"):
        a = np.asarray(p["colors"][color])
        if a.shape != (2, 3) or not np.isfinite(a).all() or (a != np.floor(a)).any() or (a < 0).any() or (a > [179, 255, 255]).any() or (a[0, 1:] > a[1, 1:]).any():
            raise ValueError("Invalid color calibration")
    if "color_model" in p:
        validate_palette(p["color_model"])
    if p.get("variants") != {k: dict(zip(PART_NAMES, v)) for k, v in VARIANTS.items()}:
        raise ValueError("Variant map must match the four agreed recipes")
    for key, maximum in (("position", 0.2), ("area_relative", 0.5), ("shape", 1),
                         ("angle_degrees", 20), ("color_fraction", 1)):
        value = p["thresholds"][key]
        if not np.isfinite(value) or not 0 < value <= maximum:
            raise ValueError(f"Invalid threshold: {key}")
    expected = make_relations([np.asarray(part["contour"], np.float32) for part in p["parts"]])
    if not expected or p.get("relations") != expected:
        raise ValueError("Invalid or missing edge relations; recalibrate")


def detect_parts(frame, profile):
    if [frame.shape[1], frame.shape[0]] != profile["frame_size"]:
        raise ValueError("Variant calibration requires the same processing resolution")
    x, y, w, h = profile["roi"]
    if "color_model" in profile:
        masks = palette_masks(frame[y:y+h, x:x+w], profile["color_model"])
    else:
        hsv = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
        masks = {name: hsv_mask(hsv, bounds) for name, bounds in profile["colors"].items()}
    # Separate colors, but never hallucinate boundaries between touching same-color parts.
    found = []
    debug = np.zeros((h, w), np.uint8)
    occupied = np.zeros((h, w), np.uint8)
    for color, mask in masks.items():
        # Ambiguous color pixels cannot be evidence for two pieces.
        others = np.zeros_like(mask)
        for other, other_mask in masks.items():
            if other != color:
                others = cv2.bitwise_or(others, other_mask)
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(others))
        if "color_model" in profile:
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        debug = cv2.bitwise_or(debug, mask)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area < max(30, w*h*0.001):
                continue
            cx, cy, cw, ch = cv2.boundingRect(c)
            if cx == 0 or cy == 0 or cx+cw >= w or cy+ch >= h:
                continue  # colored background crossing the work-area boundary
            inside = interior_mask(mask.shape, c) > 0
            fractions = {name: float(np.count_nonzero((m > 0) & inside) / max(1, inside.sum()))
                         for name, m in masks.items()}
            if np.any(occupied[inside]):
                continue
            occupied[inside] = 255
            found.append({"contour": c.astype(np.float32), "color": color, "fractions": fractions})
    return found, debug


def assign_parts(reference, observed):
    """Minimum-cost one-to-one matching with missing slots, bounded to 16 detections."""
    if len(observed) > 16:
        return {}
    costs = np.array([[np.linalg.norm(center(a)-center(b)) +
                       0.1*abs(np.log(max(cv2.contourArea(b), 1e-8)/cv2.contourArea(a)))
                       for b in observed] for a in reference])
    states = {0: (0.0, {})}
    for j in range(len(observed)):
        updated = dict(states)
        for mask, (cost, mapping) in states.items():
            for i in range(7):
                if not mask & (1 << i):
                    key = mask | (1 << i)
                    value = cost + float(costs[i, j])
                    if key not in updated or value < updated[key][0]:
                        updated[key] = (value, {**mapping, i: j})
        states = updated
    key = min(states, key=lambda k: (7-k.bit_count(), states[k][0]))
    return states[key][1]


def align(reference, observed, mapping):
    if len(mapping) < 3:
        return observed
    a = np.array([center(observed[j]) for i, j in mapping.items()])
    b = np.array([center(reference[i]) for i, j in mapping.items()])
    ac, bc = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a-ac).T @ (b-bc))
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    scale = np.sum(((a-ac) @ rotation)*(b-bc)) / max(np.sum((a-ac)**2), 1e-9)
    return [(((c-ac) @ rotation)*scale+bc).astype(np.float32) for c in observed]


def inspect_variants(frame, profile, expected_variant=None):
    if expected_variant is not None and expected_variant not in VARIANTS:
        raise ValueError("Expected variant must be A, B, C or D")
    detected, debug = detect_parts(frame, profile)
    result = {"object_present": bool(detected), "base_present": bool(detected),
              "passed": False, "found_count": len(detected), "parts": [], "reasons": [],
              "detected_variant": None, "expected_variant": expected_variant,
              "quality_score": 0.0, "relations": []}
    if len(detected) != 7:
        result["reasons"].append("part_count")
    if not detected or len(detected) > 16:
        return result, debug
    reference = [np.asarray(p["contour"], np.float32) for p in profile["parts"]]
    observed = normalize([d["contour"] for d in detected])
    mapping = assign_parts(reference, observed)
    observed = align(reference, observed, mapping)
    limits = profile["thresholds"]
    edge_maps, colors, fractions, geometry_scores = {}, {}, {}, []
    for i, name in enumerate(PART_NAMES):
        part = {"name": name, "passed": False, "reasons": []}
        if i not in mapping:
            part["reasons"] = ["missing"]
            result["parts"].append(part)
            geometry_scores.append(0)
            continue
        j = mapping[i]
        a, b = reference[i], observed[j]
        mapped_edges = edge_correspondence(a, b)
        angle_error = max((angle_difference(x[0], y[0]) for x, y in zip(edges(a), mapped_edges)), default=90) if mapped_edges else 90
        metrics = {"position": float(np.linalg.norm(center(a)-center(b))),
                   "area_relative": abs(cv2.contourArea(b)/cv2.contourArea(a)-1),
                   "shape": float(cv2.matchShapes(a, b, cv2.CONTOURS_MATCH_I1, 0)),
                   "angle_degrees": angle_error}
        part["metrics"] = metrics
        part["reasons"] = [k for k, v in metrics.items() if v > limits[k]]
        if not cv2.isContourConvex(cv2.approxPolyDP(b, 0.025*cv2.arcLength(b, True), True)):
            part["reasons"].append("nonconvex")
        geometry_scores.append(float(np.mean([max(0, 1-v/(2*limits[k])) for k, v in metrics.items()])))
        if mapped_edges:
            edge_maps[i] = mapped_edges
        colors[name] = detected[j]["color"]
        fractions[name] = detected[j]["fractions"]
        part["color"] = colors[name]
        part["color_fractions"] = fractions[name]
        result["parts"].append(part)
    matches = [key for key, recipe in profile["variants"].items()
               if len(colors) == 7 and all(colors[n] == c and fractions[n][c] >= limits["color_fraction"] for n, c in recipe.items())]
    if len(matches) == 1:
        result["detected_variant"] = matches[0]
    else:
        result["reasons"].append("unknown_or_ambiguous_variant")
    if expected_variant and result["detected_variant"] != expected_variant:
        result["reasons"].append("variant_mismatch")
    recipe = profile["variants"].get(expected_variant or result["detected_variant"], {})
    for part in result["parts"]:
        color = recipe.get(part["name"])
        if color and fractions.get(part["name"], {}).get(color, 0) < limits["color_fraction"]:
            part["reasons"].append("color")
        part["passed"] = not part["reasons"]
    relation_scores = []
    for relation in profile["relations"]:
        i, j = relation["a"], relation["b"]
        error = 90.0
        if i in edge_maps and j in edge_maps:
            difference = angle_difference(edge_maps[i][relation["edge_a"]][0], edge_maps[j][relation["edge_b"]][0])
            error = abs(difference - (0 if relation["kind"] == "parallel" else 90))
        result["relations"].append({**relation, "error_degrees": error, "passed": error <= limits["angle_degrees"]})
        relation_scores.append(max(0, 1-error/(2*limits["angle_degrees"])))
    if any(not r["passed"] for r in result["relations"]):
        result["reasons"].append("edge_relations")
    # Pairwise displacement checks cannot be hidden by a high average score.
    position_errors = []
    for i, j in itertools.combinations(mapping, 2):
        error = float(np.linalg.norm((center(observed[mapping[j]])-center(observed[mapping[i]])) - (center(reference[j])-center(reference[i]))))
        position_errors.append(error)
    result["max_relative_position_error"] = max(position_errors, default=1.0)
    if result["max_relative_position_error"] > limits["position"]:
        result["reasons"].append("relative_position")
    color_score = sum(fractions.get(n, {}).get(c, 0) for n, c in recipe.items()) / 7
    result["scores"] = {"geometry": 100*float(np.mean(geometry_scores)),
                        "edge_relations": 100*float(np.mean(relation_scores)) if relation_scores else 0,
                        "relative_position": 100*float(np.mean([max(0, 1-e/(2*limits["position"])) for e in position_errors])) if position_errors else 0,
                        "color": 100*color_score}
    result["quality_score"] = round(.4*result["scores"]["geometry"] + .25*result["scores"]["edge_relations"] + .2*result["scores"]["relative_position"] + .15*result["scores"]["color"], 2)
    result["passed"] = not result["reasons"] and all(p["passed"] for p in result["parts"])
    return result, debug
