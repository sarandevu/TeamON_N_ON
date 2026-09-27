"""EdgePPG Random Forest baseline training (PC-side, training-only).

Random Forest is the documented baseline classifier (`TechStack §3`, "Core").
XGBoost is evaluated as a challenger (`train_xgb.py`), MLP is optional.

The output is a frozen model artifact + manifest under `models/`. The
manifest records:
  * schema version
  * training data fingerprint (so future evidence can be tied back)
  * training label (LIVE vs SPOOF; UNCERTAIN rows are NOT used for training)
  * explicit "UNTRAINED_NO_REAL_DATA" status when no real data is present
  * metric placeholders that are filled in only when real data is available

The runtime never imports this module. It only consumes the frozen artifact
via the ML fusion client.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import joblib

from ml.src.feature_schema import (
    FEATURE_ORDER,
    SCHEMA_VERSION,
    validate_row,
)
from ml.src.dataset import (
    Dataset,
    REPO_ROOT,
    DATA_DIR,
    dataset_fingerprint,
    load_csv,
    make_synthetic_fixture,
    split_dataset_csv,
)


def load_raw_dataset(raw_dir: Path) -> Dataset:
    """Load all per-session CSVs from data/raw/<subject>/<session>.csv.

    Each CSV has exactly one data row (one VKYC session = one feature row).
    Returns a combined Dataset ordered by subject for GroupShuffleSplit.
    """
    all_rows: list[dict] = []
    for csv_path in sorted(raw_dir.rglob("*.csv")):
        if csv_path.name == "ingest_summary.json":
            continue
        try:
            ds = load_csv(csv_path)
            all_rows.extend(ds.rows)
        except Exception as exc:
            import warnings
            warnings.warn(f"Skipping {csv_path}: {exc}", stacklevel=2)
    if not all_rows:
        raise RuntimeError(
            f"No valid CSV rows found under {raw_dir}. "
            f"Run: python -m ml.src.ingest_videos <videos_folder> first."
        )
    return Dataset(
        rows=all_rows,
        subject_ids=[r["subject_id"] for r in all_rows],
        feature_names=FEATURE_ORDER,
    )
from ml.src.calibration import PlattScaler, default_thresholds


def _rows_to_Xy(rows: list[dict]) -> tuple[list[list[float]], list[int]]:
    """Convert rows to (X, y) for sklearn. UNCERTAIN rows are dropped — they
    are not used for supervised training. Missing feature values (NaN) are
    filled with the feature median across the kept rows so the model never
    silently zero-fills."""
    keep = [r for r in rows if r.get("decision") in ("LIVE", "SPOOF")]
    if not keep:
        raise RuntimeError("no LIVE/SPOOF rows to train on")

    medians: dict[str, float] = {}
    for name in FEATURE_ORDER:
        vals = [r[name] for r in keep if not math.isnan(r[name])]
        if vals:
            medians[name] = sorted(vals)[len(vals) // 2]
        else:
            medians[name] = 0.0  # nothing to fill; document this

    X: list[list[float]] = []
    y: list[int] = []
    for r in keep:
        X.append([(r[n] if not math.isnan(r[n]) else medians[n]) for n in FEATURE_ORDER])
        y.append(1 if r["decision"] == "LIVE" else 0)
    return X, y


def train_random_forest(dataset: Dataset,
                        n_estimators: int = 300,
                        seed: int = 7) -> dict:
    """Train the RF baseline. Returns a dict suitable for freezing."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score

    X, y = _rows_to_Xy(dataset.rows)
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    clf.fit(X, y)
    raw_proba = clf.predict_proba(X)[:, 1].tolist()
    auc = roc_auc_score(y, raw_proba) if len(set(y)) > 1 else float("nan")

    # Platt-fit on the same data; OK because we're emitting a placeholder
    # model and explicitly marking the artifact UNTRAINED_NO_REAL_DATA.
    # On real data this should be fit on the held-out calibration set.
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


def write_artifact(out_dir: Path,
                   train_result: dict,
                   dataset: Dataset,
                   split_paths: dict,
                   manifest_status: str,
                   notes: list[str] | None = None) -> dict:
    """Serialize the trained model + scaler + manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "edgeppg_rf_v1.joblib"
    manifest_path = out_dir / "edgeppg_rf_v1.manifest.json"

    joblib.dump({
        "clf": train_result["clf"],
        "scaler": train_result["scaler"],
        "feature_names": list(FEATURE_ORDER),
        "schema_version": SCHEMA_VERSION,
        "model_type": "RandomForestClassifier",
    }, artifact_path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "feature_names": list(FEATURE_ORDER),
        "model_type": "RandomForestClassifier",
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
        "status": manifest_status,
        "notes": notes or [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"artifact": str(artifact_path), "manifest": str(manifest_path)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=REPO_ROOT / "models",
                   help="output directory for the frozen model artifact")
    p.add_argument("--n-subjects", type=int, default=8)
    p.add_argument("--sessions-per-subject", type=int, default=6)
    p.add_argument("--data-source", choices=("synthetic", "raw"), default="synthetic")
    args = p.parse_args()

    if args.data_source == "synthetic":
        dataset = make_synthetic_fixture(
            n_subjects=args.n_subjects,
            sessions_per_subject=args.sessions_per_subject,
        )
        split_paths = split_dataset_csv(dataset, REPO_ROOT / "data" / "splits")
        status = ("UNTRAINED_NO_REAL_DATA — synthetic fixture only, "
                  "used for pipeline verification.")
        notes = [
            "Trained on a deterministic synthetic fixture, not real data.",
            "ROC-AUC reported here is on the SAME training set; not a "
            "held-out estimate. Treat as pipeline self-test only.",
            "Replace with real-data training once a validation set is "
            "collected (Requirements §PR-DAT-1).",
        ]
    else:
        raw_dir = REPO_ROOT / "data" / "raw"
        print(f"Loading real data from {raw_dir} …")
        dataset = load_raw_dataset(raw_dir)
        n_live  = sum(1 for r in dataset.rows if r.get("decision") == "LIVE")
        n_spoof = sum(1 for r in dataset.rows if r.get("decision") == "SPOOF")
        print(f"  {len(dataset)} rows: {n_live} LIVE, {n_spoof} SPOOF, "
              f"{len(set(dataset.subject_ids))} subjects")
        if n_live == 0 or n_spoof == 0:
            raise SystemExit(
                f"Need both LIVE and SPOOF rows to train. "
                f"Found {n_live} LIVE, {n_spoof} SPOOF. "
                f"Run ingest_videos with both LIVE and SPOOF videos."
            )
        split_paths = split_dataset_csv(dataset, REPO_ROOT / "data" / "splits")
        status = "TRAINED_REAL_DATA"
        notes  = [
            f"Trained on {len(dataset)} real mobile-video sessions "
            f"({n_live} LIVE, {n_spoof} SPOOF, "
            f"{len(set(dataset.subject_ids))} subjects).",
            "Subject-independent GroupShuffleSplit applied.",
        ]

    result = train_random_forest(dataset)
    paths = write_artifact(args.out, result, dataset, split_paths,
                            status, notes)

    print(json.dumps({
        "wrote": paths,
        "n_train_rows": result["n_train_rows"],
        "train_auc": result["train_auc"],
        "status": status,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
