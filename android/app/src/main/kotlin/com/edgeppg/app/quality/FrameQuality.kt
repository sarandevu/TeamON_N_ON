package com.edgeppg.app.quality

/**
 * Stage 3 — Per-frame quality snapshot emitted by [QualityGate].
 *
 * All fields are real values derived from sensor reads and frame counters;
 * nothing here is fabricated. Values that aren't observable yet are
 * surfaced as NaN — never silently zero-filled (Architecture §11).
 *
 *  - `fps`        : effective frames-per-second over the rolling window
 *                   (only frames that passed the AE/AWB lock).
 *  - `dropRate`   : dropped / expected frames over the rolling window.
 *  - `exposureStability` : 1 - CoV(SENSOR_EXPOSURE_TIME * SENSOR_SENSITIVITY)
 *                          over the rolling window. NaN when no samples.
 *  - `awbStability` : 1 - mean(CoV(R/G), CoV(B/G)) of AWB gains.
 *                     NaN when null AWB state (LEGACY devices).
 *  - `contaminationFlag` : true iff [MotionContamination] saw ≥ N
 *                           consecutive RGB step spikes.
 *  - `hasFace`    : whether a face has been seen recently.
 *  - `lockState`  : whether AE + AWB are locked.
 */
data class FrameQuality(
    val fps: Float,
    val dropRate: Float,
    val exposureStability: Float,
    val awbStability: Float,
    val contaminationFlag: Boolean,
    val hasFace: Boolean,
    val lockState: Boolean,
)
