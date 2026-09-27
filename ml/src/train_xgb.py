"""EdgePPG XGBoost challenger (PC-side, training-only).

Same contract as `train_rf.py`. Used to compare against the Random Forest
baseline before selecting the frozen model.

Until real data is collected, this script:
  * builds the same synthetic fixture
  * trains an XGBoost classifier on it
  * writes the artifact under a different filename so the RF baseline isn't
    overwritten
  * emits a manifest with status `UNTRAINED_NO_REAL_DATA`

The frozen model selection happens in `freeze_model.py` once a real
validation set is available. Until then, both artifacts are kept.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

from ml.src.feature_schema import FEATURE_ORDER, SCHEMA_VERSION
from ml.src.dataset import (
    REPO_ROOT,
    dataset_fingerprint,
    make_synthetic_fixture,
    split_dataset_csv,
)
from ml.src.calibration import PlattScaler, default_thresholds
from ml.src.train_rf import _rows_to_Xy


def train_xgboost(dataset: Dataset,
                  n_estimators: int = 300,
                  seed: int = 7) -> dict:
    """Train an XGBoost binary classifier on (X, y)."""
    try:
        import xgboost as xgb
    except ImportError as e:
        raise RuntimeError(
            "xgboost is not installed in the active environment"
        ) from e
    from sklearn.metrics import roc_auc_score

    X, y = _rows_to_Xy(dataset.rows)
    clf = xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=4,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=seed,
        tree_method="hist",
    )
    clf.fit(X, y)
    raw_proba = clf.predict_proba(X)[:, 1].tolist()
    auc = roc_auc_score(y, raw_proba) if len(set(y)) > 1 else float("nan")
    scaler = PlattScaler()
    scaler.fit(raw_proba, y)
    return {
        "clf": clf,
        "scaler": scaler,
        "train_auc": float(auc),
        "n_estimators": n_estimators,
        "seed": seed,
        "n_features": len(FEATURE_ORDER),
        "n_train_rows": len(X),
    }


def write_artifact(out_dir: Path, train_result: dict, dataset: Dataset,
                   split_paths: dict, status: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "edgeppg_xgb_v1.joblib"
    manifest_path = out_dir / "edgeppg_xgb_v1.manifest.json"

    joblib.dump({
        "clf": train_result["clf"],
        "scaler": train_result["scaler"],
        "feature_names": list(FEATURE_ORDER),
        "schema_version": SCHEMA_VERSION,
        "model_type": "XGBClassifier",
    }, artifact_path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_names": list(FEATURE_ORDER),
        "model_type": "XGBClassifier",
        "n_estimators": train_result["n_estimators"],
        "seed": train_result["seed"],
        "n_features": train_result["n_features"],
        "n_train_rows": train_result["n_train_rows"],
        "train_auc": train_result["train_auc"],
        "scaler": train_result["scaler"].to_dict(),
        "thresholds": default_thresholds(SCHEMA_VERSION).as_dict(),
        "dataset_fingerprint_sha256": dataset_fingerprint(dataset),
        "n_subjects": len(set(dataset.subject_ids)),
        "split_files": {k: str(v) for k, v in split_paths.items()},
        "status": status,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"artifact": str(artifact_path), "manifest": str(manifest_path)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=REPO_ROOT / "models")
    p.add_argument("--n-subjects", type=int, default=8)
    p.add_argument("--sessions-per-subject", type=int, default=6)
    args = p.parse_args()

    dataset = make_synthetic_fixture(
        n_subjects=args.n_subjects,
        sessions_per_subject=args.sessions_per_subject,
    )
    split_paths = split_dataset_csv(dataset, REPO_ROOT / "data" / "splits")
    status = "UNTRAINED_NO_REAL_DATA — synthetic fixture only."
    result = train_xgboost(dataset)
    paths = write_artifact(args.out, result, dataset, split_paths, status)
    print(json.dumps({
        "wrote": paths,
        "n_train_rows": result["n_train_rows"],
        "train_auc": result["train_auc"],
        "status": status,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
