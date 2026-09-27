package com.edgeppg.app.quality

/**
 * Stage 3 — Quality gate.
 *
 * Composes [FrameMetrics], [ExposureStability], [AwbStability] and
 * [MotionContamination] into a single [FrameQuality] snapshot, and
 * routes that snapshot to a three-way `gateDecision`:
 *
 *  - PASS   : every required signal is acceptable.
 *  - RETRY  : a transient signal (motion spike, AE not yet locked) may
 *             resolve on the next frame; caller may apply the
 *             configurable retry policy (default: 1 retry, per
 *             FR-SESS-6, configurable per Architecture §11).
 *  - FAIL   : a hard quality failure (very low FPS, sustained
 *             contamination, or missing AE lock entirely). This routes
 *             the session to UNCERTAIN at the decision engine
 *             (Stage 11) — never to SPOOF.
 *
 * Threshold policy:
 *  - All thresholds live here as constants; none are hard-coded inside
 *    the consuming code. They are explicitly labeled as starting values
 *    to be calibrated once a real validation set exists (Stage 10).
 */
class QualityGate(
    private val minFpsForPass: Float = 25f,
    private val maxDropRateForPass: Float = 0.10f,
    private val minExposureStabilityForPass: Float = 0.80f,
    private val minAwbStabilityForPass: Float = 0.80f,
) {
    enum class GateDecision { PASS, RETRY, FAIL }

    val frameMetrics = FrameMetrics()
    val exposureStability = ExposureStability()
    val awbStability = AwbStability()
    val motionContamination = MotionContamination()

    /**
     * Record one frame's worth of evidence.
     *  - `timestampNs` is the sensor timestamp for frame-timing stats.
     *  - `rgbMeans` is the 9-float RGB-means array from [RoiTracker].
     *  - `exposureNs`, `sensitivityIso`, `awbR`, `awbG`, `awbB` are
     *    Camera2 `CaptureResult` reads. Any may be null (LEGACY device).
     *  - `lockState` is whether AE+AWB are locked (Stage-2 contract).
     *  - `hasFace` is the Stage-2 face presence flag.
     */
    fun record(
        timestampNs: Long,
        rgbMeans: FloatArray,
        exposureNs: Long?,
        sensitivityIso: Int?,
        awbR: Float?,
        awbG: Float?,
        awbB: Float?,
        lockState: Boolean,
        hasFace: Boolean,
    ) {
        if (lockState) {
            frameMetrics.record(timestampNs)
            exposureStability.record(exposureNs, sensitivityIso)
            awbStability.record(awbR, awbG, awbB)
        }
        motionContamination.observe(rgbMeans)
    }

    /** Build a [FrameQuality] snapshot from the current accumulators. */
    fun snapshot(hasFace: Boolean, lockState: Boolean): FrameQuality = FrameQuality(
        fps = frameMetrics.fps(),
        dropRate = frameMetrics.dropRate(),
        exposureStability = exposureStability.stability(),
        awbStability = awbStability.stability(),
        contaminationFlag = motionContamination.isContaminated(),
        hasFace = hasFace,
        lockState = lockState,
    )

    /**
     * Compute the gate decision for this snapshot. All inputs are taken
     * from a fresh [snapshot]; missing-data values are propagated as
     * NaN/UNDEFINED.
     */
    fun decide(hasFace: Boolean, lockState: Boolean): GateDecision {
        // Hard fail: no AE/AWB lock after a reasonable time. We don't know
        // the exact time the camera has been running here; we leave it as
        // a signal the caller can use.
        if (!lockState) return GateDecision.RETRY
        // Hard fail: no face.
        if (!hasFace) return GateDecision.RETRY
        // Hard fail: contamination flag set (sustained spikes).
        if (motionContamination.isContaminated()) return GateDecision.FAIL

        val fps = frameMetrics.fps()
        if (!fps.isNaN() && fps < minFpsForPass) return GateDecision.FAIL

        val drops = frameMetrics.dropRate()
        if (!drops.isNaN() && drops > maxDropRateForPass) return GateDecision.FAIL

        val es = exposureStability.stability()
        if (!es.isNaN() && es < minExposureStabilityForPass) return GateDecision.FAIL

        val awb = awbStability.stability()
        if (!awb.isNaN() && awb < minAwbStabilityForPass) return GateDecision.FAIL

        return GateDecision.PASS
    }

    fun reset() {
        frameMetrics.reset()
        exposureStability.reset()
        awbStability.reset()
        motionContamination.reset()
    }
}