"""EdgePPG frozen-model selection (PC-side, training-only).

Once a real validation set exists, this module picks between the RF baseline
and the XGBoost challenger based on held-out ROC-AUC and writes the chosen
artifact to `models/edgeppg_frozen.joblib` plus a manifest.

Until then, this module refuses to make a selection — it returns
`NotImplemented` and points at the synthetic fixture for pipeline
verification only.

Export format choice:
  * Random Forest → joblib (scikit-learn native)
  * XGBoost       → joblib (compatible; future ONNX export gated on TechStack
                              §7: "Export format cannot be decided until the
                              on-device runtime is benchmarked on iQOO 15.")
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib

from ml.src.feature_schema import FEATURE_ORDER, SCHEMA_VERSION
from ml.src.calibration import default_thresholds


def load_artifact(path: Path) -> dict:
    """Load a frozen model artifact produced by `train_rf` or `train_xgb`."""
    return joblib.load(path)


def freeze_for_runtime(out_dir: Path,
                       candidate_paths: dict[str, Path],
                       held_out_metrics: dict[str, dict] | None = None
                       ) -> dict:
    """Pick the best candidate and write it as the runtime artifact.

    `held_out_metrics` is `{model_name: {"roc_auc": float, ...}}`. When None
    or empty, this function refuses to make a selection.
    """
    if not held_out_metrics:
        return {
            "status": "not_frozen",
            "reason": "no held-out metrics available",
            "next_action": (
                "Run ml/src/evaluate.py against a real validation set, "
                "pass the metrics here, then re-run this script."
            ),
        }

    ranked = sorted(
        held_out_metrics.items(),
        key=lambda kv: (kv[1].get("roc_auc") or float("-inf")),
        reverse=True,
    )
    winner_name, winner_metrics = ranked[0]
    auc = winner_metrics.get("roc_auc")
    if auc is None or (isinstance(auc, float) and math.isnan(auc)):
        return {
            "status": "not_frozen",
            "reason": "winner has undefined ROC-AUC",
        }

    winner_path = candidate_paths[winner_name]
    bundle = joblib.load(winner_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "edgeppg_frozen.joblib"
    manifest_path = out_dir / "edgeppg_frozen.manifest.json"
    joblib.dump(bundle, artifact_path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_names": list(FEATURE_ORDER),
        "model_type": bundle.get("model_type"),
        "winner": winner_name,
        "held_out_metrics": held_out_metrics,
        "thresholds": default_thresholds(SCHEMA_VERSION).as_dict(),
        "export_format": "joblib",
        "export_format_note": (
            "ONNX / TFLite export gated on TechStack §7: cannot be decided "
            "until the on-device runtime is benchmarked on iQOO 15."
        ),
        "status": "FROZEN — on real validation data",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": "frozen",
        "artifact": str(artifact_path),
        "manifest": str(manifest_path),
        "winner": winner_name,
        "held_out_metrics": held_out_metrics,
    }


if __name__ == "__main__":
    # No real data ⇒ refuse to select.
    print(json.dumps({
        "status": "not_frozen",
        "reason": "no real validation set collected yet",
    }, indent=2))
