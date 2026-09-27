"""EdgePPG ML source package.

PC-side ML pipeline:
  feature_schema   — frozen 28-feature contract shared with the on-device runtime
  dataset          — GroupShuffleSplit on subject_id, one-row-per-session files
  train_rf         — Random Forest baseline (first classifier)
  train_xgb        — XGBoost challenger
  calibration      — Platt scaling + configurable LIVE/SPOOF thresholds
  evaluate         — ROC-AUC, F1, attack-specific FAR/FRR (real data only)
  freeze_model     — serializes the chosen frozen model artifact

Training NEVER moves into the Android runtime. The runtime loads only the frozen
artifact via the ML fusion client.

All metrics produced here are explicitly marked as coming from a synthetic
fixture until real validation data exists. No real-data metrics are ever
fabricated (NFR-MET-1).
"""
__all__ = ["feature_schema", "dataset", "train_rf", "train_xgb",
           "calibration", "evaluate", "freeze_model"]
