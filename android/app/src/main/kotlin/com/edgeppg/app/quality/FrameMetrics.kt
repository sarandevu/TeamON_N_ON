package com.edgeppg.app.quality

import kotlin.math.max

/**
 * Stage 3 — Frame timing metrics.
 *
 * Records the timestamp_ns of each frame that passed the AE/AWB lock and
 * computes:
 *  - effective FPS over the rolling window
 *  - drop rate (frames that fell outside the expected cadence)
 *  - jitter (std-dev of inter-frame deltas)
 *
 * Rolling window is the last [windowSize] frames (default 120 = 4 s at 30 fps).
 * All values are NaN until enough samples are collected; we never fabricate.
 */
class FrameMetrics(private val windowSize: Int = 120) {

    private val tsNs: LongArray = LongArray(windowSize)
    private var count: Int = 0
    private var head: Int = 0

    /** Record a frame's sensor timestamp (ns). */
    fun record(timestampNs: Long) {
        tsNs[head] = timestampNs
        head = (head + 1) % windowSize
        if (count < windowSize) count++
    }

    /**
     * Compute effective FPS over the rolling window. NaN if fewer than
     * 2 frames recorded.
     */
    fun fps(): Float {
        if (count < 2) return Float.NaN
        val first = firstTs()
        val last = lastTs()
        val spanNs = (last - first).coerceAtLeast(1L)
        val frames = (count - 1).toDouble()
        return (frames * 1_000_000_000.0 / spanNs).toFloat()
    }

    /**
     * Drop rate over the rolling window, defined as
     *     (expectedFrames - actualFrames) / expectedFrames
     * where `expectedFrames` is derived from the median inter-frame delta.
     *
     * NaN if fewer than 4 frames recorded (not enough for a stable median).
     */
    fun dropRate(): Float {
        if (count < 4) return Float.NaN
        // Destructuring a kotlin.Pair from built-in-Kotlin's compiler
        // infers `Any?`; that breaks `<= 0` and `/`. Pull the
        // components out by their typed accessors instead.
        val dm = deltasWithMedian()
        val median: Long = dm.second
        if (median <= 0) return Float.NaN
        val totalNs = (lastTs() - firstTs()).coerceAtLeast(1L)
        val expected = (totalNs.toDouble() / median).toInt()
        val actual = count - 1
        if (expected <= 0) return Float.NaN
        val drops = max(0, expected - actual)
        return (drops.toFloat() / expected.toFloat()).coerceIn(0f, 1f)
    }

    /** Jitter = std-dev of inter-frame deltas, in milliseconds. NaN if < 4 frames. */
    fun jitterMs(): Float {
        if (count < 4) return Float.NaN
        val (deltas, _) = deltasWithMedian()
        val mean = deltas.sum().toDouble() / deltas.size
        var acc = 0.0
        for (d in deltas) {
            val diff = d - mean
            acc += diff * diff
        }
        val sdNs = Math.sqrt(acc / deltas.size)
        return (sdNs / 1_000_000.0).toFloat()
    }

    /**
     * Median inter-frame delta (ns). NaN if < 4 frames. Useful for
     * downstream diagnostics.
     */
    fun medianDeltaNs(): Float {
        if (count < 4) return Float.NaN
        val (deltas, median) = deltasWithMedian()
        // median is Long; explicit cast avoids any type-inference quirk
        // when destructuring a generic Pair from the stdlib.
        return (median as Long).toFloat()
    }

    /**
     * Compute (deltas, median) in one pass. Caller treats median as the
     * "expected cadence" reference.
     */
    private fun deltasWithMedian(): Pair<LongArray, Long> {
        val n = count - 1
        val deltas = LongArray(n)
        if (count < windowSize) {
            for (i in 0 until n) {
                deltas[i] = tsNs[i + 1] - tsNs[i]
            }
        } else {
            for (i in 0 until n) {
                val a = (head + i) % windowSize
                val b = (head + i + 1) % windowSize
                deltas[i] = tsNs[b] - tsNs[a]
            }
        }
        // Guard against non-monotonic (rare on LEGACY devices).
        for (i in deltas.indices) if (deltas[i] < 0) deltas[i] = 0
        // Median via partial sort.
        val sortedCopy = deltas.copyOf()
        java.util.Arrays.sort(sortedCopy)
        return Pair(deltas, sortedCopy[sortedCopy.size / 2])
    }

    val sampleCount: Int get() = count

    private fun firstTs(): Long {
        // Oldest sample is at (head + windowSize - count) % windowSize,
        // but easier: smallest index among the count entries when count < windowSize.
        if (count < windowSize) {
            // samples occupy 0..count-1 since head == count
            return tsNs[0]
        }
        return tsNs[head]  // head is the next-write slot, which holds the oldest sample
    }

    private fun lastTs(): Long {
        if (count < windowSize) {
            return tsNs[(count - 1).coerceAtLeast(0)]
        }
        return tsNs[(head - 1 + windowSize) % windowSize]
    }

    fun reset() {
        count = 0
        head = 0
    }
}
