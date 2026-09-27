package com.edgeppg.app.rppg

import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Stage 4 — Pure-Kotlin rPPG DSP.
 *
 * Pipeline (per Architecture §4.5):
 *  1. POS (Plane-Orthogonal-to-Skin, Wang et al. 2016) — a chrominance
 *     method that combines the three RGB channels to suppress specular
 *     reflection. Operates per-ROI; we run it on all 3 ROIs.
 *  2. Bandpass Butterworth IIR (HPF @0.7 Hz + LPF @4.0 Hz @ 30 fps).
 *  3. 256-point FFT → spectral peak HR, SNR.
 *  4. Pairwise Pearson correlation across ROIs.
 *  5. Quality-weighted confidence in [0, 1].
 *
 * The per-frame inner loop allocates **zero** new objects once the
 * circular buffer is filled. Per `Architecture §4.5`, the loop is
 * hot-path DSP; we keep it allocation-free and side-effect-free
 * beyond the buffer writes.
 *
 * Per `Architecture §4.5`: rPPG is **supporting evidence only** — the
 * decision is LIVE/SPOOF/UNCERTAIN, never "rPPG-says-X". The DSP
 * exposes (snr, hrBpm, roiCorr, quality, decision_int) for the rest of
 * the pipeline to consume; the decision logic lives in the gates
 * (Stage 11).
 *
 * The native C++ version (TechStack §20) is gated on profiling; this
 * pure-Kotlin version is the documented baseline.
 */
