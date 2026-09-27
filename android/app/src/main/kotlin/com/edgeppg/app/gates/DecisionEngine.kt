package com.edgeppg.app.gates

/**
 * Stage 11 — Security decision gates (Architecture §8).
 *
 * Reproduces the documented pseudocode verbatim:
 *
 * ```
 * if critical_integrity_failure:           → SPOOF
 * elif insufficient_quality (no face/lock/contamination):
 *     if P(LIVE) ≤ SPOOF_THRESHOLD:       → SPOOF   (physio override)
 *     elif P(LIVE) ≥ LIVE_THRESHOLD:      → LIVE    (physio override)
 *     else:                               → UNCERTAIN
 * elif low_fps / high_drop_rate:          → UNCERTAIN
 * elif P(LIVE) ≤ SPOOF_THRESHOLD:         → SPOOF
 * elif low_exposure/awb_stability:        → UNCERTAIN
 * elif challenge_incomplete:              → UNCERTAIN
 * elif P(LIVE) ≥ LIVE_THRESHOLD:          → LIVE
 * else:                                   → UNCERTAIN
 * ```
 *
 * Thresholds are read from [Thresholds] (a value class) and are explicitly
 * marked as starting values per `Requirements FR-GATE-8`:
 *
 *  - `LIVE_THRESHOLD = 0.80`
 *  - `SPOOF_THRESHOLD = 0.20`
 *
 * They MUST be re-calibrated from real validation data; the public API
 * accepts a [Thresholds] instance so callers can pass calibrated values
 * without recompiling.
 *
 * UNCERTAIN is a first-class output (TechStack §17). **Poor sensing
 * quality routes to UNCERTAIN — never automatically SPOOF** (FR-GATE-4).
 *
 * Inputs that are not observable (e.g. P(LIVE) == NaN because the model
 * is untrained, or quality == NaN because there are too few samples) are
 * treated as "insufficient quality" — UNCERTAIN. We never silently zero-
 * fill missing evidence (Architecture §11).
 */
object DecisionEngine {

    enum class Decision { LIVE, SPOOF, UNCERTAIN }

    /**
     * Inputs to the gate. All values are explicit; `Float.NaN` is the
     * canonical "missing" sentinel and means "no evidence available".
     */
    data class Inputs(
        val integrityOk: Boolean,
        val hasFace: Boolean,
        val lockState: Boolean,
        val contaminationFlag: Boolean,
        val fps: Float,
        val dropRate: Float,
        val exposureStability: Float,
        val awbStability: Float,
        val challengeCompleted: Boolean,
        val liveProbability: Float,
    )

    /**
     * Audit-friendly decision record. The caller (Stage 12 / 15) emits
     * this so the verifier can show *which gate* fired.
     */
    data class Verdict(
        val decision: Decision,
        val reason: String,
    )

    /**
     * Apply the gate pseudocode (Architecture §8).
     *
     * @param inputs the per-session evidence; see [Inputs].
     * @param thresholds LIVE/SPOOF thresholds (default = placeholder 0.80/0.20).
     */
    fun decide(
        inputs: Inputs,
        thresholds: Thresholds = Thresholds.PLACEHOLDER,
    ): Verdict {
        // 1. Integrity failure is the only path to SPOOF from the gates
        //    alone (the decision here is downstream of the gate; the
        //    Keystore layer (Stage 12) can also force SPOOF independently
        //    if a critical signature / nonce failure is observed).
        if (!inputs.integrityOk) {
            return Verdict(Decision.SPOOF, "integrity-failure")
        }

        // 2. Insufficient quality — UNCERTAIN, never auto-SPOOF.
        //    EXCEPTION: If we have strong accumulated physiological evidence
        //    (from peak rPPG values across the session), do NOT let transient
        //    quality issues (movement contamination, brief face-flicker, lock jitter)
        //    override the physiological verdict. A real person moving their head
        //    will trigger contamination, but their PEAK signal (when still) will
        //    clearly show live pulse. A spoof's peak will remain low.
        if (!inputs.hasFace || !inputs.lockState || inputs.contaminationFlag) {
            // If we have accumulated physiological evidence, let it decide
            if (!inputs.liveProbability.isNaN()) {
                if (inputs.liveProbability <= thresholds.spoof) {
                    return Verdict(Decision.SPOOF,
                        "p(live)<=${inputs.liveProbability}|quality-override:spoof")
                }
                if (inputs.liveProbability >= thresholds.live) {
                    return Verdict(Decision.LIVE,
                        "p(live)>=${inputs.liveProbability}|quality-override:live")
                }
            }
            return Verdict(
                Decision.UNCERTAIN,
                "insufficient-quality:"
                    + listOf(
                        if (!inputs.hasFace) "no-face" else null,
                        if (!inputs.lockState) "no-lock" else null,
                        if (inputs.contaminationFlag) "contamination" else null,
                    ).filterNotNull().joinToString(","),
            )
        }
        if (inputs.fps.isNaN() || inputs.fps < thresholds.minFpsForPass) {
            return Verdict(Decision.UNCERTAIN, "low-fps:${inputs.fps}")
        }
        if (!inputs.dropRate.isNaN() &&
            inputs.dropRate > thresholds.maxDropRateForPass) {
            return Verdict(Decision.UNCERTAIN, "high-drop-rate:${inputs.dropRate}")
        }

        // 3. Positive Spoof Detection — BEFORE optional quality gates.
        //    Exposure/AWB stability problems on a screen/photo must NOT mask
        //    a clear spoof signal. If the ML/physiological evidence says the
        //    subject is a presentation attack, that is the priority verdict.
        if (!inputs.liveProbability.isNaN() && inputs.liveProbability <= thresholds.spoof) {
            return Verdict(Decision.SPOOF,
                "p(live)<=spoof-threshold:${inputs.liveProbability}")
        }

        // 4. Optional quality gates (exposure/AWB stability).
        //    These run AFTER spoof detection so they don't mask a clear spoof.
        if (!inputs.exposureStability.isNaN() &&
            inputs.exposureStability < thresholds.minExposureStabilityForPass) {
            return Verdict(Decision.UNCERTAIN,
                "low-exposure-stability:${inputs.exposureStability}")
        }
        if (!inputs.awbStability.isNaN() &&
            inputs.awbStability < thresholds.minAwbStabilityForPass) {
            return Verdict(Decision.UNCERTAIN,
                "low-awb-stability:${inputs.awbStability}")
        }

        // 5. Challenge incomplete for non-spoof applicant — UNCERTAIN (FR-SESS-5 / FR-GATE-3).
        if (!inputs.challengeCompleted) {
            return Verdict(Decision.UNCERTAIN, "challenge-incomplete")
        }

        // 6. NaN P(LIVE) → no ML evidence → UNCERTAIN. We do NOT call this
        //    SPOOF. (Architecture §8 pseudocode + FR-GATE-4.)
        if (inputs.liveProbability.isNaN()) {
            return Verdict(Decision.UNCERTAIN, "no-ml-evidence:NaN")
        }

        // 7. Threshold gates.
        if (inputs.liveProbability >= thresholds.live) {
            return Verdict(Decision.LIVE,
                "p(live)>=live-threshold:${inputs.liveProbability}")
        }
        return Verdict(Decision.UNCERTAIN,
            "p(live)-borderline:${inputs.liveProbability}")
    }
}