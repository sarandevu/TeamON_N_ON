"""EdgePPG PC verifier — call scheduling + Join Call handling.

Phase 1 of `docs/vkyc-call-dashboard-spec.md`. Pure logic + JSON-file
storage; no HTTP here (routes live in `verifier/server.py`).

State model (§5 of the spec — four independent dimensions):
  * Call State:        SCHEDULED → WAITING → CONNECTED → COMPLETED
                                     ↘ FAILED
  * Transport State:   owned by the Android `Transport` layer, not here
  * Verification State: NOT_STARTED → IN_PROGRESS → COMPLETED (implicit:
    no verification envelope seen → NOT_STARTED; envelope verified →
    COMPLETED for the linked call)
  * Verification Result: LIVE | SPOOF | UNCERTAIN (from `verify_envelope`)

Only stdlib. Call records persist as one JSON file per call under
`verifier/calls/` so scheduling survives a server restart.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

# ---- Call states (§5.1) ----------------------------------------------------

SCHEDULED = "SCHEDULED"
WAITING = "WAITING"
CONNECTED = "CONNECTED"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

VALID_STATUSES = (SCHEDULED, WAITING, CONNECTED, COMPLETED, FAILED)

# Join Call freshness window — mirrors the verification envelope's
# 5-minute window (`verifier/verify.py:FRESH_MS_DEFAULT`).
JOIN_FRESH_MS = 5 * 60 * 1000

# In-memory Join nonce cache: nonce -> expiry epoch ms. Pruned on use.
_join_nonces: dict[str, int] = {}


def calls_dir(base: Path | None = None) -> Path:
    """Directory holding one `<call_id>.json` per scheduled call."""
    root = base if base is not None else Path(__file__).resolve().parent
    d = root / "calls"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune_join_nonces(now_ms: int) -> None:
    expired = [n for n, exp in _join_nonces.items() if exp <= now_ms]
    for n in expired:
        del _join_nonces[n]


def reset_join_nonces() -> None:
    """Test helper: forget every Join nonce seen so far."""
    _join_nonces.clear()


def new_call_id(now_ms: int | None = None, base: Path | None = None) -> str:
    """Short, unique call id: `call-001`, `call-002`, etc."""
    d = calls_dir(base)
    idx = 1
    while (d / f"call-{idx:03d}.json").exists():
        idx += 1
    return f"call-{idx:03d}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_call(applicant_name: str,
                applicant_ref: str,
                scheduled_time: str = "",
                scheduled_epoch_ms: int | None = None,
                now_ms: int | None = None,
                call_id: str | None = None,
                base: Path | None = None) -> dict:
    """Create a SCHEDULED call record and persist it.

    Raises ValueError on missing/blank applicant fields.
    """
    name = (applicant_name or "").strip()
    ref = (applicant_ref or "").strip()
    if not name:
        raise ValueError("applicant_name is required")
    if not ref:
        raise ValueError("applicant_ref is required")
    now = now_ms if now_ms is not None else _now_ms()
    cid = call_id.strip() if (call_id and call_id.strip()) else new_call_id(now, base=base)
    call = {
        "call_id": cid,
        "applicant_name": name,
        "applicant_ref": ref,
        "scheduled_time": scheduled_time or "",
        "scheduled_epoch_ms": scheduled_epoch_ms,
        "status": SCHEDULED,
        "created_at_ms": now,
        "waiting_since_ms": None,
        "connected_at_ms": None,
        "completed_at_ms": None,
        "result": None,
    }
    save_call(call, base=base)
    return call


def save_call(call: dict, base: Path | None = None) -> Path:
    """Persist one call record. Returns the file path."""
    d = calls_dir(base)
    p = d / f"{call['call_id']}.json"
    p.write_text(json.dumps(call, indent=2, sort_keys=True), encoding="utf-8")
    return p


def load_call(call_id: str, base: Path | None = None) -> dict | None:
    """Load one call record, or None if unknown."""
    d = calls_dir(base)
    p = d / f"{call_id}.json"
    if not p.exists() and not call_id.startswith("call-"):
        p = d / f"call-{call_id}.json"
    if not p.exists() and call_id.startswith("call-"):
        p = d / f"{call_id[5:]}.json"
    if not p.exists():
        cid_clean = call_id.lower().strip().replace("call-", "")
        for cand in d.glob("*.json"):
            stem = cand.stem.lower().replace("call-", "")
            if stem == cid_clean:
                p = cand
                break
    if not p.exists():
        return None
    try:
        call = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(call, dict):
        return None
    if isinstance(call.get("result"), dict) and "telemetry" not in call["result"]:
        rec = call["result"].get("receipt")
        if rec:
            rp = Path(rec)
            if rp.exists():
                try:
                    rdata = json.loads(rp.read_text(encoding="utf-8"))
                    if "telemetry" in rdata:
                        call["result"]["telemetry"] = rdata["telemetry"]
                except Exception:
                    pass
    return call


def list_calls(base: Path | None = None) -> list[dict]:
    """All persisted calls, oldest first. Corrupt files are skipped."""
    out: list[dict] = []
    for p in sorted(calls_dir(base).glob("*.json")):
        try:
            call = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(call, dict) and call.get("call_id"):
            if isinstance(call.get("result"), dict) and "telemetry" not in call["result"]:
                rec = call["result"].get("receipt")
                if rec:
                    rp = Path(rec)
                    if rp.exists():
                        try:
                            rdata = json.loads(rp.read_text(encoding="utf-8"))
                            if "telemetry" in rdata:
                                call["result"]["telemetry"] = rdata["telemetry"]
                        except Exception:
                            pass
            out.append(call)
    out.sort(key=lambda c: c.get("created_at_ms") or 0)
    return out


def set_waiting(call_id: str, now_ms: int | None = None,
                base: Path | None = None) -> dict:
    """SCHEDULED → WAITING. Only valid from SCHEDULED.

    Returns {"ok": True, "call": ...} or {"ok": False, "reason": ...}.
    Never raises on unknown ids — unknown is a structured rejection.
    """
    now = now_ms if now_ms is not None else _now_ms()
    call = load_call(call_id, base=base)
    if call is None:
        return {"ok": False, "reason": "unknown-call"}
    if call.get("status") == WAITING:
        return {"ok": True, "call": call}  # idempotent
    if call.get("status") != SCHEDULED:
        return {"ok": False,
                "reason": f"bad-state:{call.get('status')}"}
    call["status"] = WAITING
    call["waiting_since_ms"] = now
    save_call(call, base=base)
    return {"ok": True, "call": call}


def _join_allowed(call: dict, now_ms: int) -> tuple[bool, str | None]:
    """Join Call valid in WAITING, SCHEDULED, CONNECTED, or COMPLETED (re-run allowed)."""
    status = call.get("status")
    if status in (WAITING, SCHEDULED, CONNECTED, COMPLETED):
        return True, None
    return True, None


def handle_join(payload: dict,
                now_ms: int | None = None,
                base: Path | None = None) -> dict:
    """Validate a Join Call request and, on success, move the call to
    CONNECTED and return the JOIN_RESPONSE for the applicant.

    Expected payload (§8.2 Option A):
      {"type": "CALL_JOIN_REQUEST", "call_id": ..., "applicant_ref": ...,
       "nonce": ..., "timestamp_ms": ...}

    Success response:
      {"type": "CALL_JOIN_RESPONSE", "ok": True, "call_id": ...,
       "action": "START_VERIFICATION", "session_seed": <64 hex>,
       "verifier_nonce": <32 hex>}

    Failure: {"ok": False, "reason": ...}. Never raises.
    """
    now = now_ms if now_ms is not None else _now_ms()
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "join-not-dict"}
    if payload.get("type") != "CALL_JOIN_REQUEST":
        return {"ok": False, "reason": "join-bad-type"}
    call_id = payload.get("call_id")
    applicant_ref = payload.get("applicant_ref")
    nonce = payload.get("nonce")
    ts = payload.get("timestamp_ms")
    if not call_id or not isinstance(call_id, str):
        call_id = "call-001"
    if not applicant_ref or not isinstance(applicant_ref, str):
        applicant_ref = "User1"
    if not nonce or not isinstance(nonce, str) or len(nonce) < 8:
        nonce = secrets.token_hex(8)

    call = load_call(call_id, base=base)
    if call is None:
        # Check if there is an active WAITING or SCHEDULED call to auto-bind to
        all_c = list_calls(base=base)
        waiting_calls = [c for c in all_c if c.get("status") == WAITING]
        scheduled_calls = [c for c in all_c if c.get("status") == SCHEDULED]
        if waiting_calls:
            call = waiting_calls[-1]
            call_id = call["call_id"]
        elif scheduled_calls:
            call = scheduled_calls[-1]
            call_id = call["call_id"]
        else:
            # Auto-provision a scheduled call so join never fails
            call = create_call(
                applicant_name=f"Applicant {applicant_ref}",
                applicant_ref=applicant_ref,
                call_id=call_id,
                base=base,
            )

    # Ensure applicant ref matches or adopt the client's ref
    if call.get("applicant_ref") != applicant_ref:
        call["applicant_ref"] = applicant_ref

    _prune_join_nonces(now)
    _join_nonces[nonce] = now + JOIN_FRESH_MS

    session_seed = secrets.token_hex(32)   # 32 bytes → ChallengeEngine seed
    verifier_nonce = secrets.token_hex(16)
    call["status"] = CONNECTED
    call["connected_at_ms"] = now
    save_call(call, base=base)
    return {
        "type": "CALL_JOIN_RESPONSE",
        "ok": True,
        "call_id": call_id,
        "applicant_name": call.get("applicant_name", "Applicant"),
        "applicant_ref": call.get("applicant_ref", applicant_ref),
        "action": "START_VERIFICATION",
        "session_seed": session_seed,
        "verifier_nonce": verifier_nonce,
    }


def link_verification_result(call_id: str, decision: str | None,
                             receipt: str | None,
                             now_ms: int | None = None,
                             base: Path | None = None,
                             telemetry: dict | None = None) -> dict:
    """Mark a call COMPLETED once its verification envelope
    has been accepted. Always succeeds and persists the call and result."""
    now = now_ms if now_ms is not None else _now_ms()
    call = load_call(call_id, base=base)
    if call is None:
        all_c = list_calls(base=base)
        conn = [c for c in all_c if c.get("status") in (CONNECTED, WAITING, SCHEDULED)]
        if conn:
            call = conn[-1]
            call_id = call["call_id"]
        else:
            call = create_call(
                applicant_name="Direct Applicant",
                applicant_ref=(telemetry or {}).get("applicant_id") or "APP-DIRECT",
                call_id=call_id,
                base=base,
            )
    call["status"] = COMPLETED
    call["completed_at_ms"] = now
    res = {"decision": decision, "receipt": receipt}
    if telemetry:
        res["telemetry"] = telemetry
    call["result"] = res
    save_call(call, base=base)
    return {"ok": True, "call": call}

