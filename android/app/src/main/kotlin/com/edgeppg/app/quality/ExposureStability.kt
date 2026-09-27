package com.edgeppg.app.quality

import kotlin.math.sqrt

/**
 * Stage 3 — Exposure stability.
 *
 * Computes the coefficient of variation of `SENSOR_EXPOSURE_TIME *
 * SENSOR_SENSITIVITY` over a rolling window, then returns `1 - CoV` as
 * the stability score (1 = perfectly stable, 0 = wild drift).
 *
 * Higher `CoV` indicates AE is still actively compensating (i.e. lock has
 * not been effective or scene is changing). The Quality Gate (Stage 3)
 * uses this as one of the inputs to the "contamination / instability"
 * routing decision.
 *
 * Camera2 reports null values on LEGACY-level devices or for parameters
 * the device does not expose. We treat null as "no sample" (skip), and
 * return NaN if fewer than [minSamples] samples have been observed.
 */
class ExposureStability(
    private val windowSize: Int = 120,
    private val minSamples: Int = 8,
) {
    private val samples: DoubleArray = DoubleArray(windowSize)
    private var count: Int = 0
    private var head: Int = 0

    /**
     * Record a single (exposureNs, sensitivityIso) pair. Either may be
     * null to indicate "not reported by the device this frame" — we
     * silently skip such samples.
     */
    fun record(exposureNs: Long?, sensitivityIso: Int?) {
        if (exposureNs == null || sensitivityIso == null) return
        if (exposureNs <= 0L || sensitivityIso <= 0) return
        // "Exposure value" proportional to the amount of light gathered
        // (longer exposure OR higher ISO both = brighter image).
        val ev = exposureNs.toDouble() * sensitivityIso.toDouble()
        samples[head] = ev
        head = (head + 1) % windowSize
        if (count < windowSize) count++
    }

    /**
     * 1 - CoV(EV). NaN if fewer than [minSamples] samples recorded.
     */
    fun stability(): Float {
        if (count < minSamples) return Float.NaN
        var sum = 0.0
        for (i in 0 until count) sum += samples[i]
        val mean = sum / count
        if (mean <= 0.0) return Float.NaN
        var acc = 0.0
        for (i in 0 until count) {
            val d = samples[i] - mean
            acc += d * d
        }
        val sd = sqrt(acc / count)
        val cov = sd / mean
        val s = (1.0 - cov).coerceIn(0.0, 1.0)
        return s.toFloat()
    }

    fun reset() {
        count = 0
        head = 0
    }
}