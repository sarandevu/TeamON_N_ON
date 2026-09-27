"""EdgePPG verifier tests (stdlib unittest).

Run with:
    .venv\\Scripts\\python.exe -m verifier.tests.run_tests

Tests cover:
  * canonical JSON parity (byte-exact match between Python and the documented
    device-side shape)
  * full round-trip: device-generated envelope → verifier accepts
  * tampered bytes → verifier rejects
  * replay nonce → verifier rejects on the second attempt
  * expired timestamp → verifier rejects
  * missing field / extra field → verifier rejects
  * bad-decision → verifier rejects
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from verifier.canonical import (  # noqa: E402
    CANONICAL_KEY_ORDER,
    canonical_payload,
    expected_keys,
    is_canonical_string,
    self_test_parity,
)
from verifier.verify import (  # noqa: E402
    FRESH_MS_DEFAULT,
    reset_nonce_cache,
    verify_envelope,
)
from verifier.receipt import write_receipt  # noqa: E402


def _make_keypair():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    sk = ec.generate_private_key(ec.SECP256R1())
    pk = sk.public_key()
    pem = pk.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return sk, pem.decode("ascii")


def _sample_payload(now_ms: int, **overrides) -> dict:
    p = {
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
        "timestamp_ms": now_ms,
    }
    p.update(overrides)
    return p


def _sign(sk, data: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    sig = sk.sign(data.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode("ascii")


def _envelope(payload, sk) -> dict:
    data = canonical_payload(payload)
    sig_b64 = _sign(sk, data)
    return {
        "data": data,
        "sig": sig_b64,
        "alg": "SHA256withECDSA",
        "keyAlias": "edgeppg_device_key_v2",
    }


def _assert_raises(callable_, exc_type):
    try:
        callable_()
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(e).__name__}: {e}"
        )
    raise AssertionError(f"expected {exc_type.__name__}, no exception raised")


class CanonicalTests(unittest.TestCase):

    def test_key_order_matches_requirements(self):
        self.assertEqual(CANONICAL_KEY_ORDER[0], "challenge_id")
        self.assertEqual(CANONICAL_KEY_ORDER[-1], "timestamp_ms")
        self.assertEqual(len(CANONICAL_KEY_ORDER), 11)

    def test_self_test_parity(self):
        self.assertTrue(self_test_parity())

    def test_canonical_payload_byte_exact(self):
        """The canonical string must be byte-stable — exact deterministic
        output that the Android side and Python side both produce."""
        p = _sample_payload(1700000000000)
        s = canonical_payload(p)
        # Decision is quoted; numbers are bare; no whitespace.
        self.assertIn('"decision":"LIVE"', s)
        self.assertIn('"timestamp_ms":1700000000000', s)
        self.assertIn('"confidence":0.94', s)
        self.assertNotIn(" ", s)

    def test_canonical_payload_float_format(self):
        """0.9400 must become 0.94, not 0.94 vs 0.9400 (4dp trailing stripped)."""
        p = _sample_payload(1700000000000, confidence=0.94)
        s = canonical_payload(p)
        self.assertIn('"confidence":0.94', s)
        self.assertNotIn("0.9400", s)

    def test_canonical_payload_quotes_escape(self):
        p = _sample_payload(1700000000000,
                            expected_seq='[{"d":25,"t":250,"c":0,"x":"\\"}]')
        s = canonical_payload(p)
        # JSON-parses back to the original
        self.assertEqual(json.loads(s)["expected_seq"],
                         '[{"d":25,"t":250,"c":0,"x":"\\"}]')

    def test_canonical_payload_rejects_missing_key(self):
        p = _sample_payload(1700000000000)
        del p["timestamp_ms"]
        _assert_raises(lambda: canonical_payload(p), ValueError)

    def test_canonical_payload_rejects_extra_key(self):
        p = _sample_payload(1700000000000, extra_field=1)
        _assert_raises(lambda: canonical_payload(p), ValueError)

    def test_canonical_payload_rejects_bad_decision(self):
        p = _sample_payload(1700000000000, decision="MAYBE")
        _assert_raises(lambda: canonical_payload(p), ValueError)

    def test_canonical_payload_rejects_non_int_timestamp(self):
        p = _sample_payload(1700000000000)
        p["timestamp_ms"] = 1700000000000.5
        _assert_raises(lambda: canonical_payload(p), ValueError)

    def test_canonical_payload_nan_becomes_zero(self):
        p = _sample_payload(1700000000000, confidence=float("nan"))
        s = canonical_payload(p)
        self.assertIn('"confidence":0', s)


class IsCanonicalStringTests(unittest.TestCase):

    def test_accepts_known_canonical(self):
        s = canonical_payload(_sample_payload(1700000000000))
        self.assertTrue(is_canonical_string(s))

    def test_rejects_with_whitespace(self):
        s = canonical_payload(_sample_payload(1700000000000))
        self.assertFalse(is_canonical_string(s.replace(':', ': ')))

    def test_rejects_with_scientific_notation(self):
        self.assertFalse(is_canonical_string(
            '{"x":1e10}'))


class VerifyTests(unittest.TestCase):

    def setUp(self):
        self.sk, self.pem = _make_keypair()
        self.now_ms = int(time.time() * 1000)
        reset_nonce_cache()

    def _good(self, **overrides) -> dict:
        return _envelope(_sample_payload(self.now_ms, **overrides), self.sk)

    def test_round_trip_ok(self):
        env = self._good()
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["decision"], "LIVE")
        self.assertIn("telemetry", verdict)
        self.assertIn("telemetry_sha256", verdict)

    def test_tampered_bytes_rejected(self):
        env = self._good()
        # Flip one byte of the signed data. We pick a position inside a
        # number to guarantee the change is detectable by ECDSA without
        # also triggering a structural error path.
        d = env["data"]
        idx = d.find('"snr":')
        # change "0.42" → "0.43" (digits only)
        flipped = d.replace('"snr":0.42', '"snr":0.43', 1)
        self.assertNotEqual(d, flipped)
        env["data"] = flipped
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        # Any non-ok reason is acceptable here — the point is that the
        # tampered bytes do not pass.
        self.assertIsNotNone(verdict["reason"])

    def test_tampered_signature_rejected(self):
        env = self._good()
        sig = base64.b64decode(env["sig"])
        flipped = sig[:-1] + bytes([(sig[-1] + 1) % 256])
        env["sig"] = base64.b64encode(flipped).decode("ascii")
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        # Base64 of a single-byte mutation could yield a malformed DER —
        # either bad-signature or bad-sig-encoding is acceptable.
        self.assertIn(verdict["reason"], ("bad-signature", "bad-sig-encoding"))

    def test_replay_nonce_rejected(self):
        env = self._good()
        first = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertTrue(first["ok"])
        second = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(second["ok"])
        self.assertEqual(second["reason"], "replay-nonce")

    def test_expired_timestamp_rejected(self):
        old = self.now_ms - (FRESH_MS_DEFAULT + 60_000)
        env = self._good(timestamp_ms=old)
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "stale-timestamp")

    def test_missing_field_rejected(self):
        # Build a valid envelope, then mutate the canonical bytes to drop
        # a key. The signature won't match the mutated bytes, so the
        # verifier should reject — either because the signature doesn't
        # verify (bad-signature) or because the missing-field check fires
        # after a JSON parse recovers the missing entry.
        env = self._good()
        d = env["data"]
        # Drop the ",snr:..." segment by surgical replacement.
        bad = d.replace(',"snr":0.42', "")
        self.assertNotEqual(d, bad)
        env["data"] = bad
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        # The ECDSA verifies against the original `d`; once we mutate,
        # the signature fails. Either reason is acceptable.
        self.assertIsNotNone(verdict["reason"])

    def test_extra_field_rejected(self):
        # Build an envelope and append an extra key after the closing brace.
        d = canonical_payload(_sample_payload(self.now_ms))
        bad = d[:-1] + ',"extra":"x"}'
        env = {
            "data": bad,
            "sig": _sign(self.sk, bad),
            "alg": "SHA256withECDSA",
            "keyAlias": "edgeppg_device_key_v2",
        }
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        self.assertIsNotNone(verdict["reason"])

    def test_bad_decision_rejected(self):
        # Sign over a payload with decision=MAYBE — the canonical_payload
        # validator forbids this, so we hand-craft the canonical string.
        payload = _sample_payload(self.now_ms, decision="MAYBE")
        # Manually build a canonical string with the bad decision so we
        # can sign over it and test that the verifier rejects.
        from verifier.canonical import CANONICAL_KEY_ORDER
        from verifier.canonical import _quote, _format_float
        parts = []
        for k in CANONICAL_KEY_ORDER:
            v = payload[k]
            if isinstance(v, bool):
                v = "1" if v else "0"
            elif isinstance(v, (int, float)):
                v = str(v) if isinstance(v, int) else _format_float(v)
            else:
                v = _quote(v)
            parts.append(f"{_quote(k)}:{v}")
        bad_data = "{" + ",".join(parts) + "}"
        env = {
            "data": bad_data,
            "sig": _sign(self.sk, bad_data),
            "alg": "SHA256withECDSA",
            "keyAlias": "edgeppg_device_key_v2",
        }
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        self.assertTrue(verdict["reason"].startswith("bad-decision"))

    def test_unsupported_alg_rejected(self):
        env = self._good()
        env["alg"] = "MD5withRSA"
        verdict = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        self.assertIn("unsupported-alg", verdict["reason"])

    def test_bad_pubkey_rejected(self):
        env = self._good()
        verdict = verify_envelope(env, "garbage-not-a-key", now_ms=self.now_ms)
        self.assertFalse(verdict["ok"])
        self.assertIn("bad-pubkey", verdict["reason"])

    def test_envelope_shape_rejected(self):
        for bad in ({}, {"data": "x"}, {"sig": "x"}):
            v = verify_envelope(bad, self.pem, now_ms=self.now_ms)
            self.assertFalse(v["ok"], f"expected reject for {bad}")
            self.assertIn(v["reason"], ("envelope-shape", "data-not-json"))


class ReceiptTests(unittest.TestCase):

    def setUp(self):
        self.sk, self.pem = _make_keypair()
        self.now_ms = int(time.time() * 1000)
        reset_nonce_cache()

    def test_write_receipt_on_ok(self):
        env = _envelope(_sample_payload(self.now_ms), self.sk)
        v = verify_envelope(env, self.pem, now_ms=self.now_ms)
        self.assertTrue(v["ok"])
        path = write_receipt(v)
        self.assertTrue(path.exists())
        body = json.loads(path.read_text())
        self.assertEqual(body["verdict"], "ok")
        self.assertIn("telemetry_sha256", body)
        # Cleanup so we don't litter the receipts/ dir.
        path.unlink()

    def test_write_receipt_refuses_on_failure(self):
        v = {"ok": False, "reason": "x"}
        _assert_raises(lambda: write_receipt(v), ValueError)
