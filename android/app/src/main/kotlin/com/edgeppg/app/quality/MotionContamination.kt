package com.edgeppg.app.quality

/**
 * Stage 3 — Per-frame RGB step detector (blink / motion contamination).
 *
 * The rPPG pipeline (Stage 4) trusts that the 3 ROIs see a continuous
 * skin reflection. A blink or a fast head motion produces a step change
 * in mean RGB larger than the cardiac-signal amplitude — feeding those
 * frames through the POS path would destroy SNR.
 *
 * Policy:
 *  - When the per-frame max-channel step exceeds [stepThreshold] counts
 *    (default 28, in 0..255 YUV space), count it as a "spike".
 *  - When [streakThreshold] consecutive spikes occur (default 3), emit
 *    `contaminationFlag = true` to the Quality Gate. The Gate then routes
 *    the session to UNCERTAIN (Architecture §8 / FR-GATE-3).
 *  - A single non-spike resets the streak counter.
 *
 * Configuration is provided by the Quality Gate so it can be tuned
 * without changing this class.
 */
class MotionContamination(
    private val stepThreshold: Float = 28f,
    private val streakThreshold: Int = 3,
) {
    @Volatile private var streak: Int = 0
    @Volatile private var contaminationFlag: Boolean = false
    private var prev: FloatArray? = null  // [r1,g1,b1, r2,g2,b2, r3,g3,b3]

    /** Feed one frame's RGB means. Returns the contamination flag AFTER update. */
    fun observe(rgbMeans: FloatArray): Boolean {
        val p = prev
        if (p == null || p.size != rgbMeans.size) {
            prev = rgbMeans.copyOf()
            streak = 0
            return contaminationFlag
        }
        var stepMax = 0f
        for (i in rgbMeans.indices) {
            val d = kotlin.math.abs(rgbMeans[i] - p[i])
            if (d > stepMax) stepMax = d
        }
        // Copy for next comparison (caller may reuse the buffer).
        for (i in rgbMeans.indices) p[i] = rgbMeans[i]
        if (stepMax > stepThreshold) {
            streak++
        } else {
            streak = 0
            contaminationFlag = false
            return false
        }
        if (streak >= streakThreshold) {
            contaminationFlag = true
        }
        return contaminationFlag
    }

    fun isContaminated(): Boolean = contaminationFlag

    fun reset() {
        streak = 0
        contaminationFlag = false
        prev = null
    }
}