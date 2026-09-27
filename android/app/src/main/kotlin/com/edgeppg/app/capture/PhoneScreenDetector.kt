package com.edgeppg.app.capture

import android.graphics.Rect
import android.media.Image
import com.edgeppg.app.Log
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.label.ImageLabel
import com.google.mlkit.vision.label.ImageLabeler
import com.google.mlkit.vision.label.ImageLabeling
import com.google.mlkit.vision.label.defaults.ImageLabelerOptions
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * Real-time Phone and Secondary Screen Presentation Attack Detector.
 *
 * Implements multi-layered physical and algorithmic detection:
 *  1. ML Kit Image Labeling / Object Recognition:
 *     Actively identifies electronic displays, mobile phones, smartphones,
 *     cellular devices, screens, monitors, and tablets visible in frame.
 *  2. 3D Facial Mesh Planarity Collapse:
 *     A genuine human face exhibits 3D anatomical relief (nose tip extends
 *     30-60mm forward from the eye/cheek plane, normalized depth relief > 0.12).
 *     On a mobile phone screen or printed photo, the face is rendered on a
 *     flat 2D plane: depth variance and facial curvature collapse to ~0.
 *  3. Phone Bezel / Screen Border Edge Analysis:
 *     Detects high-contrast straight rectangular boundaries (phone bezels)
 *     framing the face in the camera YUV luminance buffer.
 *
 * When any layer detects a phone/secondary screen, the detector latches
 * [isPhoneDetected] = true, triggering immediate and uncompromising SPOOF
 * routing in [SessionController] and [DecisionEngine].
 */
