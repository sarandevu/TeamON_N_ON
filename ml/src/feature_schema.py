"""EdgePPG frozen 28-feature schema (Architecture §6).

This schema is the **byte-exact** contract between PC training and the on-device
runtime feature vector assembly (Stage 9 / `FeatureSchema.kt`). Adding,
removing, or reordering a feature here is a schema-version bump and requires a
migration document. Renaming silently is forbidden.

Order of features (verbatim from Architecture §6):
    face_confidence, face_quality,
    rppg_snr, rppg_peak_strength, rppg_hr_stability, rppg_roi_agreement,
    gaze_accuracy, head_accuracy, hand_accuracy,
    challenge_timing_error,
    optical_response_score,
    trusted_face_confidence, trusted_face_quality,
    trusted_gaze_accuracy, trusted_head_accuracy, trusted_hand_accuracy,
    trusted_challenge_timing_error,
    cross_person_timing, cross_person_interaction,
    relative_motion_consistency, participant_presence_consistency,
    challenge_sequence_consistency,
    camera_quality, frame_drop_rate, exposure_stability, awb_stability,
    capture_duration, device_integrity

Missing values are represented as `float('nan')`, **never** 0.0 — silently
zero-filling a missing rPPG would let UNCERTAIN sessions drift toward SPOOF,
which is explicitly forbidden (Architecture §11).
"""

#: Current schema version. Bump on any change to FEATURE_ORDER / FEATURE_UNITS.
SCHEMA_VERSION = "edgeppg-1.0"

#: Ordered tuple of all 28 feature names. Order matters: the on-device row
#: assembler writes in this exact order, the verifier / trainer reads in this
#: exact order, and the model artifact is bound to it.
FEATURE_ORDER = (
    "face_confidence",
    "face_quality",
    "rppg_snr",
    "rppg_peak_strength",
    "rppg_hr_stability",
    "rppg_roi_agreement",
    "gaze_accuracy",
    "head_accuracy",
    "hand_accuracy",
    "challenge_timing_error",
    "optical_response_score",
    "trusted_face_confidence",
    "trusted_face_quality",
    "trusted_gaze_accuracy",
    "trusted_head_accuracy",
    "trusted_hand_accuracy",
    "trusted_challenge_timing_error",
    "cross_person_timing",
    "cross_person_interaction",
    "relative_motion_consistency",
    "participant_presence_consistency",
    "challenge_sequence_consistency",
    "camera_quality",
    "frame_drop_rate",
    "exposure_stability",
    "awb_stability",
    "capture_duration",
    "device_integrity",
)

#: Features whose natural range excludes 0.0. A literal 0.0 in these
#: slots is almost certainly a silent zero-fill of a missing value,
#: which Architecture §11 forbids. Mirrors
#: `android/.../features/FeatureSchema.kt:ZERO_FORBIDDEN`; the parity
#: test `tests/test_schema_parity.py` enforces that the two stay in
#: sync.
ZERO_FORBIDDEN = frozenset({
    "rppg_snr",
    "rppg_peak_strength",
    "rppg_hr_stability",
    "rppg_roi_agreement",
    "optical_response_score",
    "camera_quality",
    "exposure_stability",
    "awb_stability",
    "device_integrity",
})

#: Expected approximate scale / units per feature, used by the schema
#: validator and surfaced for documentation only. Values outside these ranges
#: are warnings, not hard failures.
FEATURE_UNITS = {
    "face_confidence":                   "[0, 1]   detector confidence",
    "face_quality":                      "[0, 1]   quality score (illumination, motion)",
    "rppg_snr":                          "[0, 1]   bandpass peak SNR / total",
    "rppg_peak_strength":                "[0, 1]   normalised FFT peak power",
    "rppg_hr_stability":                 "[0, 1]   inverse of HR variance",
    "rppg_roi_agreement":                "[-1, 1]  mean pairwise Pearson across ROIs",
    "gaze_accuracy":                     "[0, 1]   fraction of gaze challenges matched",
    "head_accuracy":                     "[0, 1]   fraction of head challenges matched",
    "hand_accuracy":                     "[0, 1]   fraction of hand challenges matched",
    "challenge_timing_error":            "[0, +∞)  s, mean abs latency vs request",
    "optical_response_score":            "[0, 1]   correlation with expected optical seq",
    "trusted_face_confidence":           "[0, 1]",
    "trusted_face_quality":              "[0, 1]",
    "trusted_gaze_accuracy":             "[0, 1]",
    "trusted_head_accuracy":             "[0, 1]",
    "trusted_hand_accuracy":             "[0, 1]",
    "trusted_challenge_timing_error":    "[0, +∞)  s",
    "cross_person_timing":               "[0, 1]   ordering/timing consistency",
    "cross_person_interaction":          "[0, 1]   cross-person challenge interaction",
    "relative_motion_consistency":       "[0, 1]   inter-subject motion coherence",
    "participant_presence_consistency":  "[0, 1]   both subjects present for whole session",
    "challenge_sequence_consistency":    "[0, 1]   sequence match vs challenge seed",
    "camera_quality":                    "[0, 1]   composite quality gate score",
    "frame_drop_rate":                   "[0, 1]   drops / expected frames",
    "exposure_stability":                "[0, 1]   1 - CoV of exposure time",
    "awb_stability":                     "[0, 1]   1 - CoV of AWB gains",
    "capture_duration":                  "s,       total session length",
    "device_integrity":                  "{0, 1}   1=integrity checks pass",
}

