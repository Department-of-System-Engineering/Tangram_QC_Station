"""Run on the target Pi with a representative laboratory image and profile."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from qc_station.vision import inspect, load_profile

parser = argparse.ArgumentParser()
parser.add_argument("--image", required=True)
parser.add_argument("--profile", required=True)
parser.add_argument("--frames", type=int, default=200)
args = parser.parse_args()
if args.frames < 1:
    parser.error("frames must be positive")
frame = cv2.imread(args.image)
if frame is None:
    parser.error("Cannot read image")
scale = min(1, 640/frame.shape[1], 480/frame.shape[0])
if scale < 1:
    frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
profile = load_profile(args.profile)
cv2.setNumThreads(2)
for _ in range(10):
    inspect(frame, profile)
times = []
for _ in range(args.frames):
    start = time.perf_counter()
    result, _ = inspect(frame, profile)
    times.append((time.perf_counter()-start)*1000)
print(json.dumps({"frames": args.frames, "size": list(frame.shape[:2]),
                  "median_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95)),
                  "analysis_fps": 1000/float(np.mean(times)), "last_passed": result["passed"],
                  "note": "Analysis only; excludes camera, video writing and display"}, indent=2))
