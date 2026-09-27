"""EdgePPG dataset handling (PC-side, training-only).

Strict subject-independent split: `GroupShuffleSplit` on `subject_id`.
No session data from the same subject appears in both train and test.

Until real data is collected, this module operates on a **synthetic golden
fixture**: deterministic seed, two subject groups, balanced LIVE / SPOOF
labels, all features within documented units. The fixture is for pipeline
verification only — the resulting model artifact is explicitly marked
`UNTRAINED_NO_REAL_DATA` and is never used to claim real metrics.

When real data lands:
  * drop the CSV rows under `data/raw/<subject_id>/<session_id>.csv` (one row
    per session) with the columns from `feature_schema.full_columns_csv()`;
  * set `DATA_SOURCE=raw` in the environment;
  * re-run `python -m ml.src.train_rf --out models/`.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sklearn.model_selection import GroupShuffleSplit

from ml.src.feature_schema import (
    AUX_COLUMNS,
    FEATURE_ORDER,
    FeatureSchemaError,
    SCHEMA_VERSION,
    empty_row,
    validate_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


@dataclass
class Dataset:
    rows: list[dict]
    subject_ids: list[str]
    feature_names: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.rows)


# ----- Synthetic golden fixture (pipeline-only) --------------------------------

def _synth_live_row(rng: random.Random, subject_id: str, session_id: str) -> dict:
    """A synthetic LIVE row: high quality, rPPG present, challenges matched,
    coherence high. Used only to verify the pipeline path end-to-end."""
    row = empty_row(subject_id=subject_id, session_id=session_id,
                    decision="LIVE")
    row["face_confidence"]                 = 0.90 + rng.uniform(-0.05, 0.05)
    row["face_quality"]                    = 0.85 + rng.uniform(-0.05, 0.05)
    row["rppg_snr"]                        = 0.55 + rng.uniform(-0.05, 0.05)
    row["rppg_peak_strength"]              = 0.60 + rng.uniform(-0.05, 0.05)
    row["rppg_hr_stability"]               = 0.80 + rng.uniform(-0.05, 0.05)
    row["rppg_roi_agreement"]              = 0.60 + rng.uniform(-0.05, 0.05)
    row["gaze_accuracy"]                   = 0.92 + rng.uniform(-0.05, 0.05)
    row["head_accuracy"]                   = 0.92 + rng.uniform(-0.05, 0.05)
    row["hand_accuracy"]                   = 0.85 + rng.uniform(-0.10, 0.05)
    row["challenge_timing_error"]          = 0.10 + rng.uniform(0.0, 0.05)
    row["optical_response_score"]          = 0.80 + rng.uniform(-0.05, 0.05)
    row["trusted_face_confidence"]         = 0.85 + rng.uniform(-0.05, 0.05)
    row["trusted_face_quality"]            = 0.80 + rng.uniform(-0.05, 0.05)
    row["trusted_gaze_accuracy"]           = 0.90 + rng.uniform(-0.05, 0.05)
    row["trusted_head_accuracy"]           = 0.90 + rng.uniform(-0.05, 0.05)
    row["trusted_hand_accuracy"]           = 0.80 + rng.uniform(-0.10, 0.05)
    row["trusted_challenge_timing_error"]  = 0.12 + rng.uniform(0.0, 0.05)
    row["cross_person_timing"]             = 0.85 + rng.uniform(-0.05, 0.05)
    row["cross_person_interaction"]        = 0.85 + rng.uniform(-0.05, 0.05)
    row["relative_motion_consistency"]     = 0.85 + rng.uniform(-0.05, 0.05)
    row["participant_presence_consistency"]= 0.95 + rng.uniform(-0.05, 0.05)
    row["challenge_sequence_consistency"]  = 0.95 + rng.uniform(-0.05, 0.05)
    row["camera_quality"]                  = 0.90 + rng.uniform(-0.05, 0.05)
    row["frame_drop_rate"]                 = 0.02 + rng.uniform(0.0, 0.02)
    row["exposure_stability"]              = 0.95 + rng.uniform(-0.05, 0.05)
    row["awb_stability"]                   = 0.90 + rng.uniform(-0.05, 0.05)
    row["capture_duration"]                = 12.0 + rng.uniform(-1.0, 1.0)
    row["device_integrity"]                = 1.0
    return row


def _synth_spoof_row(rng: random.Random, subject_id: str, session_id: str) -> dict:
    """A synthetic SPOOF row: low rPPG, low optical correlation, mismatched
    challenges. Used only to verify the pipeline path end-to-end."""
    row = empty_row(subject_id=subject_id, session_id=session_id,
                    decision="SPOOF")
    row["face_confidence"]                 = 0.80 + rng.uniform(-0.05, 0.05)
    row["face_quality"]                    = 0.55 + rng.uniform(-0.10, 0.05)
    row["rppg_snr"]                        = 0.05 + rng.uniform(0.0, 0.05)
    row["rppg_peak_strength"]              = 0.05 + rng.uniform(0.0, 0.05)
    row["rppg_hr_stability"]               = 0.20 + rng.uniform(-0.05, 0.05)
    # rppg_roi_agreement is in the zero_forbidden set; use a small floor.
    row["rppg_roi_agreement"]              = 0.01 + rng.uniform(-0.01, 0.04)
    row["gaze_accuracy"]                   = 0.20 + rng.uniform(-0.05, 0.05)
    row["head_accuracy"]                   = 0.20 + rng.uniform(-0.05, 0.05)
    row["hand_accuracy"]                   = 0.20 + rng.uniform(-0.05, 0.05)
    row["challenge_timing_error"]          = 0.80 + rng.uniform(0.0, 0.10)
    row["optical_response_score"]          = 0.10 + rng.uniform(0.0, 0.05)
    row["trusted_face_confidence"]         = 0.30 + rng.uniform(-0.05, 0.05)
    row["trusted_face_quality"]            = 0.30 + rng.uniform(-0.05, 0.05)
    row["trusted_gaze_accuracy"]           = 0.20 + rng.uniform(-0.05, 0.05)
    row["trusted_head_accuracy"]           = 0.20 + rng.uniform(-0.05, 0.05)
    row["trusted_hand_accuracy"]           = 0.20 + rng.uniform(-0.05, 0.05)
    row["trusted_challenge_timing_error"]  = 0.85 + rng.uniform(0.0, 0.10)
    row["cross_person_timing"]             = 0.20 + rng.uniform(-0.05, 0.05)
    row["cross_person_interaction"]        = 0.20 + rng.uniform(-0.05, 0.05)
    row["relative_motion_consistency"]     = 0.30 + rng.uniform(-0.05, 0.05)
    row["participant_presence_consistency"]= 0.30 + rng.uniform(-0.05, 0.05)
    row["challenge_sequence_consistency"]  = 0.20 + rng.uniform(-0.05, 0.05)
    row["camera_quality"]                  = 0.50 + rng.uniform(-0.10, 0.05)
    row["frame_drop_rate"]                 = 0.10 + rng.uniform(0.0, 0.05)
    row["exposure_stability"]              = 0.60 + rng.uniform(-0.05, 0.05)
    row["awb_stability"]                   = 0.50 + rng.uniform(-0.05, 0.05)
    row["capture_duration"]                = 12.0 + rng.uniform(-1.0, 1.0)
    row["device_integrity"]                = 1.0
    return row


def _synth_video_replay_spoof_row(rng: random.Random, subject_id: str, session_id: str) -> dict:
    """A synthetic video replay SPOOF row: high face confidence/quality from high-res screen,
    but near-zero rPPG pulse, low ROI correlation, timing error on active challenges, and
    distorted optical reflection."""
    row = empty_row(subject_id=subject_id, session_id=session_id, decision="SPOOF")
    row["face_confidence"]                 = 0.92 + rng.uniform(-0.03, 0.03)
    row["face_quality"]                    = 0.85 + rng.uniform(-0.05, 0.05)
    row["rppg_snr"]                        = 0.04 + rng.uniform(0.0, 0.04)
    row["rppg_peak_strength"]              = 0.04 + rng.uniform(0.0, 0.03)
    row["rppg_hr_stability"]               = 0.15 + rng.uniform(-0.05, 0.05)
    row["rppg_roi_agreement"]              = 0.02 + rng.uniform(-0.01, 0.03)
    row["gaze_accuracy"]                   = 0.15 + rng.uniform(-0.05, 0.05)
    row["head_accuracy"]                   = 0.15 + rng.uniform(-0.05, 0.05)
    row["hand_accuracy"]                   = 0.10 + rng.uniform(-0.05, 0.05)
    row["challenge_timing_error"]          = 0.88 + rng.uniform(0.0, 0.08)
    row["optical_response_score"]          = 0.08 + rng.uniform(0.0, 0.04)
    row["trusted_face_confidence"]         = 0.30 + rng.uniform(-0.05, 0.05)
    row["trusted_face_quality"]            = 0.30 + rng.uniform(-0.05, 0.05)
    row["trusted_gaze_accuracy"]           = 0.15 + rng.uniform(-0.05, 0.05)
    row["trusted_head_accuracy"]           = 0.15 + rng.uniform(-0.05, 0.05)
    row["trusted_hand_accuracy"]           = 0.10 + rng.uniform(-0.05, 0.05)
    row["trusted_challenge_timing_error"]  = 0.90 + rng.uniform(0.0, 0.08)
    row["cross_person_timing"]             = 0.15 + rng.uniform(-0.05, 0.05)
    row["cross_person_interaction"]        = 0.15 + rng.uniform(-0.05, 0.05)
    row["relative_motion_consistency"]     = 0.25 + rng.uniform(-0.05, 0.05)
    row["participant_presence_consistency"]= 0.30 + rng.uniform(-0.05, 0.05)
    row["challenge_sequence_consistency"]  = 0.15 + rng.uniform(-0.05, 0.05)
    row["camera_quality"]                  = 0.85 + rng.uniform(-0.05, 0.05)
    row["frame_drop_rate"]                 = 0.06 + rng.uniform(0.0, 0.04)
    row["exposure_stability"]              = 0.75 + rng.uniform(-0.05, 0.05)
    row["awb_stability"]                   = 0.70 + rng.uniform(-0.05, 0.05)
    row["capture_duration"]                = 12.0 + rng.uniform(-1.0, 1.0)
    row["device_integrity"]                = 1.0
    return row


def make_synthetic_fixture(n_subjects: int = 8,
                           sessions_per_subject: int = 6,
                           seed: int = 0xE9BE00) -> Dataset:
    """Build a deterministic synthetic dataset for pipeline verification.

    Half subjects produce only LIVE rows; half produce SPOOF rows (photo + video replays).
    GroupShuffleSplit on subject_id is a meaningful split because the labels are subject-correlated.
    """
    if n_subjects % 2 != 0:
        raise ValueError("n_subjects must be even (half LIVE, half SPOOF).")
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n_subjects):
        sid = f"S{i:03d}"
        is_live = (i % 2 == 0)
        for j in range(sessions_per_subject):
            sess = f"{sid}-j{j:02d}"
            if is_live:
                rows.append(_synth_live_row(rng, sid, sess))
            elif j % 2 == 0:
                rows.append(_synth_video_replay_spoof_row(rng, sid, sess))
            else:
                rows.append(_synth_spoof_row(rng, sid, sess))
    for r in rows:
        validate_row(r)
    return Dataset(
        rows=rows,
        subject_ids=[r["subject_id"] for r in rows],
        feature_names=FEATURE_ORDER,
    )


def make_orpad_fixture(n_subjects: int = 30, seed: int = 0x011CA) -> Dataset:
    """Build a dataset conforming to the 26-scenario OR-PAD benchmark.

    Covers Real Access (S1-S3), Print Attacks (PB, PM, PI), Replay Static (RSB, RSM, RSI, RSA),
    and Replay Video Attacks (RB, RMX, RMY, RI, RA).
    Each subject has both real access and presentation attacks, ensuring
    stratified, subject-independent generalization.
    """
    from ml.src.orpad_engine import make_orpad_benchmark_dataset
    rows = make_orpad_benchmark_dataset(n_subjects=n_subjects, seed=seed)
    return Dataset(
        rows=rows,
        subject_ids=[r["subject_id"] for r in rows],
        feature_names=FEATURE_ORDER,
    )


# ----- Subject-independent split ---------------------------------------------

def subject_independent_split(dataset: Dataset,
                              val_frac: float = 0.25,
                              test_frac: float = 0.25,
                              seed: int = 17) -> tuple[list[int],
                                                        list[int],
                                                        list[int]]:
    """Two-stage GroupShuffleSplit: train / (val+test), then val / test.

    Returns index lists into `dataset.rows`.
    Raises ValueError if a split would produce an empty partition.
    """
    if not 0 < val_frac < 1 or not 0 < test_frac < 1:
        raise ValueError("val_frac / test_frac must be in (0, 1).")
    if val_frac + test_frac >= 1.0:
        raise ValueError("val_frac + test_frac must be < 1.0.")

    gss1 = GroupShuffleSplit(n_splits=1, test_size=val_frac + test_frac,
                             random_state=seed)
    train_idx, holdout_idx = next(gss1.split(
        X=range(len(dataset)), y=None,
        groups=dataset.subject_ids,
    ))
    holdout_subjects = [dataset.subject_ids[i] for i in holdout_idx]
    relative_test = test_frac / (val_frac + test_frac)
    gss2 = GroupShuffleSplit(n_splits=1, test_size=relative_test,
                             random_state=seed + 1)
    val_rel, test_rel = next(gss2.split(
        X=range(len(holdout_idx)), y=None,
        groups=holdout_subjects,
    ))
    val_idx = [holdout_idx[i] for i in val_rel]
    test_idx = [holdout_idx[i] for i in test_rel]
    if len(train_idx) == 0 or len(val_idx) == 0 or len(test_idx) == 0:
        raise ValueError(
            f"empty partition: train={len(train_idx)} val={len(val_idx)} "
            f"test={len(test_idx)}; n_subjects={len(set(dataset.subject_ids))}"
        )
    return list(train_idx), val_idx, test_idx


# ----- CSV persistence --------------------------------------------------------

def write_csv(rows: Iterable[dict], path: Path,
              columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), extrasaction="raise")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def load_csv(path: Path) -> Dataset:
    """Load a CSV. Strict schema validation."""
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            row = {k: (float(v) if k in FEATURE_ORDER else v) for k, v in r.items()}
            validate_row(row)
            rows.append(row)
    return Dataset(
        rows=rows,
        subject_ids=[r["subject_id"] for r in rows],
        feature_names=FEATURE_ORDER,
    )


def split_dataset_csv(dataset: Dataset,
                      out_dir: Path,
                      seed: int = 17,
                      val_frac: float = 0.25,
                      test_frac: float = 0.25) -> dict[str, Path]:
    """Persist the subject-independent split as three CSVs."""
    train_idx, val_idx, test_idx = subject_independent_split(
        dataset, val_frac=val_frac, test_frac=test_frac, seed=seed,
    )
    cols = ("subject_id", "session_id") + FEATURE_ORDER + AUX_COLUMNS[2:]
    paths = {
        "train": out_dir / "train.csv",
        "val":   out_dir / "val.csv",
        "test":  out_dir / "test.csv",
    }
    for name, idxs in (("train", train_idx), ("val", val_idx), ("test", test_idx)):
        rows = [dataset.rows[i] for i in idxs]
        for r in rows:
            r["split"] = name
        write_csv(rows, paths[name], cols)
    return paths


def dataset_fingerprint(dataset: Dataset) -> str:
    """Stable SHA-256 over all rows + subject ids. Used in the model manifest
    so a future 'is this the model that produced this evidence?' check is
    possible."""
    h = hashlib.sha256()
    for r in dataset.rows:
        h.update(repr(sorted(r.items())).encode("utf-8"))
    return h.hexdigest()


if __name__ == "__main__":
    # CLI: build the synthetic fixture, write a split, print the fingerprint.
    ds = make_synthetic_fixture()
    print(f"synthetic dataset: {len(ds)} rows, "
          f"{len(set(ds.subject_ids))} subjects, "
          f"{len(ds.feature_names)} features")
    paths = split_dataset_csv(ds, DATA_DIR / "splits")
    print(f"splits written to {paths}")
    print(f"fingerprint: {dataset_fingerprint(ds)[:16]}…")
