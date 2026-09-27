package com.edgeppg.app.features

/**
 * Stage 9 — Frozen 28-feature schema (Architecture §6).
 *
 * This is the **byte-exact** contract between on-device feature-vector
 * assembly and PC-side training / verification. It mirrors
 * `ml/src/feature_schema.py` exactly: the same 28 feature names, in the
 * same order, with the same NaN-for-missing semantics (Architecture §11).
 *
 * Renaming / reordering / adding a feature here is a schema-version bump
 * and requires a migration document. Renaming silently is forbidden.
 *
 * Order of features (verbatim from Architecture §6):
 *   face_confidence, face_quality,
 *   rppg_snr, rppg_peak_strength, rppg_hr_stability, rppg_roi_agreement,
 *   gaze_accuracy, head_accuracy, hand_accuracy,
 *   challenge_timing_error,
 *   optical_response_score,
 *   trusted_face_confidence, trusted_face_quality,
 *   trusted_gaze_accuracy, trusted_head_accuracy, trusted_hand_accuracy,
 *   trusted_challenge_timing_error,
 *   cross_person_timing, cross_person_interaction,
 *   relative_motion_consistency, participant_presence_consistency,
 *   challenge_sequence_consistency,
 *   camera_quality, frame_drop_rate, exposure_stability, awb_stability,
 *   capture_duration, device_integrity
 *
 * Missing values are represented as `Float.NaN`, **never** 0.0 — silently
 * zero-filling a missing rPPG would let UNCERTAIN sessions drift toward
 * SPOOF, which is explicitly forbidden (Architecture §11).
 */
object FeatureSchema {

    const val SCHEMA_VERSION = "edgeppg-1.0"

    /** Ordered, frozen feature names. Length MUST equal 28. */
    val FEATURE_ORDER: Array<String> = arrayOf(
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

    /**
     * Features whose natural range excludes 0.0. A literal 0.0 in these
     * slots is almost certainly a silent zero-fill of a missing value,
     * which Architecture §11 forbids. The validator flags it.
     */
    val ZERO_FORBIDDEN: Set<String> = setOf(
        "rppg_snr",
        "rppg_peak_strength",
        "rppg_hr_stability",
        "rppg_roi_agreement",
        "optical_response_score",
        "camera_quality",
        "exposure_stability",
        "awb_stability",
        "device_integrity",
    )

    /** Required auxiliary columns (NOT model features). */
    val AUX_COLUMNS: Array<String> = arrayOf(
        "subject_id",
        "session_id",
        "decision",
        "model_version",
        "protocol_version",
        "schema_version",
        "split",
    )

    /** The number of model features (28). */
    const val FEATURE_COUNT: Int = 28

    init {
        require(FEATURE_ORDER.size == FEATURE_COUNT) {
            "FEATURE_ORDER must have exactly $FEATURE_COUNT entries; " +
                "got ${FEATURE_ORDER.size}"
        }
    }

    /**
     * Return a row array of length 28 initialised to NaN. Auxiliary
     * columns are filled by the caller.
     *
     * This is the ONLY supported way to construct an empty row —
     * never inline literal zeroing.
     */
    fun emptyRow(): FloatArray {
        val row = FloatArray(FEATURE_COUNT)
        for (i in 0 until FEATURE_COUNT) {
            row[i] = Float.NaN
        }
        return row
    }

    /**
     * Index of a feature by name, or -1 if not present. Use
     * [requireValidName] when you need a guaranteed valid name.
     */
    fun indexOf(name: String): Int = FEATURE_ORDER.indexOf(name)

    fun requireValidName(name: String): Int {
        val i = indexOf(name)
        require(i >= 0) { "unknown feature name: $name" }
        return i
    }
}