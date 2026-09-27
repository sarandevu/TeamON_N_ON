"""EdgePPG offline receipt writer.

When the verifier accepts an envelope, it writes a small JSON receipt under
`verifier/receipts/<session_id>_<timestamp_ms>.json`. The receipt contains:
  * the canonical telemetry
  * the SHA-256 of the signed bytes
  * the verifier's verdict and reason
  * the verifier's local timestamp

Receipts are offline artifacts — no cloud, no Office Kit.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"


def write_receipt(verdict: dict, out_dir: Optional[Path] = None) -> Path:
    """Write a JSON receipt for a successful verification."""
    if not verdict.get("ok"):
        raise ValueError("write_receipt called on a failed verdict")

    target_dir = out_dir or RECEIPTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    telemetry = verdict["telemetry"]
    session_id = telemetry.get("challenge_id", "unknown")
    ts = telemetry.get("timestamp_ms", int(time.time() * 1000))
    sha = verdict["telemetry_sha256"]
    short_sha = sha[:12]
    fname = f"{session_id}_{ts}_{short_sha}.json"
    path = target_dir / fname

    receipt = {
        "verifier_version": "edgeppg-baseline-1.0",
        "verified_at_ms": int(time.time() * 1000),
        "verdict": "ok",
        "telemetry": telemetry,
        "telemetry_sha256": sha,
        "reason": None,
    }
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path
