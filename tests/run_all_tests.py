"""EdgePPG unified test runner.

Runs every test in `ml.tests` and `verifier.tests` using stdlib unittest.
This is the placeholder CI script until pytest is provisioned in the
verified environment.

Usage:
    .venv\\Scripts\\python.exe -m tests.run_all_tests

Exit code 0 = all tests passed, non-zero = failures.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _suite() -> unittest.TestSuite:
    from ml.tests import test_ml_pipeline
    from verifier.tests import test_calls, test_verify
    from tests import test_quality_math
    from tests import test_decision_truth_table
    from tests import test_schema_parity
    from tests import test_canonical_parity
    from tests import test_challenge_engine
    from tests import test_behavior_estimator
    from tests import test_rppg_dsp
    from tests import test_multi_tracker
    from tests import test_call_dashboard
    from tests import test_transport_contract
    from tests import test_harness
    loader = unittest.TestLoader()
    s = unittest.TestSuite()
    s.addTests(loader.loadTestsFromModule(test_ml_pipeline))
    s.addTests(loader.loadTestsFromModule(test_verify))
    s.addTests(loader.loadTestsFromModule(test_calls))
    s.addTests(loader.loadTestsFromModule(test_quality_math))
    s.addTests(loader.loadTestsFromModule(test_decision_truth_table))
    s.addTests(loader.loadTestsFromModule(test_schema_parity))
    s.addTests(loader.loadTestsFromModule(test_canonical_parity))
    s.addTests(loader.loadTestsFromModule(test_challenge_engine))
    s.addTests(loader.loadTestsFromModule(test_behavior_estimator))
    s.addTests(loader.loadTestsFromModule(test_rppg_dsp))
    s.addTests(loader.loadTestsFromModule(test_multi_tracker))
    s.addTests(loader.loadTestsFromModule(test_transport_contract))
    s.addTests(loader.loadTestsFromModule(test_call_dashboard))
    s.addTests(loader.loadTestsFromModule(test_harness))
    return s


def main() -> int:
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
