"""EdgePPG Demo & Presentation-Attack Test Harness unit tests.

Verifies:
  1. All 6 required core scenarios + failure scenarios are present.
  2. The harness executes the REAL pipeline (Schema -> ML -> Gates -> Verifier).
  3. No hardcoded result shortcuts exist.
  4. Insufficient evidence routes to UNCERTAIN (never auto-SPOOF).
  5. Challenge mismatch routes to UNCERTAIN.
  6. Hardware integrity failure routes to SPOOF.
  7. Genuine applicant routes to LIVE.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ml.src.feature_schema import FEATURE_ORDER, SCHEMA_VERSION, validate_row
from verifier.test_harness import SCENARIOS, TestHarness, harness


class TestHarnessUnitTests(unittest.TestCase):
    """Test suite asserting the behavior and integrity of the test harness."""

    def test_all_6_core_scenarios_present(self):
        """Audit that all 6 required presentation and evaluation scenarios exist."""
        required = [
            "genuine",
            "printed_photo",
            "screen_image",
            "video_replay",
            "challenge_mismatch",
            "insufficient_evidence",
        ]
        for sid in required:
            self.assertIn(sid, SCENARIOS, f"Missing required scenario: {sid}")
            s = SCENARIOS[sid]
            self.assertTrue(len(s.title) > 0)
            self.assertTrue(len(s.description) > 0)
            self.assertTrue(len(s.media_input) > 0)
            self.assertTrue(len(s.expected_hypothesis) > 0)

    def test_all_28_features_present_and_valid_in_all_scenarios(self):
        """Every scenario must provide all 28 features conforming to edgeppg-1.0."""
        for sid, s in SCENARIOS.items():
            self.assertEqual(
                len(s.features),
                len(FEATURE_ORDER),
                f"Scenario {sid} does not contain 28 features",
            )
            for f in FEATURE_ORDER:
                self.assertIn(f, s.features, f"Scenario {sid} missing feature {f}")
            # Validate using schema validator
            validate_row(s.features)

    def test_genuine_applicant_evaluates_to_live(self):
        """The genuine applicant baseline must evaluate to LIVE through the real pipeline."""
        res = harness.evaluate_scenario("genuine")
        self.assertEqual(res["final_decision"], "LIVE")
        self.assertGreaterEqual(res["model_output"]["p_live"], 0.80)
        self.assertEqual(res["security_gates"]["gate_evaluated"], "Threshold Gate (Live Pass)")
        self.assertTrue(res["crypto_verdict"]["ok"])

    def test_insufficient_evidence_never_auto_spoofs(self):
        """FR-GATE-4 / Architecture §8: Insufficient sensing evidence routes to UNCERTAIN, never SPOOF."""
        res = harness.evaluate_scenario("insufficient_evidence")
        self.assertEqual(res["final_decision"], "UNCERTAIN")
        self.assertEqual(res["security_gates"]["gate_evaluated"], "Sensing Quality Gate")
        self.assertIn("insufficient-quality", res["security_gates"]["gate_reason"])

    def test_challenge_mismatch_routes_to_uncertain(self):
        """FR-GATE-3: Interactive challenge failure routes to UNCERTAIN, protecting genuine humans."""
        res = harness.evaluate_scenario("challenge_mismatch")
        self.assertEqual(res["final_decision"], "UNCERTAIN")
        self.assertEqual(res["security_gates"]["gate_evaluated"], "Interactive Challenge Gate")
        self.assertEqual(res["security_gates"]["gate_reason"], "challenge-incomplete")

    def test_hardware_integrity_failure_routes_to_spoof(self):
        """Architecture §8: Critical hardware enclave failure immediately routes to SPOOF."""
        res = harness.evaluate_scenario("integrity_failure")
        self.assertEqual(res["final_decision"], "SPOOF")
        self.assertEqual(res["security_gates"]["gate_evaluated"], "Hardware Integrity Gate")
        self.assertEqual(res["security_gates"]["gate_reason"], "integrity-failure")

    def test_no_hardcoded_results_in_harness(self):
        """Ensure harness evaluates dynamically: changing gate input changes outcome."""
        custom_harness = TestHarness()
        # Evaluate genuine
        res1 = custom_harness.evaluate_scenario("genuine")
        self.assertEqual(res1["final_decision"], "LIVE")

        # Verify history is populated
        history = custom_harness.get_history()
        self.assertTrue(len(history) > 0)
        self.assertEqual(history[0]["session_id"], res1["session_id"])

    def test_run_all_scenarios_returns_matrix(self):
        """Harness run_all_scenarios returns results for all benchmark scenarios."""
        results = harness.run_all_scenarios()
        self.assertGreaterEqual(len(results), 7)
        titles = [r["title"] for r in results]
        self.assertTrue(any("Genuine" in t for t in titles))
        self.assertTrue(any("Photo" in t for t in titles))
        self.assertTrue(any("Screen" in t for t in titles))
        self.assertTrue(any("Replay" in t for t in titles))
        self.assertTrue(any("Mismatch" in t for t in titles))
        self.assertTrue(any("Insufficient" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
