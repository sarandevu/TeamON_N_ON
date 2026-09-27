"""Mirror-implementation tests for EdgePPG quality math (Stage 3).

These tests verify the **math** that the Kotlin Stage-3 components
implement — FrameMetrics (FPS / drop rate / jitter), ExposureStability,
AwbStability, and MotionContamination.

The Kotlin code runs on-device; this Python reimplementation exists so
the algorithms can be unit-tested in any environment with the verified
Windows venv. If the Kotlin algorithms drift from these expectations,
the drift must be reconciled in `docs/implementation_plan.md` and the
Kotlin test must be added when an Android test runner is provisioned.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import unittest
from collections import deque
from typing import Optional


def fps(timestamps_ns: list[int]) -> float:
    """Mirror of FrameMetrics.fps() — NaN if fewer than 2 frames."""
    if len(timestamps_ns) < 2:
        return float("nan")
    if timestamps_ns[-1] <= timestamps_ns[0]:
        return float("nan")
    span_ns = timestamps_ns[-1] - timestamps_ns[0]
    frames = len(timestamps_ns) - 1
    return frames * 1_000_000_000.0 / span_ns


def drop_rate(timestamps_ns: list[int]) -> float:
    """Mirror of FrameMetrics.dropRate() — NaN if fewer than 4 frames."""
    if len(timestamps_ns) < 4:
        return float("nan")
    deltas = [
        max(0, timestamps_ns[i + 1] - timestamps_ns[i])
        for i in range(len(timestamps_ns) - 1)
    ]
    median = sorted(deltas)[len(deltas) // 2]
    if median <= 0:
        return float("nan")
    total_ns = max(1, timestamps_ns[-1] - timestamps_ns[0])
    expected = int(total_ns / median)
    if expected <= 0:
        return float("nan")
    actual = len(timestamps_ns) - 1
    drops = max(0, expected - actual)
    return min(1.0, max(0.0, drops / expected))


def jitter_ms(timestamps_ns: list[int]) -> float:
    if len(timestamps_ns) < 4:
        return float("nan")
    deltas = [
        timestamps_ns[i + 1] - timestamps_ns[i]
        for i in range(len(timestamps_ns) - 1)
    ]
    mean = sum(deltas) / len(deltas)
    var = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    return (math.sqrt(var)) / 1_000_000.0


def exposure_stability(samples: list[tuple[int, int]]) -> float:
    """Mirror of ExposureStability.stability(). Each sample is (exposureNs,
    sensitivityIso)."""
    ev = [e_ns * iso for e_ns, iso in samples if e_ns > 0 and iso > 0]
    if len(ev) < 8:
        return float("nan")
    mean = sum(ev) / len(ev)
    if mean <= 0:
        return float("nan")
    var = sum((v - mean) ** 2 for v in ev) / len(ev)
    cov = math.sqrt(var) / mean
    return max(0.0, min(1.0, 1.0 - cov))


def awb_stability(samples: list[tuple[float, float, float]]) -> float:
    """Mirror of AwbStability.stability(). Each sample is (R, G, B)."""
    rg = [r / g for r, g, b in samples if g > 0]
    bg = [b / g for r, g, b in samples if g > 0]
    if len(rg) < 8:
        return float("nan")
    def cov(xs):
        mean = sum(xs) / len(xs)
        if mean <= 0:
            return float("nan")
        var = sum((x - mean) ** 2 for x in xs) / len(xs)
        return math.sqrt(var) / mean
    rg_cov = cov(rg)
    bg_cov = cov(bg)
    if math.isnan(rg_cov) or math.isnan(bg_cov):
        return float("nan")
    return max(0.0, min(1.0, 1.0 - 0.5 * (rg_cov + bg_cov)))


def motion_contamination(
    frames: list[tuple[float, ...]],
    step_threshold: float = 28.0,
    streak_threshold: int = 3,
) -> bool:
    """Mirror of MotionContamination.observe(): return True iff a streak
    of `streak_threshold` frames each had a max-channel step > threshold."""
    streak = 0
    prev = None
    for fr in frames:
        if prev is None or len(prev) != len(fr):
            prev = fr
            streak = 0
            continue
        step_max = max(abs(fr[i] - prev[i]) for i in range(len(fr)))
        prev = fr
        if step_max > step_threshold:
            streak += 1
        else:
            streak = 0
        if streak >= streak_threshold:
            return True
    return False


# ---- Tests -----------------------------------------------------------------

class FrameMetricsTests(unittest.TestCase):

    def test_perfect_30fps(self):
        # 30 fps = 33_333_333 ns between frames
        ts = [i * 33_333_333 for i in range(60)]
        self.assertAlmostEqual(fps(ts), 30.0, places=1)
        self.assertAlmostEqual(drop_rate(ts), 0.0, places=2)
        self.assertLess(jitter_ms(ts), 0.1)

    def test_dropped_frames(self):
        # 30 fps with every 6th frame missing → ~17% drop rate
        base = [i * 33_333_333 for i in range(60) if i % 6 != 0]
        dr = drop_rate(base)
        # The drop rate is approximate; we just check it's positive and
        # less than 1.0.
        self.assertGreater(dr, 0.0)
        self.assertLess(dr, 1.0)

    def test_too_few_frames_returns_nan(self):
        # 1 frame → fps NaN; 2 frames → fps valid but drop_rate NaN.
        self.assertTrue(math.isnan(fps([1])))
        self.assertTrue(math.isnan(drop_rate([1, 2, 3])))

    def test_monotonic_clock_skew(self):
        # A tiny clock skew (delta varies by ±1ms) should still produce
        # ~30 fps and a small jitter.
        ts = []
        delta = 33_333_333
        for i in range(60):
            ts.append(i * delta + (i % 3) * 1_000_000)
        self.assertAlmostEqual(fps(ts), 30.0, delta=1.0)
        self.assertLess(jitter_ms(ts), 1.5)


class ExposureStabilityTests(unittest.TestCase):

    def test_constant_exposure_is_stable(self):
        # Same (exposureNs, iso) every frame ⇒ stability == 1.0
        samples = [(10_000_000, 100)] * 60
        self.assertAlmostEqual(exposure_stability(samples), 1.0)

    def test_drifting_exposure_is_unstable(self):
        # EV swings 50% → stability should be < 0.8
        samples = []
        for i in range(60):
            samples.append((10_000_000 + i * 1_000_000, 100 + i * 5))
        s = exposure_stability(samples)
        self.assertLess(s, 0.8)

    def test_null_samples_skipped(self):
        # Mix in zeros — they should be silently skipped.
        samples = [(10_000_000, 100)] * 8 + [(0, 0)] * 5
        self.assertAlmostEqual(exposure_stability(samples), 1.0)


class AwbStabilityTests(unittest.TestCase):

    def test_neutral_gains_are_stable(self):
        # R == G == B ⇒ R/G == B/G == 1.0 ⇒ stability == 1.0
        samples = [(1.0, 1.0, 1.0)] * 60
        self.assertAlmostEqual(awb_stability(samples), 1.0)

    def test_drifting_gains_are_unstable(self):
        # R/G swings 0.5..1.5
        samples = [(1.0 + 0.01 * i, 1.0, 1.0) for i in range(60)]
        s = awb_stability(samples)
        self.assertLess(s, 0.95)


class MotionContaminationTests(unittest.TestCase):

    def test_clean_signal_not_contaminated(self):
        # Each channel drifts < 5 per frame.
        frames = [(128.0 + 0.1 * i, 130.0 - 0.1 * i, 120.0) for i in range(20)]
        self.assertFalse(motion_contamination(frames))

    def test_three_consecutive_spikes_flag_contamination(self):
        # Each consecutive frame has a > threshold step in some channel.
        frames = [
            (100.0, 100.0, 100.0),
            (200.0, 200.0, 200.0),  # +100 → spike, streak=1
            (50.0, 50.0, 50.0),    # -150 → spike, streak=2
            (250.0, 250.0, 250.0), # +200 → spike, streak=3 → contaminated
        ]
        self.assertTrue(motion_contamination(frames))

    def test_two_consecutive_spikes_dont_flag(self):
        frames = [
            (100.0, 100.0, 100.0),
            (200.0, 200.0, 200.0),  # +100 spike
            (200.0, 200.0, 200.0),  # +0 → resets? no, also > threshold from prev=200
        ]
        # Actually a step from 200→200 is 0, not > 28 → streak resets.
        self.assertFalse(motion_contamination(frames))

    def test_intermittent_spikes_dont_flag(self):
        frames = [
            (100.0,) * 3,
            (200.0,) * 3,  # 1 spike
            (100.0,) * 3,  # step back: -100 > 28 → spike, streak=2
            (100.0,) * 3,  # 0 step → reset
        ]
        # streak never reaches 3 → not contaminated.
        self.assertFalse(motion_contamination(frames))


if __name__ == "__main__":
    unittest.main(verbosity=2)