"""EdgePPG batch video ingestion (PC-side, offline training only).

Scans a folder for mobile videos, extracts features from each,
and writes them to data/raw/<subject_id>/<session_id>.csv files
ready for the training pipeline.

Folder conventions
------------------
Input folder can follow either pattern:

Pattern A — labelled subfolders:
    videos/
      LIVE/
        S001_v01.mp4
        S001_v02.mp4
      SPOOF/
        S002_v01.mp4

Pattern B — flat with filename convention:
    videos/
      S001_v01_LIVE.mp4
      S002_v01_SPOOF.mp4

Pattern C — no label (defaults to --default-label, usually LIVE for
enrolled users and SPOOF for test spoofs):
    videos/
      S001_v01.mp4

Usage:
    python -m ml.src.ingest_videos path/to/videos/ --label-mode subfolder
    python -m ml.src.ingest_videos path/to/videos/ --label-mode filename
    python -m ml.src.ingest_videos path/to/videos/ --default-label SPOOF

After ingestion, run:
    python -m ml.src.train_rf --data-source raw --out models/
    python -m ml.src.train_xgb --data-source raw --out models/
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO_ROOT = _HERE.parents[2]
RAW_DIR   = REPO_ROOT / "data" / "raw"

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}


def _guess_label_from_path(video_path: Path, label_mode: str,
                            default_label: str) -> str:
    if label_mode == "subfolder":
        parts = [p.upper() for p in video_path.parts]
        if "LIVE" in parts:
            return "LIVE"
        if "SPOOF" in parts:
            return "SPOOF"
        return default_label
    if label_mode == "filename":
        stem_up = video_path.stem.upper()
        if "LIVE" in stem_up:
            return "LIVE"
        if "SPOOF" in stem_up:
            return "SPOOF"
        return default_label
    return default_label


def _subject_session_from_path(video_path: Path, label_mode: str,
                                subject_prefix: str) -> tuple[str, str]:
    stem = video_path.stem
    # Remove label suffix if present
    for suffix in ("_LIVE", "_SPOOF", "-LIVE", "-SPOOF"):
        if stem.upper().endswith(suffix):
            stem = stem[:len(stem) - len(suffix)]

    parts = stem.split("_")
    if len(parts) >= 2 and parts[0].upper().startswith(subject_prefix.upper()):
        subject_id = parts[0].upper()
        session_id = stem
    else:
        subject_id = f"{subject_prefix}{stem[:6].upper()}"
        session_id = stem
    return subject_id, session_id


def ingest_folder(videos_dir: Path, out_dir: Path, label_mode: str,
                  default_label: str, subject_prefix: str,
                  max_frames: int, verbose: bool) -> list[dict]:
    from ml.src.extract_video_features import extract_features_from_video
    from ml.src.feature_schema import FEATURE_ORDER, AUX_COLUMNS

    cols = ("subject_id", "session_id") + FEATURE_ORDER + AUX_COLUMNS[2:]

    videos = sorted([p for p in videos_dir.rglob("*")
                     if p.suffix.lower() in VIDEO_EXTS])
    if not videos:
        print(f"No video files found in {videos_dir}")
        return []

    print(f"Found {len(videos)} video(s) in {videos_dir}")
    results = []
    errors  = []

    for vp in videos:
        label = _guess_label_from_path(vp, label_mode, default_label)
        subject_id, session_id = _subject_session_from_path(vp, label_mode, subject_prefix)

        if verbose:
            print(f"\n→ {vp.name}  subject={subject_id}  session={session_id}  label={label}")

        try:
            row = extract_features_from_video(
                vp, subject_id=subject_id, session_id=session_id,
                label=label, max_frames=max_frames, verbose=verbose)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            errors.append({"video": str(vp), "error": str(exc)})
            continue

        # Write per-subject CSV
        subj_dir = out_dir / subject_id
        subj_dir.mkdir(parents=True, exist_ok=True)
        csv_path = subj_dir / f"{session_id}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(cols), extrasaction="ignore")
            w.writeheader()
            w.writerow({c: row.get(c, "") for c in cols})

        results.append({"video": str(vp), "subject": subject_id,
                        "session": session_id, "label": label,
                        "csv": str(csv_path)})
        print(f"  ✓ wrote {csv_path}")

    print(f"\nIngestion complete: {len(results)} OK, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  {e}")
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Batch ingest mobile videos into EdgePPG data/raw/")
    p.add_argument("videos_dir", type=Path,
                   help="Folder of mobile video files (MP4/MOV/AVI/MKV)")
    p.add_argument("--out-dir",         type=Path, default=RAW_DIR,
                   help=f"Output directory [default: {RAW_DIR}]")
    p.add_argument("--label-mode",      choices=["subfolder", "filename", "default"],
                   default="subfolder",
                   help="How to determine LIVE/SPOOF label from folder structure")
    p.add_argument("--default-label",   choices=["LIVE", "SPOOF"], default="LIVE",
                   help="Label when not determinable from path")
    p.add_argument("--subject-prefix",  default="S",
                   help="Prefix for auto-generated subject IDs")
    p.add_argument("--max-frames",      type=int, default=900)
    p.add_argument("--quiet",           action="store_true")
    args = p.parse_args()

    results = ingest_folder(
        videos_dir=args.videos_dir,
        out_dir=args.out_dir,
        label_mode=args.label_mode,
        default_label=args.default_label,
        subject_prefix=args.subject_prefix,
        max_frames=args.max_frames,
        verbose=not args.quiet,
    )

    summary_path = args.out_dir / "ingest_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Summary written to {summary_path}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
