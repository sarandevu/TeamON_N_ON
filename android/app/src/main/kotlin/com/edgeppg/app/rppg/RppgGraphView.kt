package com.edgeppg.app.rppg

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.util.AttributeSet
import android.util.TypedValue
import android.view.View
import kotlin.math.abs
import kotlin.math.max

/**
 * Real-time rPPG Photoplethysmogram (PPG) Pulse Wave Graph.
 *
 * Visualizes the optical blood volume pulse (BVP) wave as cardiac perfusion
 * cycles through the facial microvasculature.
 *
 * Features:
 *  - Zero heap allocation in [onDraw] (pre-allocated Path, Paint, and buffers).
 *  - Auto-ranging adaptive amplitude scaling.
 *  - Glowing pulse wave stroke with cyan-to-emerald gradient.
 *  - Flatline state when face is lost / undetected.
 */
class RppgGraphView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    private val capacity = 100
    private val buffer = FloatArray(capacity)
    private var writeIdx = 0
    private var isFlatline = true
    private var sampleCount = 0

    // Drawing resources
    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF0C1322.toInt()
        style = Paint.Style.FILL
    }
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF1E2D4A.toInt()
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
    }
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF162238.toInt()
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
    }
    private val wavePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(2.5f)
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xFF34D399.toInt()
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF94A3B8.toInt()
        textSize = dp(10f)
    }
    private val statusPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFFEF4444.toInt()
        textSize = dp(10f)
        textAlign = Paint.Align.CENTER
    }
    private val flatPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF475569.toInt()
        style = Paint.Style.STROKE
        strokeWidth = dp(1.5f)
    }

    private val wavePath = Path()
    private val bgRect = RectF()
    private var currentGradient: LinearGradient? = null
    private var lastWidth = 0
    private var lastHeight = 0

    private fun dp(v: Float): Float = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics
    )

    fun addSample(sample: Float) {
        buffer[writeIdx] = sample
        writeIdx = (writeIdx + 1) % capacity
        if (sampleCount < capacity) sampleCount++
        isFlatline = false
        postInvalidateOnAnimation()
    }

    fun setFlatline(flat: Boolean) {
        if (isFlatline != flat) {
            isFlatline = flat
            if (flat) {
                sampleCount = 0
                for (i in 0 until capacity) buffer[i] = 0f
            }
            postInvalidateOnAnimation()
        }
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        lastWidth = w
        lastHeight = h
        bgRect.set(dp(1f), dp(1f), w - dp(1f), h - dp(1f))
        currentGradient = LinearGradient(
            0f, 0f, w.toFloat(), 0f,
            intArrayOf(0xFF06B6D4.toInt(), 0xFF10B981.toInt(), 0xFF34D399.toInt()),
            null,
            Shader.TileMode.CLAMP
        )
        wavePaint.shader = currentGradient
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0 || h <= 0) return

        val radius = dp(10f)
        // Draw background container
        canvas.drawRoundRect(bgRect, radius, radius, bgPaint)
        canvas.drawRoundRect(bgRect, radius, radius, borderPaint)

        // Draw horizontal center gridline
        val midY = h / 2f
        canvas.drawLine(dp(12f), midY, w - dp(12f), midY, gridPaint)

        // Header text
        canvas.drawText("PULSE WAVE (rPPG)", dp(12f), dp(16f), textPaint)

        if (isFlatline || sampleCount < 5) {
            // Draw flatline in red/gray
            canvas.drawLine(dp(12f), midY, w - dp(12f), midY, flatPaint)
            statusPaint.color = 0xFFF87171.toInt()
            canvas.drawText("NO FACE DETECTED • ALIGN FACE IN FRAME", w / 2f, midY - dp(6f), statusPaint)
            return
        }

        // Compute adaptive peak amplitude for proportional scaling
        var maxAmp = 0.5f
        for (i in 0 until capacity) {
            val a = abs(buffer[i])
            if (a > maxAmp) maxAmp = a
        }

        val padX = dp(12f)
        val drawW = w - padX * 2f
        val maxH = (h / 2f) - dp(14f)

        wavePath.reset()
        var lastX = 0f
        var lastY = midY

        val stepX = drawW / (capacity - 1)
        for (i in 0 until capacity) {
            val bufIdx = (writeIdx + i) % capacity
            val x = padX + i * stepX
            val rawVal = buffer[bufIdx]
            val normY = (rawVal / maxAmp).coerceIn(-1.2f, 1.2f)
            val y = midY - normY * maxH

            if (i == 0) {
                wavePath.moveTo(x, y)
            } else {
                wavePath.lineTo(x, y)
            }
            lastX = x
            lastY = y
        }

        canvas.drawPath(wavePath, wavePaint)

        // Draw leading live pulse beacon dot
        canvas.drawCircle(lastX, lastY, dp(3.5f), dotPaint)
    }
}
