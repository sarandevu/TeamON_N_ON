package com.edgeppg.app.optical

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.os.Handler
import android.os.Looper
import android.util.AttributeSet
import android.view.View
import com.edgeppg.app.challenge.OpticalColor

/**
 * Stage 15 Task 3 — Optical flash overlay.
 *
 * Per FR-OPT-1 the device must project a fresh, randomized optical
 * sequence on screen. The renderer is a single full-window [View]
 * that paints a solid color over the entire layout for a short
 * window (default 100..500 ms, per `PR-VAL-1`).
 *
 * The View is normally [View.GONE]. The [SessionController] (or the
 * behaviour-runner coroutine, Stage 15 Task 4) calls
 * [showFlash] with a color / delta / duration; the overlay paints
 * itself, then auto-hides after the duration expires.
 *
 * The "delta" is a brightness hint (0..100 percent above ambient).
 * The Activity controls whether delta is implemented as full-white
 * (delta=100) vs. dim (delta < 50) — at the [View]-paint level
 * we just draw a solid color. The camera-side correlation
 * (FR-OPT-2 / FR-OPT-3) is the responsibility of the rPPG DSP, not
 * this overlay.
 */
class OpticalFlashOverlay @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val paint = Paint().apply {
        style = Paint.Style.FILL
    }
    private var currentColor: Int = Color.TRANSPARENT
    private val mainHandler = Handler(Looper.getMainLooper())

    init {
        visibility = GONE
        setWillNotDraw(false)
    }

    /**
     * Show the flash for [durationMs] ms. Color is one of [OpticalColor];
     * the brightness delta is included so future renderers can scale
     * the RGB triple, but at the [View]-paint level we draw the
     * full color regardless of delta.
     */
    fun showFlash(color: OpticalColor, deltaPct: Int, durationMs: Long) {
        val argb = colorToArgb(color, deltaPct)
        mainHandler.removeCallbacksAndMessages(HIDE_TOKEN)
        currentColor = argb
        invalidate()
        visibility = VISIBLE
        mainHandler.postDelayed({
            currentColor = Color.TRANSPARENT
            invalidate()
            visibility = GONE
        }, HIDE_TOKEN, durationMs)
    }

    /** Cancel any pending flash. Safe to call from lifecycle hooks. */
    fun cancel() {
        mainHandler.removeCallbacksAndMessages(HIDE_TOKEN)
        currentColor = Color.TRANSPARENT
        invalidate()
        visibility = GONE
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (currentColor != Color.TRANSPARENT) {
            canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint.apply {
                color = currentColor
            })
        }
    }

    /**
     * Map the documented (color, deltaPct) pair to an opaque ARGB
     * color. The delta currently controls alpha for warm/cool, full
     * saturation for white — the verifier-side correlation only
     * sees RGB at 8-bit and is robust to that.
     */
    private fun colorToArgb(color: OpticalColor, deltaPct: Int): Int = when (color) {
        OpticalColor.WHITE -> {
            // Brightness via alpha on a near-white tint.
            val a = (deltaPct.coerceIn(0, 100) * 255 / 100).coerceIn(0, 255)
            Color.argb(a, 255, 255, 255)
        }
        OpticalColor.WARM -> {
            val a = (deltaPct.coerceIn(0, 100) * 255 / 100).coerceIn(0, 255)
            Color.argb(a, 255, 200, 180)
        }
        OpticalColor.COOL -> {
            val a = (deltaPct.coerceIn(0, 100) * 255 / 100).coerceIn(0, 255)
            Color.argb(a, 180, 200, 255)
        }
    }

    companion object {
        // A single tagged-token hide callback so concurrent flashes
        // don't pile up scheduled hides. The token is a private
        // Any so external code can't accidentally collide.
        private val HIDE_TOKEN: Any = Any()
    }
}
