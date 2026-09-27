"""Schema parity tests (Stage 9).

These tests assert that the Kotlin `FeatureSchema.kt` and the Python
`ml/src/feature_schema.py` define the **same** 28-feature schema — same
names, same order, same auxiliary columns, same schema version.

The test parses the Kotlin source for `FEATURE_ORDER` directly. If the
Kotlin source is updated and the Python schema isn't (or vice versa),
the test fails. This is the contract enforcement between the device
runtime and the PC training pipeline.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from ml.src.feature_schema import (  # noqa: E402
    AUX_COLUMNS,
    FEATURE_ORDER,
    SCHEMA_VERSION,
    ZERO_FORBIDDEN,
)


def _read_kotlin_source() -> str:
    kt_path = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
               / "com" / "edgeppg" / "app" / "features" / "FeatureSchema.kt")
    return kt_path.read_text(encoding="utf-8")


def _extract_array(source: str, var_name: str) -> list[str]:
    """Extract a Kotlin `val X = arrayOf("a", "b", ...)` from source."""
    m = re.search(
        rf'val\s+{re.escape(var_name)}\s*:\s*Array<String>\s*=\s*'
        rf'arrayOf\((.*?)\)',
        source, re.DOTALL,
    )
    if not m:
        raise AssertionError(f"could not find {var_name} in Kotlin source")
    inner = m.group(1)
    return re.findall(r'"([^"]+)"', inner)


def _extract_set(source: str, var_name: str) -> set[str]:
    m = re.search(
        rf'val\s+{re.escape(var_name)}\s*:\s*Set<String>\s*=\s*'
        rf'setOf\((.*?)\)',
        source, re.DOTALL,
    )
    if not m:
        raise AssertionError(f"could not find {var_name} in Kotlin source")
    inner = m.group(1)
    return set(re.findall(r'"([^"]+)"', inner))


def _extract_constant_string(source: str, const_name: str) -> str:
    # Either `const val X = "..."` or `const val X: String = "..."`.
    patterns = [
        rf'const\s+val\s+{re.escape(const_name)}\s*:\s*String\s*=\s*"([^"]+)"',
        rf'const\s+val\s+{re.escape(const_name)}\s*=\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, source)
        if m:
            return m.group(1)
    raise AssertionError(f"could not find {const_name} in Kotlin source")


class SchemaParityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kotlin_src = _read_kotlin_source()

    def test_feature_order_matches_python(self):
        kotlin_features = _extract_array(self.kotlin_src, "FEATURE_ORDER")
        self.assertEqual(
            kotlin_features, list(FEATURE_ORDER),
            "Kotlin FEATURE_ORDER must match Python FEATURE_ORDER exactly"
        )

    def test_feature_count_is_28(self):
        kotlin_features = _extract_array(self.kotlin_src, "FEATURE_ORDER")
        self.assertEqual(len(kotlin_features), 28)
        self.assertEqual(len(FEATURE_ORDER), 28)

    def test_aux_columns_match(self):
        kotlin_aux = _extract_array(self.kotlin_src, "AUX_COLUMNS")
        self.assertEqual(
            kotlin_aux, list(AUX_COLUMNS),
            "Kotlin AUX_COLUMNS must match Python AUX_COLUMNS exactly"
        )

    def test_schema_version_matches(self):
        kotlin_version = _extract_constant_string(self.kotlin_src,
                                                  "SCHEMA_VERSION")
        self.assertEqual(kotlin_version, SCHEMA_VERSION)

    def test_zero_forbidden_set_matches(self):
        kotlin_zf = _extract_set(self.kotlin_src, "ZERO_FORBIDDEN")
        self.assertEqual(
            kotlin_zf, set(ZERO_FORBIDDEN),
            "Kotlin ZERO_FORBIDDEN must match the Python ZERO_FORBIDDEN"
        )

    def test_first_feature_is_face_confidence(self):
        kotlin_features = _extract_array(self.kotlin_src, "FEATURE_ORDER")
        self.assertEqual(kotlin_features[0], "face_confidence")

    def test_last_feature_is_device_integrity(self):
        kotlin_features = _extract_array(self.kotlin_src, "FEATURE_ORDER")
        self.assertEqual(kotlin_features[-1], "device_integrity")


# Validate the Python side too: that every feature is present, no extra.
class PythonSchemaSelfTests(unittest.TestCase):

    def test_python_feature_order_length(self):
        self.assertEqual(len(FEATURE_ORDER), 28)

    def test_python_aux_columns(self):
        for c in ("subject_id", "session_id", "decision",
                  "model_version", "protocol_version",
                  "schema_version", "split"):
            self.assertIn(c, AUX_COLUMNS)

    def test_python_first_and_last(self):
        self.assertEqual(FEATURE_ORDER[0], "face_confidence")
        self.assertEqual(FEATURE_ORDER[-1], "device_integrity")


if __name__ == "__main__":
    unittest.main(verbosity=2)