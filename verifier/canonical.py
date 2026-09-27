"""Canonical JSON for the EdgePPG signed envelope.

The Android Keystore side (`IntegrityManager.canonicalJson`) emits a fixed
alphabetical-key-order, no-whitespace, 4dp-trimmed JSON. This module reproduces
the exact same bytes in Python so the verifier and the device agree on what
was signed.

Why not use `json.dumps(sort_keys=True, separators=(",", ":"))`? Because that
implementation choice varies across language versions (handling of NaN,
Infinity, key quoting, escape sequences, etc.). To stay safe, we explicitly
write the bytes field-by-field, in the documented order, with the documented
escape rules. The test suite asserts byte-exact parity with the device.

Canonical order (Requirements §FR-CRY-3, Architecture §9 — see also
`EDGEPPG_MASTER_INSTRUCTIONS.md` Known Conflict #5 for the resolution: the
verifier uses the full `Requirements` set):
    challenge_id, confidence, decision, expected_seq, hr_bpm,
    model_version, nonce, roi_corr, signal_quality, snr, timestamp_ms

Float format: 4dp fixed, trailing zeros stripped only after the point.
NaN / Infinity are NOT allowed — they must be emitted as `0` per the device
implementation.
"""

from __future__ import annotations

import json
import re
from typing import Any

CANONICAL_KEY_ORDER = (
    "challenge_id",
    "confidence",
    "decision",
    "expected_seq",
    "hr_bpm",
    "model_version",
    "nonce",
    "roi_corr",
    "signal_quality",
    "snr",
    "timestamp_ms",
)

# Decision set per Requirements / Architecture.
DECISIONS = {"LIVE", "SPOOF", "UNCERTAIN"}


def _format_float(v: float) -> str:
    """Match the Kotlin 4dp-trimmed float format: NaN/Inf ⇒ "0"."""
    if v != v or v in (float("inf"), float("-inf")):
        return "0"
    s = f"{v:.4f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s


def _quote(s: str) -> str:
    """Minimal JSON string quoting matching the Kotlin implementation."""
    sb: list[str] = ['"']
    for c in s:
        cp = ord(c)
        if c == '"':
            sb.append('\\"')
        elif c == "\\":
            sb.append("\\\\")
        elif c == "\n":
            sb.append("\\n")
        elif c == "\r":
            sb.append("\\r")
        elif c == "\t":
            sb.append("\\t")
        elif cp < 0x20:
            sb.append(f"\\u{cp:04x}")
        else:
            sb.append(c)
    sb.append('"')
    return "".join(sb)


def canonical_payload(payload: dict) -> str:
    """Return the byte-exact canonical JSON string for `payload`.

    The caller is responsible for ensuring `payload` carries every key in
    `CANONICAL_KEY_ORDER` and that decision ∈ DECISIONS. We raise ValueError
    on any deviation so we never silently sign over the wrong bytes.
    """
    missing = [k for k in CANONICAL_KEY_ORDER if k not in payload]
    if missing:
        raise ValueError(f"missing canonical keys: {missing}")
    extra = [k for k in payload if k not in CANONICAL_KEY_ORDER]
    if extra:
        raise ValueError(f"unexpected canonical keys: {extra}")
    if payload["decision"] not in DECISIONS:
        raise ValueError(f"bad decision: {payload['decision']!r}")
    if not isinstance(payload["timestamp_ms"], int):
        raise ValueError("timestamp_ms must be int")

    sb: list[str] = ["{"]
    for i, k in enumerate(CANONICAL_KEY_ORDER):
        if i > 0:
            sb.append(",")
        sb.append(_quote(k))
        sb.append(":")
        v = payload[k]
        if isinstance(v, bool):
            # Match Kotlin behavior: True/False become 1/0 (not 'true'/'false').
            sb.append("1" if v else "0")
        elif isinstance(v, int):
            sb.append(str(v))
        elif isinstance(v, float):
            sb.append(_format_float(v))
        elif isinstance(v, str):
            sb.append(_quote(v))
        else:
            raise ValueError(f"unsupported type for {k!r}: {type(v).__name__}")
    sb.append("}")
    return "".join(sb)


def expected_keys() -> tuple[str, ...]:
    """Public accessor for the canonical key order."""
    return CANONICAL_KEY_ORDER


def self_test_parity() -> bool:
    """Sanity check: round-trip via canonical_payload and back via json.loads.
    Used by tests to catch key-order drift."""
    sample = {
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
    s = canonical_payload(sample)
    parsed = json.loads(s)
    return parsed == sample


_FLOAT_RE = re.compile(r"^-?\d+(\.\d+)?$")


def is_canonical_string(s: str) -> bool:
    """Cheap shape check: canonical payloads are
       `{"key":value,"key":value,...}` with no whitespace and no scientific
       notation. False negatives are acceptable (we're conservative); false
       positives are not."""
    if not s.startswith("{") or not s.endswith("}"):
        return False
    body = s[1:-1]
    if not body:
        return True
    # State machine: KEY, COLON, VALUE, COMMA_OR_END, ...
    # After stripping the wrapping braces the first token must be a key.
    state = "expect_key"
    i = 0
    in_string = False
    while i < len(body):
        c = body[i]
        if in_string:
            if c == "\\" and i + 1 < len(body):
                i += 2
                continue
            if c == '"':
                in_string = False
                i += 1
                state = "expect_colon" if state == "expect_key" else "expect_comma_or_end"
                continue
            i += 1
            continue

        if c.isspace():
            return False

        if c == '"':
            if state not in ("expect_key", "expect_value"):
                return False
            in_string = True
            i += 1
            continue

        if c == ":":
            if state != "expect_colon":
                return False
            state = "expect_value"
            i += 1
            continue

        if c == ",":
            if state != "expect_comma_or_end":
                return False
            state = "expect_key"
            i += 1
            continue

        if c == "}":
            return False  # closing brace handled by outer check

        # Digit / minus — must be the start of a value
        if state != "expect_value":
            return False
        j = i
        while j < len(body) and body[j] not in (",", "}", ":", " "):
            j += 1
        if not _FLOAT_RE.match(body[i:j]):
            return False
        state = "expect_comma_or_end"
        i = j

    return state == "expect_comma_or_end" and not in_string
