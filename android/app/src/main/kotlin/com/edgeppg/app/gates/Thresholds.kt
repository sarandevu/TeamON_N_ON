package com.edgeppg.app.gates

/**
 * Stage 11 — Configurable gate thresholds (Architecture §8, FR-GATE-8).
 *
 * Defaults are the documented placeholder starting values
 * (`LIVE_THRESHOLD = 0.80`, `SPOOF_THRESHOLD = 0.20`). Calibration
 * happens on the PC side (Stage 10 / 16) and is plumbed in via the
 * build config or a JSON resource (TBD — the resource hook is in
 * `app/src/main/res/values/edgeppg_thresholds.xml` if/when added).
 *
 * Quality-related thresholds here mirror the QualityGate (Stage 3)
 * starting values. Once we have a real validation set, these constants
 * become configurable through the [Thresholds] constructor and stop
 * being hard-coded.
 */
data class Thresholds(
    val live: Float,
    val spoof: Float,
    val minFpsForPass: Float = 25f,
    val maxDropRateForPass: Float = 0.10f,
    val minExposureStabilityForPass: Float = 0.80f,
    val minAwbStabilityForPass: Float = 0.80f,
) {
    companion object {
        /** Documented placeholder (FR-GATE-8). */
        val PLACEHOLDER = Thresholds(
            live = 0.80f,
            spoof = 0.20f,
        )
    }
}