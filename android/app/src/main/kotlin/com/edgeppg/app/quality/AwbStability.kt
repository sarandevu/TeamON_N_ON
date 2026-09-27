package com.edgeppg.app.quality

import kotlin.math.sqrt

/**
 * Stage 3 — AWB (auto white balance) stability.
 *
 * Watches the R/G and B/G ratios over a rolling window and computes
 * `1 - mean(CoV(R/G), CoV(B/G))` as the stability score.
 *
 * Camera2 reports AWB gains as a 4-tuple (R, G_even, G_odd, B) on most
 * devices but the field is null on LEGACY-level cameras. When null we
 * return NaN — the Quality Gate must treat this as "no AWB evidence",
 * not "stable AWB" (Architecture §11: never silently zero-fill).
 */
class AwbStability(
    private val windowSize: Int = 120,
    private val minSamples: Int = 8,
) {
    private val rgSamples: DoubleArray = DoubleArray(windowSize)
    private val bgSamples: DoubleArray = DoubleArray(windowSize)
    private var count: Int = 0
    private var head: Int = 0

    /** Record one (r, gEven, b) tuple. Pass null to skip. */
    fun record(r: Float?, gEven: Float?, b: Float?) {
        if (r == null || gEven == null || b == null) return
        if (gEven <= 0f) return
        val rg = r.toDouble() / gEven.toDouble()
        val bg = b.toDouble() / gEven.toDouble()
        rgSamples[head] = rg
        bgSamples[head] = bg
        head = (head + 1) % windowSize
        if (count < windowSize) count++
    }

    /** 1 - mean(CoV(R/G), CoV(B/G)). NaN when fewer than minSamples. */
    fun stability(): Float {
        if (count < minSamples) return Float.NaN
        val rgCov = cov(rgSamples)
        val bgCov = cov(bgSamples)
        if (rgCov.isNaN() || bgCov.isNaN()) return Float.NaN
        val s = 1.0 - 0.5 * (rgCov + bgCov)
        return s.coerceIn(0.0, 1.0).toFloat()
    }

    private fun cov(xs: DoubleArray): Double {
        var sum = 0.0
        for (i in 0 until count) sum += xs[i]
        val mean = sum / count
        if (mean <= 0.0) return Double.NaN
        var acc = 0.0
        for (i in 0 until count) {
            val d = xs[i] - mean
            acc += d * d
        }
        val sd = sqrt(acc / count)
        return sd / mean
    }

    fun reset() {
        count = 0
        head = 0
    }
}