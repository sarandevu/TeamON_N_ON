package com.edgeppg.app.features

/**
 * Stage 15 Task 5 — RowAssembler.
 *
 * Maps per-session metrics (face quality, rPPG outputs, behavioural
 * accuracies, capture stats) onto the 28-feature schema documented
 * in `Architecture §6` and pinned by
 * [FeatureSchema.FEATURE_ORDER] / [SchemaValidator].
 *
 * Fields the hackathon demo does not yet produce — multi-person
 * `trusted_*` and `cross_person_*` / `participant_presence_*` —
 * are filled with [Float.NaN] (the documented "missing" sentinel,
 * per Architecture §11 / `tests/test_schema_parity.py`). The
 * schema is the documented 28 fields; do not rename, reorder, or
 * add fields without bumping the schema version.
 *
 * The function never throws. The [Result] is a sealed-style
 * success / failure: if any field fails the schema's no-zero-fill
 * rule the assembler returns a failure result with the reason
 * rather than silently writing a bad row.
 */
object RowAssembler {

    /**
     * Result of an [assemble] call. On [Outcome.Ok] the [row] is a
     * length-28 [FloatArray] that has passed [SchemaValidator]. On
     * [Outcome.BadRow] the [reason] describes the validator's
     * complaint; the [row] is the would-be row (still 28 entries,
     * may be invalid).
     */
    data class Result(
        val outcome: Outcome,
        val row: FloatArray,
        val reason: String?,
    ) {
        enum class Outcome { Ok, BadRow }
    }

    /**
     * Inputs to the assembler. The defaults are the documented
     * "missing" sentinel (NaN for floats, 0f for the integer
     * counts). The activity's [com.edgeppg.app.session.SessionController]
     * is responsible for filling in everything it can.
     */
    data class Inputs(
        val faceConfidence: Float = Float.NaN,
        val faceQuality: Float = Float.NaN,
        val rppgSnr: Float = Float.NaN,
        val rppgPeakStrength: Float = Float.NaN,
        val rppgHrStability: Float = Float.NaN,
        val rppgRoiAgreement: Float = Float.NaN,
        val gazeAccuracy: Float = Float.NaN,
        val headAccuracy: Float = Float.NaN,
        val handAccuracy: Float = Float.NaN,
        val challengeTimingError: Float = Float.NaN,
        val opticalResponseScore: Float = Float.NaN,
        // Multi-person features — out of scope for the hackathon
        // single-participant demo (Architecture §5 / FR-MP-*).
        val trustedFaceConfidence: Float = Float.NaN,
        val trustedFaceQuality: Float = Float.NaN,
        val trustedGazeAccuracy: Float = Float.NaN,
        val trustedHeadAccuracy: Float = Float.NaN,
        val trustedHandAccuracy: Float = Float.NaN,
        val trustedChallengeTimingError: Float = Float.NaN,
        val crossPersonTiming: Float = Float.NaN,
        val crossPersonInteraction: Float = Float.NaN,
        val relativeMotionConsistency: Float = Float.NaN,
        val participantPresenceConsistency: Float = Float.NaN,
        val challengeSequenceConsistency: Float = Float.NaN,
        val cameraQuality: Float = Float.NaN,
        val frameDropRate: Float = Float.NaN,
        val exposureStability: Float = Float.NaN,
        val awbStability: Float = Float.NaN,
        val captureDuration: Float = Float.NaN,
        val deviceIntegrity: Float = Float.NaN,
    ) {
        init {
            require(FeatureSchema.FEATURE_ORDER.size == 28) {
                "RowAssembler requires the documented 28-feature schema; " +
                    "FeatureSchema.FEATURE_ORDER has ${FeatureSchema.FEATURE_ORDER.size} entries"
            }
        }
    }

    /**
     * Map [Inputs] to a length-28 [FloatArray] in the documented
     * [FeatureSchema.FEATURE_ORDER] order, then validate it. The
     * returned [Result.row] is `FloatArray(28)` either way.
     */
    fun assemble(inputs: Inputs = Inputs()): Result {
        val row = FloatArray(FeatureSchema.FEATURE_COUNT)
        // The order MUST match FeatureSchema.FEATURE_ORDER. The
        // schema-parity test pins this to the Python ml-side
        // definition; a runtime check here would be redundant.
        var i = 0
        row[i++] = inputs.faceConfidence
        row[i++] = inputs.faceQuality
        row[i++] = inputs.rppgSnr
        row[i++] = inputs.rppgPeakStrength
        row[i++] = inputs.rppgHrStability
        row[i++] = inputs.rppgRoiAgreement
        row[i++] = inputs.gazeAccuracy
        row[i++] = inputs.headAccuracy
        row[i++] = inputs.handAccuracy
        row[i++] = inputs.challengeTimingError
        row[i++] = inputs.opticalResponseScore
        row[i++] = inputs.trustedFaceConfidence
        row[i++] = inputs.trustedFaceQuality
        row[i++] = inputs.trustedGazeAccuracy
        row[i++] = inputs.trustedHeadAccuracy
        row[i++] = inputs.trustedHandAccuracy
        row[i++] = inputs.trustedChallengeTimingError
        row[i++] = inputs.crossPersonTiming
        row[i++] = inputs.crossPersonInteraction
        row[i++] = inputs.relativeMotionConsistency
        row[i++] = inputs.participantPresenceConsistency
        row[i++] = inputs.challengeSequenceConsistency
        row[i++] = inputs.cameraQuality
        row[i++] = inputs.frameDropRate
        row[i++] = inputs.exposureStability
        row[i++] = inputs.awbStability
        row[i++] = inputs.captureDuration
        row[i++] = inputs.deviceIntegrity
        check(i == FeatureSchema.FEATURE_COUNT) {
            "RowAssembler internal error: filled $i of " +
                "${FeatureSchema.FEATURE_COUNT} fields"
        }

        return try {
            SchemaValidator.validate(row)
            Result(Result.Outcome.Ok, row, reason = null)
        } catch (e: SchemaValidator.FeatureSchemaError) {
            Result(Result.Outcome.BadRow, row, reason = e.message)
        }
    }
}
