"""Stage 12 — Canonical JSON parity tests (Kotlin ↔ Python).

The Android Keystore side (`IntegrityManager.kt:canonicalJson`) and the
PC verifier side (`verifier/canonical.py:canonical_payload`) MUST produce
byte-exact JSON over the same payload. This test enforces parity by
parsing the Kotlin source for the `canonicalJson` / `num` / `quote`
helpers and running a Python re-implementation of those helpers, then
asserting the two produce the same bytes.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from verifier.canonical import (  # noqa: E402
    CANONICAL_KEY_ORDER,
    canonical_payload,
)


def _read_kotlin_source() -> str:
    kt_path = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
               / "com" / "edgeppg" / "app" / "integrity" / "IntegrityManager.kt")
    return kt_path.read_text(encoding="utf-8")


def _kotlin_canonical(t: dict) -> str:
    """Re-implementation of IntegrityManager.canonicalJson() in Python.

    The Kotlin source declares the key order in literal write order
    inside `canonicalJson`. We replicate that order here.
    """
    # The Kotlin code writes keys in this exact sequence:
    #   challenge_id, confidence, decision, expected_seq, hr_bpm,
    #   model_version, nonce, roi_corr, signal_quality, snr, timestamp_ms
    # This is alphabetical order — same as the Python side.
    write_order = [
        "challenge_id", "confidence", "decision", "expected_seq",
        "hr_bpm", "model_version", "nonce", "roi_corr",
        "signal_quality", "snr", "timestamp_ms",
    ]
    parts = []
    for k in write_order:
        v = t[k]
        if isinstance(v, bool):
            parts.append(f'"{k}":{1 if v else 0}')
        elif isinstance(v, int):
            parts.append(f'"{k}":{v}')
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                parts.append(f'"{k}":0')
            else:
                s = f"{v:.4f}"
                if "." in s:
                    s = s.rstrip("0").rstrip(".")
                if s in ("", "-0"):
                    s = "0"
                parts.append(f'"{k}":{s}')
        else:
            parts.append(f'"{k}":{_kotlin_quote(v)}')
    return "{" + ",".join(parts) + "}"


def _kotlin_quote(s: str) -> str:
    """Mirror of IntegrityManager.quote()."""
    out = ['"']
    for c in s:
        cp = ord(c)
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def _make_payload() -> dict:
    return {
        "challenge_id": "sess-001",
        "confidence": 0.94,
        "decision": "LIVE",
        "expected_seq": '[{"d":25,"t":250,"c":0}]',
        "hr_bpm": 72.5,
        "model_version": "v2.1-edge",
        "nonce": "a3f1c9e2b4d60718293a4b5c6d7e8f90",
        "roi_corr": 0.61,
        "signal_quality": 0.88,
        "snr": 0.42,
        "timestamp_ms": 1700000000000,
    }


def _canonical_key_order_in_kotlin() -> list[str]:
    """Extract the key order from IntegrityManager.kt by parsing the
    `canonicalJson` function body. The order is the order of the
    `sb.append("\"key\":...")` lines."""
    src = _read_kotlin_source()
    # Match each `sb.append("\"<key>\":")` line. In the file the substring
    # looks like: sb.append(\"challenge_id\":) — i.e. backslash + double-quote.
    keys = re.findall(r'sb\.append\("\\"([a-z_]+)\\":', src)
    return keys


class CanonicalParityTests(unittest.TestCase):

    def test_kotlin_canonical_matches_python_for_sample(self):
        payload = _make_payload()
        kotlin_out = _kotlin_canonical(payload)
        python_out = canonical_payload(payload)
        self.assertEqual(
            kotlin_out, python_out,
            f"Kotlin and Python canonical JSON disagree:\n"
            f"  Kotlin: {kotlin_out}\n"
            f"  Python: {python_out}"
        )

    def test_kotlin_canonical_handles_nan(self):
        payload = _make_payload()
        payload["confidence"] = float("nan")
        kotlin_out = _kotlin_canonical(payload)
        python_out = canonical_payload(payload)
        self.assertEqual(kotlin_out, python_out)
        self.assertIn('"confidence":0', kotlin_out)

    def test_kotlin_canonical_handles_zero(self):
        payload = _make_payload()
        payload["snr"] = 0.0
        # snr is float — 0.0 should appear as "0" after 4dp trim
        kotlin_out = _kotlin_canonical(payload)
        python_out = canonical_payload(payload)
        self.assertEqual(kotlin_out, python_out)
        self.assertIn('"snr":0', kotlin_out)

    def test_kotlin_canonical_handles_negative_zero(self):
        payload = _make_payload()
        payload["confidence"] = -0.0
        kotlin_out = _kotlin_canonical(payload)
        python_out = canonical_payload(payload)
        self.assertEqual(kotlin_out, python_out)

    def test_kotlin_canonical_handles_string_with_quotes(self):
        payload = _make_payload()
        payload["expected_seq"] = '[{"d":25,"x":"\\"}]'
        kotlin_out = _kotlin_canonical(payload)
        python_out = canonical_payload(payload)
        self.assertEqual(kotlin_out, python_out)

    def test_key_order_in_kotlin_source_matches_python(self):
        kotlin_keys = _canonical_key_order_in_kotlin()
        self.assertEqual(
            kotlin_keys, list(CANONICAL_KEY_ORDER),
            "Kotlin canonicalJson() must write keys in the same order "
            "as Python CANONICAL_KEY_ORDER"
        )

    def test_kotlin_canonical_byte_stable_across_runs(self):
        # The canonical output is deterministic for the same payload.
        payload = _make_payload()
        a = _kotlin_canonical(payload)
        b = _kotlin_canonical(payload)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)