class PhoneScreenDetector(
    private val labelConfidenceThreshold: Float = 0.40f,
    private val minConsecutiveDetections: Int = 2,
    private val labeler: ImageLabeler = ImageLabeling.getClient(
        ImageLabelerOptions.Builder()
            .setConfidenceThreshold(0.35f)
            .build()
    ),
) {

    data class Result(
        val isPhoneDetected: Boolean,
        val reason: String,
        val confidence: Float,
        val planarityScore: Float = 0f,
        val bezelScore: Float = 0f,
        val detectedLabels: List<String> = emptyList(),
    )

    companion object {
        // Keywords indicating a mobile phone, tablet, screen, or electronic presentation device
        private val PHONE_KEYWORDS = setOf(
            "phone", "mobile phone", "cell phone", "cellphone", "smartphone",
            "telephone", "screen", "display device", "computer monitor",
            "display", "monitor", "television", "tablet computer", "tablet",
            "gadget", "handheld device", "electronic device", "electronics",
            "multimedia", "cellular phone"
        )
    }

    private val isRunningLabeler = AtomicBoolean(false)
    private var consecutiveDetections = 0
    @Volatile var isPhoneDetected: Boolean = false
        private set
    @Volatile var lastReason: String = ""
        private set

    /** Reset state for a fresh VKYC session. */
    fun reset() {
        consecutiveDetections = 0
        isPhoneDetected = false
        lastReason = ""
    }

    /**
     * Inspect frame for secondary phone / screen presentation attacks.
     *
     * @param image Raw YUV camera image
     * @param rotationDegrees Sensor rotation
     * @param meshPoints 468 3D landmark points [x0, y0, z0, ...] from ML Kit FaceMesh
     * @param faceBox Bounding box of primary face, if any
     */
    fun processFrame(
        image: Image,
        rotationDegrees: Int,
        meshPoints: FloatArray,
        faceBox: Rect?,
    ): Result {
        // Once latched as a phone attack during the session, remain latched.
        if (isPhoneDetected) {
            return Result(
                isPhoneDetected = true,
                reason = lastReason,
                confidence = 0.99f
            )
        }

        var detectedByThisFrame = false
        var primaryReason = ""
        var maxConfidence = 0f

        // --- Layer 1: 3D Facial Mesh Depth Planarity Check ---
        val planarityScore = evaluateMeshPlanarity(meshPoints)
        if (planarityScore > 0.70f) {
            detectedByThisFrame = true
            primaryReason = "planar-mesh-collapse:score=${"%.2f".format(planarityScore)}"
            maxConfidence = max(maxConfidence, planarityScore)
        }

        // --- Layer 2: Phone Bezel & Screen Edge Contour Check ---
        val bezelScore = if (faceBox != null && !faceBox.isEmpty) {
            evaluateScreenBezelEdges(image, faceBox)
        } else 0f
        if (bezelScore > 0.65f) {
            detectedByThisFrame = true
            val r = "screen-bezel-detected:score=${"%.2f".format(bezelScore)}"
            primaryReason = if (primaryReason.isEmpty()) r else "$primaryReason|$r"
            maxConfidence = max(maxConfidence, bezelScore)
        }

        // --- Layer 3: ML Kit Image Labeling / Electronic Device Recognition ---
        val labelsFound = mutableListOf<String>()
        if (!isRunningLabeler.get()) {
            if (isRunningLabeler.compareAndSet(false, true)) {
                try {
                    val input = InputImage.fromMediaImage(image, rotationDegrees)
                    val task = labeler.process(input)
                    val labels: List<ImageLabel>? = try {
                        Tasks.await(task, 250, TimeUnit.MILLISECONDS)
                    } catch (_: Exception) {
                        null
                    }
                    if (labels != null) {
                        for (lbl in labels) {
                            val text = lbl.text.lowercase().trim()
                            labelsFound.add("${lbl.text}:${"%.2f".format(lbl.confidence)}")
                            val isMatch = PHONE_KEYWORDS.any { kw ->
                                text == kw || text.contains(kw)
                            }
                            if (isMatch && lbl.confidence >= labelConfidenceThreshold) {
                                detectedByThisFrame = true
                                val r = "device-label:${lbl.text}(${"%.2f".format(lbl.confidence)})"
                                primaryReason = if (primaryReason.isEmpty()) r else "$primaryReason|$r"
                                maxConfidence = max(maxConfidence, lbl.confidence)
                            }
                        }
                    }
                } catch (t: Throwable) {
                    Log.error("detector", "PhoneScreenDetector labeling failed", t)
                } finally {
                    isRunningLabeler.set(false)
                }
            }
        }

        if (detectedByThisFrame) {
            consecutiveDetections++
            Log.stage("detector", "PHONE DETECTED frame-hit #$consecutiveDetections: $primaryReason")
            if (consecutiveDetections >= minConsecutiveDetections || maxConfidence >= 0.85f) {
                isPhoneDetected = true
                lastReason = primaryReason
                Log.stage("detector", "PHONE LATCHED -> SPOOF TRIGGERED: $lastReason")
            }
        } else {
            if (consecutiveDetections > 0) {
                consecutiveDetections--
            }
        }

        return Result(
            isPhoneDetected = isPhoneDetected,
            reason = if (isPhoneDetected) lastReason else primaryReason,
            confidence = maxConfidence,
            planarityScore = planarityScore,
            bezelScore = bezelScore,
            detectedLabels = labelsFound,
        )
    }

    /**
     * Measure 3D anatomical relief vs 2D planar collapse.
     * Returns a score in [0.0, 1.0], where 1.0 = completely flat 2D surface (phone screen/photo),
     * and 0.0 = deep natural 3D human skull anatomy.
     */
    private fun evaluateMeshPlanarity(meshPoints: FloatArray): Float {
        if (meshPoints.size < 468 * 3) return 0f

        // Key landmarks:
        // Nose tip: 1, Nose bridge: 168, Chin: 152, Forehead: 10
        // Left eye outer: 263, Right eye outer: 33
        // Left cheek: 234, Right cheek: 454
        fun pt(idx: Int): FloatArray {
            val off = idx * 3
            return floatArrayOf(meshPoints[off], meshPoints[off + 1], meshPoints[off + 2])
        }

        val noseTip = pt(1)
        val eyeL = pt(263)
        val eyeR = pt(33)
        val cheekL = pt(234)
        val cheekR = pt(454)

        val faceWidth = hypot(cheekR[0] - cheekL[0], cheekR[1] - cheekL[1]).coerceAtLeast(1f)
        if (faceWidth < 40f) return 0f // Face too small / low-res to judge planarity

        // Eye-plane depth midpoint
        val eyeZ = 0.5f * (eyeL[2] + eyeR[2])
        val cheekZ = 0.5f * (cheekL[2] + cheekR[2])
        val baseZ = 0.5f * (eyeZ + cheekZ)

        // Depth relief: distance nose sticks forward from the eye/cheek base
        val depthRelief = abs(noseTip[2] - baseZ)
        val normalizedRelief = depthRelief / faceWidth

        // In a real human face, normalizedRelief is typically 0.12 to 0.35.
        // On a flat phone screen or paper photo, normalizedRelief collapses towards 0.0.
        return when {
            normalizedRelief < 0.045f -> 0.95f // Extremely flat -> Screen / Paper
            normalizedRelief < 0.075f -> 0.75f // Highly planar -> Probable screen replay
            normalizedRelief < 0.100f -> 0.45f // Borderline
            else -> 0.0f                      // Natural 3D relief
        }
    }

    /**
     * Inspect concentric margin outside face bounding box for straight rectangular
     * high-contrast edges (phone chassis / screen bezel).
     */
    private fun evaluateScreenBezelEdges(image: Image, box: Rect): Float {
        val planes = image.planes
        if (planes.isEmpty()) return 0f
        val yBuf = planes[0].buffer
        val yRowStride = planes[0].rowStride
        val imgW = image.width
        val imgH = image.height

        val bw = box.width()
        val bh = box.height()
        if (bw < 50 || bh < 50) return 0f

        // Bezel check zones: 12% to 35% margin to the left and right of face box
        val leftBezelX = (box.left - (bw * 0.25f).toInt()).coerceIn(4, imgW - 8)
        val rightBezelX = (box.right + (bw * 0.25f).toInt()).coerceIn(4, imgW - 8)
        val topBezelY = (box.top - (bh * 0.20f).toInt()).coerceIn(4, imgH - 8)
        val bottomBezelY = (box.bottom + (bh * 0.20f).toInt()).coerceIn(4, imgH - 8)

        var strongEdgeCount = 0
        var totalSamples = 0

        // Vertical gradient scan on left bezel
        var y = box.top
        while (y < box.bottom) {
            val y1 = y.coerceIn(0, imgH - 1)
            val p0 = yBuf.get(y1 * yRowStride + (leftBezelX - 3)).toInt() and 0xFF
            val p1 = yBuf.get(y1 * yRowStride + (leftBezelX + 3)).toInt() and 0xFF
            val gradL = abs(p1 - p0)
            if (gradL > 45) strongEdgeCount++
            totalSamples++
            y += 8
        }

        // Vertical gradient scan on right bezel
        y = box.top
        while (y < box.bottom) {
            val y1 = y.coerceIn(0, imgH - 1)
            val p0 = yBuf.get(y1 * yRowStride + (rightBezelX - 3)).toInt() and 0xFF
            val p1 = yBuf.get(y1 * yRowStride + (rightBezelX + 3)).toInt() and 0xFF
            val gradR = abs(p1 - p0)
            if (gradR > 45) strongEdgeCount++
            totalSamples++
            y += 8
        }

        // Horizontal gradient scan on top bezel
        var x = box.left
        while (x < box.right) {
            val x1 = x.coerceIn(0, imgW - 1)
            val p0 = yBuf.get((topBezelY - 3) * yRowStride + x1).toInt() and 0xFF
            val p1 = yBuf.get((topBezelY + 3) * yRowStride + x1).toInt() and 0xFF
            val gradT = abs(p1 - p0)
            if (gradT > 45) strongEdgeCount++
            totalSamples++
            x += 8
        }

        if (totalSamples == 0) return 0f
        val edgeRatio = strongEdgeCount.toFloat() / totalSamples
        return when {
            edgeRatio > 0.40f -> 0.85f // Distinct rectangular bezel border around face
            edgeRatio > 0.25f -> 0.60f
            else -> 0.0f
        }
    }
}
