"""EdgePPG baseline PC verifier.

Pure-Python ECDSA P-256 / SHA256 verifier over the canonical envelope
emitted by the Android Keystore side.

Verification steps (in order):
  1. Envelope shape check (`{data: str, sig: str, alg: str, keyAlias: str}`)
  2. `alg == "SHA256withECDSA"` check
  3. Canonical payload must parse and contain every required field
  4. `decision ∈ {LIVE, SPOOF, UNCERTAIN}` check
  5. Freshness: `|now - timestamp_ms| <= FRESH_MS` (default 5 minutes)
  6. Nonce not previously seen (LRU cache; pruned on each call)
  7. ECDSA signature verifies against the provisioned public key over the
     **byte-exact** canonical `data` string

No LLM, no cloud, no Office Kit. The verifier is intentionally minimal and
audit-friendly.
"""

from __future__ import annotations

import base64
import json
import time
from collections import OrderedDict
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
)

from verifier.canonical import (
    DECISIONS,
    canonical_payload,
    expected_keys,
)

FRESH_MS_DEFAULT = 5 * 60 * 1000  # 5 minutes

# Cache: nonce -> expiry epoch ms.
_NONCE_CACHE: "OrderedDict[str, int]" = OrderedDict()
_NONCE_CACHE_MAX = 1024


def _prune_nonces(now_ms: int) -> None:
    """Drop nonces whose freshness window has expired."""
    while _NONCE_CACHE:
        n, exp = next(iter(_NONCE_CACHE.items()))
        if exp <= now_ms:
            _NONCE_CACHE.pop(n, None)
        else:
            return


def _load_pubkey(pubkey_b64_or_pem: str):
    """Load a public key from Base64-DER or PEM, returning an
    `EllipticCurvePublicKey` instance."""
    s = (pubkey_b64_or_pem or "").strip()
    if not s:
        raise ValueError("empty public key")
    if "BEGIN PUBLIC KEY" in s:
        return serialization.load_pem_public_key(s.encode("ascii"))
    der = base64.b64decode(s.replace("\n", "").replace(" ", ""))
    return serialization.load_der_public_key(der)


def verify_envelope(envelope: dict,
                    pubkey_b64_or_pem: str,
                    now_ms: Optional[int] = None) -> dict:
    """Verify an EdgePPG envelope.

    Returns a dict with at minimum:
      * `ok: bool`
      * `reason: str | None` (None when ok)
      * `telemetry: dict | None` (the parsed canonical payload when ok)
      * `telemetry_sha256: str` (for the audit log)
    Never raises; all error paths return a structured `ok=False` dict.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    # 1. shape
    if not isinstance(envelope, dict):
        return {"ok": False, "reason": "envelope-not-dict"}
    data = envelope.get("data")
    sig_b64 = envelope.get("sig")
    alg = envelope.get("alg", "SHA256withECDSA")
    if not isinstance(data, str) or not isinstance(sig_b64, str):
        return {"ok": False, "reason": "envelope-shape"}

    if alg != "SHA256withECDSA":
        return {"ok": False, "reason": f"unsupported-alg:{alg}"}

    # 2. canonical payload must parse
    try:
        telemetry = json.loads(data)
    except Exception:
        return {"ok": False, "reason": "data-not-json"}

    # 3. required fields present
    expected = set(expected_keys())
    have = set(telemetry)
    if have != expected:
        missing = sorted(expected - have)
        extra = sorted(have - expected)
        if missing:
            return {"ok": False, "reason": f"missing-field:{missing[0]}"}
        return {"ok": False, "reason": f"extra-field:{extra[0]}"}

    # 4. decision
    decision = telemetry.get("decision")
    if decision not in DECISIONS:
        return {"ok": False, "reason": f"bad-decision:{decision!r}"}

    # 5. freshness
    ts = telemetry.get("timestamp_ms")
    if not isinstance(ts, int):
        return {"ok": False, "reason": "timestamp-not-int"}
    if abs(now_ms - ts) > FRESH_MS_DEFAULT:
        return {"ok": False, "reason": "stale-timestamp"}

    # 6. nonce
    nonce = telemetry.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 8:
        return {"ok": False, "reason": "bad-nonce"}
    _prune_nonces(now_ms)
    if nonce in _NONCE_CACHE:
        return {"ok": False, "reason": "replay-nonce"}

    # 7. signature
    try:
        pubkey = _load_pubkey(pubkey_b64_or_pem)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"bad-pubkey:{type(e).__name__}"}

    try:
        sig_der = base64.b64decode(sig_b64)
    except Exception:
        return {"ok": False, "reason": "bad-sig-encoding"}

    try:
        pubkey.verify(
            sig_der,
            data.encode("utf-8"),
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        return {"ok": False, "reason": "bad-signature"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"verify-error:{type(e).__name__}"}

    # All gates passed — record the nonce and return.
    _NONCE_CACHE[nonce] = now_ms + FRESH_MS_DEFAULT
    while len(_NONCE_CACHE) > _NONCE_CACHE_MAX:
        _NONCE_CACHE.popitem(last=False)

    # SHA-256 of the canonical bytes for audit.
    import hashlib
    sha256 = hashlib.sha256(data.encode("utf-8")).hexdigest()

    return {
        "ok": True,
        "reason": None,
        "telemetry": telemetry,
        "telemetry_sha256": sha256,
        "decision": decision,
    }


def reset_nonce_cache() -> None:
    """Test helper: forget every nonce we've seen. Production code never
    calls this; it's exposed so unit tests can re-use the same nonce."""
    _NONCE_CACHE.clear()


def canonical_envelope(payload: dict) -> dict:
    """Build a verifiable envelope around a canonical payload. Returns
    `{data, sig, alg, keyAlias}` with `sig` left empty — caller signs
    externally. Useful for round-trip tests where we want to verify that
    Python's canonical_payload matches what the device would have written."""
    return {
        "data": canonical_payload(payload),
        "sig": "",
        "alg": "SHA256withECDSA",
        "keyAlias": "edgeppg_device_key_v2",
    }