#: Auxiliary columns every row carries. These are NOT model features; they
#: describe the row. They are required on every dataset row.
AUX_COLUMNS = (
    "subject_id",   # group key for subject-independent split
    "session_id",   # unique per session
    "decision",     # LIVE / SPOOF / UNCERTAIN (label for supervised training)
    "model_version",
    "protocol_version",
    "schema_version",
    "split",        # train / val / test / hold
)


class FeatureSchemaError(ValueError):
    """Raised on any schema-level violation (unknown key, wrong column count,
    silently-zero-filled missing value, etc.)."""


def expected_feature_count() -> int:
    """Number of model features (28). Auxiliary columns are separate."""
    return len(FEATURE_ORDER)


def validate_row(row: dict) -> None:
    """Strict row validator. Raises FeatureSchemaError on any violation.

    Validation rules:
      * Every feature in FEATURE_ORDER must be present.
      * No unknown feature keys.
      * Values are real numbers (including nan) — never strings, lists, None.
      * Decision must be LIVE / SPOOF / UNCERTAIN if provided (auxiliary).
      * Missing values are NaN, never 0.0 (Architecture §11).
        The validator is strict on this: a value that is exactly 0.0 in a
        feature whose semantics are "missing = NaN" is rejected, even
        though 0.0 is a numeric value. The caller must use `NaN` to mark
        a feature unavailable.
    """
    import math
    unknown = set(row) - set(FEATURE_ORDER) - set(AUX_COLUMNS)
    if unknown:
        raise FeatureSchemaError(f"unknown keys: {sorted(unknown)}")

    missing = [f for f in FEATURE_ORDER if f not in row]
    if missing:
        raise FeatureSchemaError(f"missing feature keys: {missing}")

    decision = row.get("decision")
    if decision is not None and decision not in {"LIVE", "SPOOF", "UNCERTAIN"}:
        raise FeatureSchemaError(f"bad decision value: {decision!r}")

    # Features whose natural range excludes 0.0. The set is exposed at
    # module scope as ZERO_FORBIDDEN so the Kotlin-side parity test can
    # assert equality.
    zero_forbidden = ZERO_FORBIDDEN

    for name in FEATURE_ORDER:
        v = row[name]
        if not isinstance(v, (int, float)) or (isinstance(v, bool)):
            # bool is a subclass of int — reject explicitly so True/False
            # can never silently stand in for a missing feature value.
            raise FeatureSchemaError(
                f"feature {name!r} has non-numeric value {v!r}"
            )
        if name in zero_forbidden and v == 0.0:
            raise FeatureSchemaError(
                f"feature {name!r} is exactly 0.0 — this is treated as a "
                f"silent zero-fill of a missing value; use NaN instead "
                f"(Architecture §11)."
            )
        # NaN is allowed (and represents "missing"). Infinity is not —
        # any non-finite that isn't NaN is a programming error.
        if not math.isfinite(v) and not math.isnan(v):
            raise FeatureSchemaError(
                f"feature {name!r} has non-finite, non-NaN value {v!r}"
            )


def empty_row(subject_id: str = "SYNTHETIC",
              session_id: str = "SYNTHETIC",
              decision: str | None = None) -> dict:
    """Return a row dict with every feature set to NaN. Auxiliary columns are
    filled with the supplied ids (or the placeholder). This is the only way to
    construct an empty row — never inline literal zeroing."""
    import math
    row = {name: math.nan for name in FEATURE_ORDER}
    row["subject_id"] = subject_id
    row["session_id"] = session_id
    row["model_version"] = "UNTRAINED_NO_REAL_DATA"
    row["protocol_version"] = "1.0"
    row["schema_version"] = SCHEMA_VERSION
    row["split"] = "hold"
    if decision is not None:
        row["decision"] = decision
    return row


def feature_names_csv() -> str:
    """Comma-joined feature names for CSV headers (no aux columns)."""
    return ",".join(FEATURE_ORDER)


def full_columns_csv() -> str:
    """Comma-joined header for a full CSV row, including auxiliary columns."""
    return ",".join(("subject_id", "session_id") + FEATURE_ORDER +
                    ("decision", "model_version", "protocol_version",
                     "schema_version", "split"))
