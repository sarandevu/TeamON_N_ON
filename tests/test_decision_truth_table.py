"""Stage 11 — Decision engine truth-table tests (Python mirror).

The Kotlin `DecisionEngine.kt` is mirrored here as Python so we can
unit-test the gating logic exhaustively in the verified venv. When an
Android test runner is provisioned, the same table must be encoded as
Kotlin/JUnit tests; the Python mirror is the source of truth for the
documented gate behaviour.

Architectural reference: Architecture §8, FR-GATE-1..8.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import unittest
from dataclasses import dataclass


LIVE = "LIVE"
SPOOF = "SPOOF"
UNCERTAIN = "UNCERTAIN"


# Default placeholder thresholds (FR-GATE-8).
LIVE_THRESHOLD = 0.80
SPOOF_THRESHOLD = 0.20
MIN_FPS = 25.0
MAX_DROP_RATE = 0.10
MIN_EXP_STAB = 0.80
MIN_AWB_STAB = 0.80


@dataclass
class Inputs:
    integrity_ok: bool
    has_face: bool
    lock_state: bool
    contamination_flag: bool
    fps: float
    drop_rate: float
    exposure_stability: float
    awb_stability: float
    challenge_completed: bool
    live_probability: float


def decide(inputs: Inputs) -> tuple[str, str]:
    """Mirror of DecisionEngine.decide() — return (decision, reason)."""
    if not inputs.integrity_ok:
        return SPOOF, "integrity-failure"

    if (
        not inputs.has_face
        or not inputs.lock_state
        or inputs.contamination_flag
    ):
        reasons = []
        if not inputs.has_face:
            reasons.append("no-face")
        if not inputs.lock_state:
            reasons.append("no-lock")
        if inputs.contamination_flag:
            reasons.append("contamination")
        return UNCERTAIN, "insufficient-quality:" + ",".join(reasons)

    if math.isnan(inputs.fps) or inputs.fps < MIN_FPS:
        return UNCERTAIN, f"low-fps:{inputs.fps}"

    if (
        not math.isnan(inputs.drop_rate)
        and inputs.drop_rate > MAX_DROP_RATE
    ):
        return UNCERTAIN, f"high-drop-rate:{inputs.drop_rate}"

    if (
        not math.isnan(inputs.exposure_stability)
        and inputs.exposure_stability < MIN_EXP_STAB
    ):
        return UNCERTAIN, f"low-exposure-stability:{inputs.exposure_stability}"

    if (
        not math.isnan(inputs.awb_stability)
        and inputs.awb_stability < MIN_AWB_STAB
    ):
        return UNCERTAIN, f"low-awb-stability:{inputs.awb_stability}"

    if not inputs.challenge_completed:
        return UNCERTAIN, "challenge-incomplete"

    if math.isnan(inputs.live_probability):
        return UNCERTAIN, "no-ml-evidence:NaN"

    if inputs.live_probability >= LIVE_THRESHOLD:
        return LIVE, f"p(live)>=live-threshold:{inputs.live_probability}"
    if inputs.live_probability <= SPOOF_THRESHOLD:
        return SPOOF, f"p(live)<=spoof-threshold:{inputs.live_probability}"
    return UNCERTAIN, f"p(live)-borderline:{inputs.live_probability}"


def _baseline_ok() -> Inputs:
    """A inputs row that satisfies every quality check and has a high
    P(LIVE). Tests can override individual fields."""
    return Inputs(
        integrity_ok=True,
        has_face=True,
        lock_state=True,
        contamination_flag=False,
        fps=30.0,
        drop_rate=0.01,
        exposure_stability=0.95,
        awb_stability=0.95,
        challenge_completed=True,
        live_probability=0.95,
    )


class DecisionEngineTests(unittest.TestCase):

    # ---- Integrity -------------------------------------------------------

    def test_integrity_failure_is_spoof(self):
        i = _baseline_ok()
        i.integrity_ok = False
        d, reason = decide(i)
        self.assertEqual(d, SPOOF)
        self.assertEqual(reason, "integrity-failure")

    # ---- Quality gate ---------------------------------------------------

    def test_no_face_is_uncertain_not_spoof(self):
        i = _baseline_ok()
        i.has_face = False
        d, _ = decide(i)
        self.assertEqual(d, UNCERTAIN)

    def test_no_lock_is_uncertain(self):
        i = _baseline_ok()
        i.lock_state = False
        d, _ = decide(i)
        self.assertEqual(d, UNCERTAIN)

    def test_contamination_is_uncertain(self):
        i = _baseline_ok()
        i.contamination_flag = True
        d, _ = decide(i)
        self.assertEqual(d, UNCERTAIN)

    def test_low_fps_is_uncertain(self):
        i = _baseline_ok()
        i.fps = 10.0
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("low-fps", reason)

    def test_nan_fps_is_uncertain(self):
        i = _baseline_ok()
        i.fps = float("nan")
        d, _ = decide(i)
        self.assertEqual(d, UNCERTAIN)

    def test_high_drop_rate_is_uncertain(self):
        i = _baseline_ok()
        i.drop_rate = 0.50
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("high-drop-rate", reason)

    def test_low_exposure_stability_is_uncertain(self):
        i = _baseline_ok()
        i.exposure_stability = 0.50
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("low-exposure-stability", reason)

    def test_nan_exposure_stability_does_not_block(self):
        # NaN signals are propagated, not treated as failures.
        i = _baseline_ok()
        i.exposure_stability = float("nan")
        d, reason = decide(i)
        self.assertEqual(d, LIVE)
        self.assertNotIn("exposure", reason)

    def test_low_awb_stability_is_uncertain(self):
        i = _baseline_ok()
        i.awb_stability = 0.50
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("low-awb-stability", reason)

    # ---- Challenge ------------------------------------------------------

    def test_challenge_incomplete_is_uncertain(self):
        i = _baseline_ok()
        i.challenge_completed = False
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertEqual(reason, "challenge-incomplete")

    # ---- ML probability ------------------------------------------------

    def test_nan_live_probability_is_uncertain_not_spoof(self):
        i = _baseline_ok()
        i.live_probability = float("nan")
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertEqual(reason, "no-ml-evidence:NaN")

    def test_high_live_probability_is_live(self):
        i = _baseline_ok()
        i.live_probability = 0.95
        d, reason = decide(i)
        self.assertEqual(d, LIVE)
        self.assertIn("p(live)>=live-threshold", reason)

    def test_low_live_probability_is_spoof(self):
        i = _baseline_ok()
        i.live_probability = 0.05
        d, reason = decide(i)
        self.assertEqual(d, SPOOF)
        self.assertIn("p(live)<=spoof-threshold", reason)

    def test_borderline_live_probability_is_uncertain(self):
        i = _baseline_ok()
        i.live_probability = 0.50
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("borderline", reason)

    def test_at_boundary_live_is_live(self):
        i = _baseline_ok()
        i.live_probability = 0.80
        d, _ = decide(i)
        self.assertEqual(d, LIVE)

    def test_at_boundary_spoof_is_spoof(self):
        i = _baseline_ok()
        i.live_probability = 0.20
        d, _ = decide(i)
        self.assertEqual(d, SPOOF)

    # ---- Ordering ------------------------------------------------------

    def test_integrity_wins_over_quality(self):
        # Integrity failure → SPOOF, even when quality would say UNCERTAIN.
        i = _baseline_ok()
        i.integrity_ok = False
        i.has_face = False
        d, _ = decide(i)
        self.assertEqual(d, SPOOF)

    def test_quality_wins_over_challenge(self):
        # Quality issue → UNCERTAIN, even when challenge is incomplete.
        i = _baseline_ok()
        i.has_face = False
        i.challenge_completed = False
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertIn("no-face", reason)

    def test_challenge_wins_over_ml(self):
        # Challenge incomplete → UNCERTAIN, even when P(LIVE) is high.
        i = _baseline_ok()
        i.challenge_completed = False
        i.live_probability = 0.99
        d, reason = decide(i)
        self.assertEqual(d, UNCERTAIN)
        self.assertEqual(reason, "challenge-incomplete")

    def test_ml_below_spoof_threshold_is_spoof(self):
        # Even with full quality, a very low P(LIVE) goes to SPOOF.
        i = _baseline_ok()
        i.live_probability = 0.0
        d, _ = decide(i)
        self.assertEqual(d, SPOOF)

    # ---- Full truth table ---------------------------------------------

    def test_truth_table_16_rows(self):
        """An exhaustive 16-row sweep covering every gate."""
        rows = [
            # integrity face lock contam fps dr exp awb chal p_live   → expected
            (False, True,  True,  False, 30, 0.01, 0.95, 0.95, True,  0.95, SPOOF),
            (True,  False, True,  False, 30, 0.01, 0.95, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  False, False, 30, 0.01, 0.95, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  True,  True,  30, 0.01, 0.95, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  True,  False, 5,  0.01, 0.95, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.50, 0.95, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, 0.50, 0.95, True,  0.95, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.50, True,  0.95, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, False, 0.95, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, True,  float('nan'), UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, True,  0.95, LIVE),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, True,  0.05, SPOOF),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, True,  0.50, UNCERTAIN),
            (True,  True,  True,  False, 30, 0.01, float('nan'), 0.95, True, 0.95, LIVE),
            (True,  True,  True,  False, 30, float('nan'), 0.95, 0.95, True, 0.95, LIVE),
            (True,  True,  True,  False, 30, 0.01, 0.95, 0.95, True,  0.80, LIVE),
        ]
        for r in rows:
            inputs = Inputs(
                integrity_ok=r[0], has_face=r[1], lock_state=r[2],
                contamination_flag=r[3], fps=r[4], drop_rate=r[5],
                exposure_stability=r[6], awb_stability=r[7],
                challenge_completed=r[8], live_probability=r[9],
            )
            d, _ = decide(inputs)
            self.assertEqual(d, r[10], f"row {r} → got {d}, want {r[10]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)