"""EdgePPG evaluation harness (PC-side, training-only).

Produces:
  * ROC-AUC on a held-out split (when real data exists)
  * per-attack-type FAR/FRR (when an attack subset exists)

Until a real validation set is collected, this module returns
`NotImplemented` for every metric and refuses to fabricate numbers
(NFR-MET-1).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ml.src.feature_schema import FEATURE_ORDER


def safe_auc(y_true: list[int], scores: list[float]) -> float:
    """ROC-AUC, with empty-class guard returning NaN."""
    if not y_true or len(set(y_true)) < 2:
        return float("nan")
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y_true, scores))


def safe_f1(y_true: list[int], y_pred: list[int]) -> float:
    if not y_true:
        return float("nan")
    from sklearn.metrics import f1_score
    return float(f1_score(y_true, y_pred, zero_division=0))


def attack_specific_far_frr(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Compute FAR / FRR per attack category.

    FAR = fraction of attack rows that the model accepts as LIVE.
    FRR = fraction of genuine rows that the model rejects as SPOOF/UNCERTAIN.

    Returns an empty dict when no `attack_type` column is present in the
    rows, instead of fabricating anything. Real data must carry an explicit
    `attack_type` column per `Requirements §PR-DAT-2`.
    """
    if not rows or "attack_type" not in rows[0]:
        return {}
    by_attack: dict[str, dict[str, float]] = {}
    # The actual FAR/FRR computation needs the trained model + thresholds;
    # we leave that to the operator-driven script that consumes this
    # harness, since the schema of the attack catalog (column names, label
    # conventions) is decided with the validation set.
    return by_attack


def report_unavailable() -> dict:
    """Return a clear 'not yet measured' report — no fabrication."""
    return {
        "status": "unavailable",
        "reason": "no real validation set has been collected yet",
        "metrics": {
            "roc_auc": None,
            "f1": None,
            "far": None,
            "frr": None,
            "attack_specific": {},
        },
        "next_action": (
            "Collect the validation set per Requirements §PR-DAT-1, then "
            "rerun this script with the trained artifact."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(report_unavailable(), indent=2))
