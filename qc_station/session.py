"""Bounded-memory voting with one result per insertion and monotonic timing."""
from collections import Counter


class InspectionWindow:
    def __init__(self, seconds=3.0, min_samples=15, pass_fraction=0.8, removal_seconds=0.7):
        if not 0.1 <= seconds <= 60 or min_samples < 2 or not 0 < pass_fraction <= 1 or removal_seconds <= 0:
            raise ValueError("Invalid inspection window settings")
        self.seconds, self.min_samples = seconds, min_samples
        self.pass_fraction, self.removal_seconds = pass_fraction, removal_seconds
        self.started = None
        self.finished = False
        self.absent_since = None
        self.samples = self.good = 0
        self.failures = Counter()
        self.previous_sample = None
        self.sampling_gap = False

    def update(self, result, now):
        if self.finished:
            if result["base_present"]:
                self.absent_since = None
            elif self.absent_since is None:
                self.absent_since = now
            elif now - self.absent_since >= self.removal_seconds:
                self.started = None
                self.finished = False
                self.samples = self.good = 0
                self.failures.clear()
                self.absent_since = None
                self.previous_sample = None
                self.sampling_gap = False
            return None
        if self.started is None:
            if not result["base_present"]:
                return None
            self.started = now
        if self.previous_sample is not None and now - self.previous_sample > 1.0:
            self.sampling_gap = True
        self.previous_sample = now
        self.samples += 1
        self.good += bool(result["passed"])
        for reason in result["reasons"]:
            self.failures[reason] += 1
        for part in result["parts"]:
            for reason in part["reasons"]:
                self.failures[f'{part["name"]}:{reason}'] += 1
        if now - self.started < self.seconds:
            return None
        self.finished = True
        enough = self.samples >= self.min_samples and not self.sampling_gap
        passed = enough and self.good / self.samples >= self.pass_fraction and result["passed"]
        return {"status": "PASS" if passed else "FAIL" if enough else "INCONCLUSIVE",
                "samples": self.samples, "passing_samples": self.good,
                "pass_fraction": self.good / self.samples,
                "duration_seconds": now - self.started,
                "sampling_gap": self.sampling_gap,
                "failure_counts": dict(self.failures), "last_frame": result}