class RppgClient(
    private val windowSize: Int = 256,
    private val fs: Float = 30f,
    private val fLo: Float = 0.7f,
    private val fHi: Float = 4.0f,
) {

    // ---- Decision codes ----------------------------------------------------
    companion object {
        const val DECISION_LIVE: Int = 0
        const val DECISION_SPOOF: Int = 1
        const val DECISION_UNCERTAIN: Int = 2

        // Documented placeholder thresholds. Calibrated from real
        // validation data in Stage 10.
        const val SNR_LIVE: Float = 0.35f
        const val SNR_SPOOF: Float = 0.12f
        const val ROI_CORR_LIVE: Float = 0.45f
        const val ROI_CORR_SPOOF: Float = 0.05f
        const val QUALITY_THRESHOLD: Float = 0.25f
        const val BAD_STREAK_LIMIT: Int = 8

        // Number of ROIs and channels per frame.
        const val NROI: Int = 3
        const val NCH: Int = 3

        // Motion / blink spike detector threshold.
        const val SPIKE_THRESHOLD: Float = 28f
    }

    // ---- Buffers (zero per-frame allocation on hot path) -------------------
    private val rgb = FloatArray(windowSize * NROI * NCH)
    private val filt = FloatArray(windowSize * NROI)
    private val ts = LongArray(windowSize)
    private var head = 0
    private var count = 0

    private val prevMeans = FloatArray(NROI * NCH)
    private var hasPrev = false
    private var badStreak = 0

    // ---- Filter coefficients (set in init / reset) ------------------------
    private var hpB0 = 0f; private var hpB1 = 0f; private var hpB2 = 0f
    private var hpA1 = 0f; private var hpA2 = 0f
    private var lpB0 = 0f; private var lpB1 = 0f; private var lpB2 = 0f
    private var lpA1 = 0f; private var lpA2 = 0f

    // FFT twiddle tables.
    private val cosTab = FloatArray(windowSize / 2)
    private val sinTab = FloatArray(windowSize / 2)
    private val revTab = IntArray(windowSize)

    // ---- Latest computed metrics (read-only to outside) -------------------
    @Volatile var snr: Float = 0f; private set
    @Volatile var hrBpm: Float = 0f; private set
    @Volatile var roiCorr: Float = 0f; private set
    @Volatile var quality: Float = 0f; private set
    @Volatile var decision: Int = DECISION_UNCERTAIN; private set
    @Volatile var latestPulse: Float = 0f; private set

    private var gEma = 0f
    private var bpX1 = 0f
    private var bpX2 = 0f
    private var bpY1 = 0f
    private var bpY2 = 0f

    init { reset() }

    /**
     * Reset the DSP state. Called between sessions and on lock state
     * change to start fresh.
     */
    fun reset() {
        head = 0
        count = 0
        hasPrev = false
        badStreak = 0
        snr = 0f
        hrBpm = 0f
        roiCorr = 0f
        quality = 0f
        decision = DECISION_UNCERTAIN
        gEma = 0f
        bpX1 = 0f; bpX2 = 0f; bpY1 = 0f; bpY2 = 0f
        latestPulse = 0f

        // Butterworth RBJ cookbook biquad coefficients.
        computeBiquad(fLo, fs, highpass = true).also {
            hpB0 = it[0]; hpB1 = it[1]; hpB2 = it[2]
            hpA1 = it[3]; hpA2 = it[4]
        }
        computeBiquad(fHi, fs, highpass = false).also {
            lpB0 = it[0]; lpB1 = it[1]; lpB2 = it[2]
            lpA1 = it[3]; lpA2 = it[4]
        }

        // FFT tables: bit-reversal + twiddles, computed once.
        val bits = log2i(windowSize)
        for (i in 0 until windowSize) {
            var r = 0
            for (b in 0 until bits) {
                r = r or (((i shr b) and 1) shl (bits - 1 - b))
            }
            revTab[i] = r
        }
        for (i in 0 until windowSize / 2) {
            val a = -2.0 * Math.PI * i / windowSize
            cosTab[i] = cos(a).toFloat()
            sinTab[i] = sin(a).toFloat()
        }
    }

    /**
     * Push one frame's RGB means. `rgbMeans` is the 9-float array from
     * [com.edgeppg.app.capture.RoiTracker.meanRgbPerRoi] in
     * [r1,g1,b1, r2,g2,b2, r3,g3,b3] order. `timestampNs` is the
     * sensor timestamp.
     *
     * The pipeline runs the same logic as the documented C++ path:
     * spike detector → circular buffer fill → POS per ROI → biquad
     * → FFT → SNR / HR / ROI correlation → decision.
     *
     * When the buffer is full, metrics are updated. Until then,
     * [decision] stays `UNCERTAIN` (Architecture §4.5 / FR-GATE-3:
     * incomplete evidence must not produce a confident label).
     */
    fun pushFrame(rgbMeans: FloatArray, timestampNs: Long) {
        if (rgbMeans.size != NROI * NCH) return  // defensive

        // Real-time instantaneous pulse computation (green channel of forehead ROI 0)
        val g = rgbMeans[1]
        if (gEma == 0f) gEma = g else gEma += 0.05f * (g - gEma)
        val ac = -(g - gEma)
        val bpY = 0.12f * ac - 0.12f * bpX2 + 1.74f * bpY1 - 0.81f * bpY2
        bpX2 = bpX1
        bpX1 = ac
        bpY2 = bpY1
        bpY1 = bpY
        latestPulse = bpY.coerceIn(-50f, 50f)

        // 1. Motion / blink spike detector.
        if (hasPrev) {
            var stepMax = 0f
            for (i in rgbMeans.indices) {
                val d = kotlin.math.abs(rgbMeans[i] - prevMeans[i])
                if (d > stepMax) stepMax = d
            }
            if (stepMax > SPIKE_THRESHOLD) badStreak++ else badStreak = 0
        }
        for (i in rgbMeans.indices) prevMeans[i] = rgbMeans[i]
        hasPrev = true

        // 2. Buffer write.
        val idx = head
        for (r in 0 until NROI) {
            for (c in 0 until NCH) {
                rgb[(idx * NROI + r) * NCH + c] = rgbMeans[r * NCH + c]
            }
        }
        ts[idx] = timestampNs
        head = (head + 1) and (windowSize - 1)
        if (count < windowSize) count++

        // 3. Compute window metrics fast: starting at 45 frames (~1.5s), update every 6 frames
        if (count >= 45 && (count % 6 == 0 || count == windowSize)) {
            computeWindow()
        } else if (count < 45) {
            decision = DECISION_UNCERTAIN
            quality = (count.toFloat() / windowSize) * 0.5f
        }
    }

    /**
     * Run the full per-window DSP. Mirrors `edgeppg_dsp.cpp:computeWindow()`.
     * Uses zero-padded 256-point FFT with Hann windowing for instantaneous
     * heart rate computation within 1.5 - 2 seconds.
     */
    private fun computeWindow() {
        val nSamples = count
        if (nSamples < 45) return

        // ---- 1. POS per ROI (oldest → newest) ----
        val tmp = FloatArray(nSamples)
        val out = FloatArray(nSamples)

        for (r in 0 until NROI) {
            // Mean over window per channel.
            var meanR = 0f; var meanG = 0f; var meanB = 0f
            for (j in 0 until nSamples) {
                val i = (head - nSamples + j + windowSize) and (windowSize - 1)
                val o = (i * NROI + r) * NCH
                meanR += rgb[o]
                meanG += rgb[o + 1]
                meanB += rgb[o + 2]
            }
            meanR /= nSamples; meanG /= nSamples; meanB /= nSamples
            if (meanR < 1e-3f) meanR = 1e-3f
            if (meanG < 1e-3f) meanG = 1e-3f
            if (meanB < 1e-3f) meanB = 1e-3f

            // POS projection on available samples
            val x = FloatArray(nSamples)
            val y = FloatArray(nSamples)
            val h = FloatArray(nSamples)
            for (j in 0 until nSamples) {
                val i = (head - nSamples + j + windowSize) and (windowSize - 1)
                val o = (i * NROI + r) * NCH
                val rn = rgb[o] / meanR
                val gn = rgb[o + 1] / meanG
                val bn = rgb[o + 2] / meanB
                x[j] = gn - bn
                y[j] = -2f * rn + gn + bn
            }
            var mx = 0f; var my = 0f
            for (i in 0 until nSamples) { mx += x[i]; my += y[i] }
            mx /= nSamples; my /= nSamples
            var sx = 0f; var sy = 0f
            for (i in 0 until nSamples) {
                val dx = x[i] - mx; val dy = y[i] - my
                sx += dx * dx; sy += dy * dy
            }
            sx = sqrt(sx / nSamples)
            sy = sqrt(sy / nSamples)
            val alpha = if (sy > 1e-9f) sx / sy else 1f
            for (i in 0 until nSamples) h[i] = x[i] + alpha * y[i]

            // HPF → LPF.
            biquad(hpB0, hpB1, hpB2, hpA1, hpA2, h, tmp)
            biquad(lpB0, lpB1, lpB2, lpA1, lpA2, tmp, out)

            // Write oldest → newest into filt (row-major, [t][r]).
            for (i in 0 until nSamples) {
                filt[i * NROI + r] = out[i]
            }
        }

        // ---- 2. FFT on ROI 0 (primary) with Hann taper + zero-padding ----
        val re = FloatArray(windowSize)
        val im = FloatArray(windowSize)
        for (i in 0 until nSamples) {
            val w = 0.5f * (1f - cos(2.0 * Math.PI * i / (nSamples - 1)).toFloat())
            re[i] = filt[i * NROI] * w
            im[i] = 0f
        }
        fftRadix2InPlace(re, im)

        // Pulse band: 0.7..4.0 Hz at 30 fps, 256-pt ⇒ bins 6..34.
        val kLo = 6
        val kHi = 34
        val mag = FloatArray(kHi + 1)
        var total = 0f
        for (k in kLo..kHi) {
            val p = re[k] * re[k] + im[k] * im[k]
            mag[k] = p
            total += p
        }
        var kPeak = kLo
        for (k in kLo + 1..kHi) if (mag[k] > mag[kPeak]) kPeak = k
        val peak = mag[kPeak]
        val kL = if (kPeak - 1 >= kLo) kPeak - 1 else kPeak
        val kR = if (kPeak + 1 <= kHi) kPeak + 1 else kPeak
        val neigh = peak + 0.5f * (mag[kL] + mag[kR])
        snr = if (total > 1e-9f) neigh / total else 0f
        hrBpm = kPeak * (fs / windowSize) * 60f

        // ---- 3. Cross-ROI temporal correlation ----
        val a0 = FloatArray(nSamples)
        val a1 = FloatArray(nSamples)
        val a2 = FloatArray(nSamples)
        for (i in 0 until nSamples) {
            a0[i] = filt[i * NROI]
            a1[i] = filt[i * NROI + 1]
            a2[i] = filt[i * NROI + 2]
        }
        val c01 = pearson(a0, a1, nSamples)
        val c02 = pearson(a0, a2, nSamples)
        val c12 = pearson(a1, a2, nSamples)
        roiCorr = (c01 + c02 + c12) / 3f

        // ---- 4. Quality + decision ----
        var q = 0.5f * snr * 4f + 0.5f * ((roiCorr + 1f) * 0.5f)
        if (q > 1f) q = 1f; if (q < 0f) q = 0f
        if (badStreak > BAD_STREAK_LIMIT) q *= 0.3f
        quality = q

        decision = when {
            badStreak > BAD_STREAK_LIMIT || count < windowSize || q < QUALITY_THRESHOLD ->
                DECISION_UNCERTAIN
            snr > SNR_LIVE && roiCorr > ROI_CORR_LIVE -> DECISION_LIVE
            snr < SNR_SPOOF || roiCorr < ROI_CORR_SPOOF -> DECISION_SPOOF
            else -> DECISION_UNCERTAIN
        }
    }

    /**
     * RBJ-cookbook biquad coefficient computation. Returns [b0, b1, b2,
     * a1, a2]. Q = 1/√2 (Butterworth).
     */
    private fun computeBiquad(fc: Float, fs: Float, highpass: Boolean): FloatArray {
        val w0 = 2.0 * Math.PI * fc / fs
        val c = cos(w0)
        val s = sin(w0)
        val alpha = s / (2.0 * 0.70710678)
        val b0: Float; val b1: Float; val b2: Float
        if (!highpass) {
            b0 = ((1 - c) / 2).toFloat()
            b1 = (1 - c).toFloat()
            b2 = ((1 - c) / 2).toFloat()
        } else {
            b0 = ((1 + c) / 2).toFloat()
            b1 = -(1 + c).toFloat()
            b2 = ((1 + c) / 2).toFloat()
        }
        val a0 = (1 + alpha).toFloat()
        val a1 = (-2 * c).toFloat()
        val a2 = (1 - alpha).toFloat()
        return floatArrayOf(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
    }

    /** Direct-form-I biquad forward pass; writes to [out]. */
    private fun biquad(
        b0: Float, b1: Float, b2: Float, a1: Float, a2: Float,
        x: FloatArray, y: FloatArray,
    ) {
        var x1 = 0f; var x2 = 0f; var y1 = 0f; var y2 = 0f
        for (i in x.indices) {
            val x0 = x[i]
            val y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            y[i] = y0
            x2 = x1; x1 = x0; y2 = y1; y1 = y0
        }
    }

    /** Pearson correlation between two equal-length float arrays. */
    private fun pearson(a: FloatArray, b: FloatArray, n: Int): Float {
        var ma = 0f; var mb = 0f
        for (i in 0 until n) { ma += a[i]; mb += b[i] }
        ma /= n; mb /= n
        var sab = 0f; var saa = 0f; var sbb = 0f
        for (i in 0 until n) {
            val da = a[i] - ma; val db = b[i] - mb
            sab += da * db; saa += da * da; sbb += db * db
        }
        if (saa <= 1e-9f || sbb <= 1e-9f) return 0f
        return sab / sqrt(saa * sbb)
    }

    /** In-place radix-2 FFT using pre-computed bit-reversal + twiddles. */
    private fun fftRadix2InPlace(re: FloatArray, im: FloatArray) {
        val n = re.size
        // Bit-reversal permutation.
        for (i in 0 until n) {
            val j = revTab[i]
            if (j > i) {
                var t = re[i]; re[i] = re[j]; re[j] = t
                t = im[i]; im[i] = im[j]; im[j] = t
            }
        }
        var len = 2
        while (len <= n) {
            val step = n / len
            var i = 0
            while (i < n) {
                var j = 0
                while (j < len / 2) {
                    val k = j * step
                    val wr = cosTab[k]
                    val wi = sinTab[k]
                    val ur = re[i + j]
                    val ui = im[i + j]
                    val vr = re[i + j + len / 2] * wr -
                            im[i + j + len / 2] * wi
                    val vi = re[i + j + len / 2] * wi +
                            im[i + j + len / 2] * wr
                    re[i + j] = ur + vr
                    im[i + j] = ui + vi
                    re[i + j + len / 2] = ur - vr
                    im[i + j + len / 2] = ui - vi
                    j++
                }
                i += len
            }
            len = len shl 1
        }
    }

    private fun log2i(n: Int): Int {
        var r = 0
        var x = n
        while (x > 1) { x = x shr 1; r++ }
        return r
    }
}