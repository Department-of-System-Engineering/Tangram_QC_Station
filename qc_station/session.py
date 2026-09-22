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
        self.variant_votes = Counter()
        self.quality_sum = 0.0

    def update(self, result, now):
        present = result.get("object_present", result["base_present"])
        if self.finished:
            if present:
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
                self.variant_votes.clear()
                self.quality_sum = 0.0
            return None
        if self.started is None:
            if not present:
                return None
            self.started = now
        if self.previous_sample is not None and now - self.previous_sample > 1.0:
            self.sampling_gap = True
        self.previous_sample = now
        self.samples += 1
        self.good += bool(result["passed"])
        if result.get("detected_variant"):
            self.variant_votes[result["detected_variant"]] += 1
        self.quality_sum += result.get("quality_score", 0.0)
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
        consistent = True
        winner = None
        if "detected_variant" in result:
            if self.variant_votes:
                candidate, votes = self.variant_votes.most_common(1)[0]
                consistent = votes / self.samples >= self.pass_fraction and result["detected_variant"] == candidate
                if consistent:
                    winner = candidate
            else:
                consistent = False
            passed = passed and consistent
        mixed = len(self.variant_votes) > 1 and not consistent
        final = {"status": "PASS" if passed else "FAIL" if enough and not mixed else "INCONCLUSIVE",
                "samples": self.samples, "passing_samples": self.good,
                "pass_fraction": self.good / self.samples,
                "duration_seconds": now - self.started,
                "sampling_gap": self.sampling_gap,
                "failure_counts": dict(self.failures), "last_frame": result}
        if "detected_variant" in result:
            final.update(detected_variant=winner, expected_variant=result.get("expected_variant"),
                         variant_votes=dict(self.variant_votes),
                         mean_quality_score=round(self.quality_sum / self.samples, 2))
        return final
