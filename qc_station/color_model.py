"""Small foreground/background Lab palette learned only during calibration."""
import cv2
import numpy as np

LABELS = ("red", "yellow", "blue", "background")


def learn_palette(frame, polygons, colors, roi):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    selected = np.zeros(frame.shape[:2], np.uint8)
    samples = {label: [] for label in LABELS}
    for polygon, color in zip(polygons, colors):
        region = np.zeros_like(selected)
        cv2.drawContours(region, [polygon], -1, 255, -1)
        selected |= region
        # Stay clear of the outline; it is not part of the material's color.
        region = cv2.erode(region, np.ones((7, 7), np.uint8))
        samples[color].append(lab[region > 0])
    x, y, w, h = roi
    background = np.zeros_like(selected)
    background[y:y+h, x:x+w] = 255
    background[cv2.dilate(selected, np.ones((7, 7), np.uint8)) > 0] = 0
    samples["background"].append(lab[background > 0])
    return palette_from_samples({label: np.concatenate(samples[label]) for label in LABELS})


def palette_from_samples(samples):
    """Build the same bounded Lab model from explicit color/background swatches."""
    model = {"space": "LAB", "centers": {}, "max_distance_squared": {}}
    for label in LABELS:
        pixels = np.asarray(samples[label], np.float32).reshape(-1, 3)
        if len(pixels) < 25:
            raise ValueError(f"Too few {label} pixels: enlarge work area margin or check corners")
        pixels = pixels[np.linspace(0, len(pixels)-1, min(len(pixels), 4096), dtype=int)]
        k = min(8, len(np.unique(pixels, axis=0)))
        cv2.setRNGSeed(41)
        _, _, centers = cv2.kmeans(pixels, k, None,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.2),
            1, cv2.KMEANS_PP_CENTERS)
        distances = np.min(np.sum((pixels[:, None, :] - centers[None, :, :])**2, axis=2), axis=1)
        model["centers"][label] = centers.tolist()
        model["max_distance_squared"][label] = float(max(100, np.percentile(distances, 99) + 25))
    return model


def validate_palette(model):
    if model.get("space") != "LAB" or set(model.get("centers", {})) != set(LABELS):
        raise ValueError("Invalid Lab palette")
    for label in LABELS:
        a = np.asarray(model["centers"][label])
        if a.ndim != 2 or a.shape[1] != 3 or not 1 <= len(a) <= 8 or not np.isfinite(a).all() or (a < 0).any() or (a > 255).any():
            raise ValueError("Invalid Lab centers")
        distance = model["max_distance_squared"][label]
        if not np.isfinite(distance) or not 0 < distance <= 3*255**2:
            raise ValueError("Invalid Lab distance limit")


def palette_masks(frame, model):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    distances = []
    for label in LABELS:
        minimum = np.full(frame.shape[:2], np.inf, np.float32)
        # No H*W*K*3 tensor: memory bounded to a handful of ROI-sized arrays.
        for point in model["centers"][label]:
            delta = lab - np.asarray(point, np.float32)
            minimum = np.minimum(minimum, np.sum(delta*delta, axis=2))
        distances.append(minimum)
    stacked = np.stack(distances)
    winner = np.argmin(stacked, axis=0)
    best_two = np.partition(stacked, 1, axis=0)[:2]
    # Equal/near-equal classes are unknown, never duplicate evidence.
    confident = best_two[1] - best_two[0] > 4
    return {label: np.uint8((winner == i) & confident &
                           (distances[i] <= model["max_distance_squared"][label])) * 255
            for i, label in enumerate(LABELS[:-1])}
