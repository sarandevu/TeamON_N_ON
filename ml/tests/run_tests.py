"""EdgePPG PC-side test runner.

Runs the ML pipeline tests using only stdlib (no pytest dependency).

Usage:
    .venv\\Scripts\\python.exe -m ml.tests.run_tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make `ml.src` importable as a package.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _make_suite() -> unittest.TestSuite:
    # Importing the test module triggers the heavy imports (numpy, sklearn).
    from ml.tests import test_ml_pipeline
    loader = unittest.TestLoader()
    return loader.loadTestsFromModule(test_ml_pipeline)


def main() -> int:
    suite = _make_suite()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
