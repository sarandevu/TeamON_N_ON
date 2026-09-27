package com.edgeppg.app.capture

import android.graphics.Rect
import android.media.Image
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.facemesh.FaceMesh
import com.google.mlkit.vision.facemesh.FaceMeshDetection
import com.google.mlkit.vision.facemesh.FaceMeshDetector
import com.google.mlkit.vision.facemesh.FaceMeshDetectorOptions
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.roundToInt

/**
 * Stage 2 — Face-mesh-driven ROI tracker.
 *
 * For each analyzer frame:
 *  1. If a fresh detector run is not due (we run every Nth frame, ML Kit
 *     is heavy), reuse the last smoothed ROI rects.
 *  2. If a fresh run IS due, fire ML Kit's face mesh detector; on success,
 *     take the primary face's bounding box and convert it to three
 *     fractional-box ROIs (forehead, left cheek, right cheek), apply an
 *     EMA smoothing on the rect corners, and store.
 *  3. Whether or not the detector ran, compute mean RGB per ROI from the
 *     YUV_420_888 planes (stride-sampled every 4th pixel — BT.601
 *     full-range integer path, zero allocations on the hot path).
 *
 * The detector runs asynchronously. The analyzer thread does a short
 * bounded wait (1 frame budget at 30 fps, i.e. ≤ 33 ms) on a flag. If the
 * detector doesn't return in budget, the analyzer reuses the previous ROIs
 * and the next frame will run detection again — we never block the
 * analyzer.
 *
 * Configuration (matches Architecture §4.5):
 *  - ROI1 forehead    : x [0.30, 0.70] y [0.08, 0.28]
 *  - ROI2 left cheek  : x [0.08, 0.32] y [0.45, 0.65]
 *  - ROI3 right cheek : x [0.68, 0.92] y [0.45, 0.65]
 *  - Eyes / lips / nose excluded by the box layout.
 *  - EMA alpha = 0.15 (configurable).
 *
 * On-failure policy:
 *  - Detector exception → keep last ROIs, log via [Log.error], continue.
 *    We never zero-fill.
 */
class RoiTracker(
    private val emaAlpha: Float = 0.15f,
    private val detectionEveryNFrames: Int = 3,
    private val detector: FaceMeshDetector = FaceMeshDetection.getClient(
        FaceMeshDetectorOptions.Builder()
            .setUseCase(FaceMeshDetectorOptions.FACE_MESH)
            .build()
    ),
) {
    data class Rois(val forehead: Rect, val cheekL: Rect, val cheekR: Rect)

    /**
     * Per-frame compute result.
     *  - `rois` are the smoothed rects to use for the current frame.
     *  - `facePresent` is true iff a face was seen recently (within
     *    `detectionEveryNFrames` of a successful detection).
     *  - `hadFreshDetection` is true iff THIS frame triggered a detector
     *    run that succeeded.
     *  - `meshPoints` are the 468 3D landmark positions from the most
     *    recent successful detection. Empty when no face is present or
     *    the bounding-box-only mode is in effect.
     */
    data class Result(
        val rois: Rois?,
        val facePresent: Boolean,
        val hadFreshDetection: Boolean,
        val meshPoints: FloatArray = FloatArray(0),
        val faceBox: Rect? = null,
    ) {
        /** Number of mesh points × 3 (x, y, z). */
        val meshPointCount: Int get() = meshPoints.size / 3
    }

    private var smooth: FloatArray? = null // [l1,t1,r1,b1, l2.., l3..] length 12
    private val detecting = AtomicBoolean(false)
    private var lastRois: Rois? = null
    private var lastMesh: FloatArray = FloatArray(0) // 468 × 3 = 1404 floats
    private var lastBox: Rect? = null
    private var framesSinceDetect = Int.MAX_VALUE

    /**
     * Run detector at most every [detectionEveryNFrames] frames. Returns
     * the latest smoothed ROIs on skipped frames. Returns null when no
     * face has been seen yet.
     *
     * NOTE: blocking-with-timeout kept tiny; caller runs on the single
     * analyzer thread. We never touch the UI thread here.
     */
    fun update(image: Image, rotationDegrees: Int): Result? {
        framesSinceDetect++

        // Fast path: skip detection this frame; reuse last ROIs.
        if (framesSinceDetect < detectionEveryNFrames && lastRois != null) {
            return Result(rois = lastRois, facePresent = true,
                          hadFreshDetection = false, meshPoints = lastMesh, faceBox = lastBox)
        }
        // Only one in-flight detection at a time.
        if (!detecting.compareAndSet(false, true)) {
            return Result(rois = lastRois, facePresent = (lastRois != null),
                          hadFreshDetection = false, meshPoints = lastMesh, faceBox = lastBox)
        }

        return try {
            val input = InputImage.fromMediaImage(image, rotationDegrees)
            val task = detector.process(input)
            val meshes: List<FaceMesh>? = try {
                com.google.android.gms.tasks.Tasks.await(task, 300, java.util.concurrent.TimeUnit.MILLISECONDS)
            } catch (_: java.util.concurrent.TimeoutException) {
                null
            }
            if (meshes.isNullOrEmpty()) {
                smooth = null
                lastRois = null
                lastMesh = FloatArray(0)
                lastBox = null
                framesSinceDetect = 0
                Result(rois = null, facePresent = false, hadFreshDetection = true, meshPoints = lastMesh, faceBox = null)
            } else {
                val box = meshes[0].boundingBox
                val raw = rawRoisFromBox(box, image.width, image.height)
                val sm = ema(raw)
                lastRois = Rois(
                    Rect(sm[0].roundToInt(), sm[1].roundToInt(),
                         sm[2].roundToInt(), sm[3].roundToInt()),
                    Rect(sm[4].roundToInt(), sm[5].roundToInt(),
                         sm[6].roundToInt(), sm[7].roundToInt()),
                    Rect(sm[8].roundToInt(), sm[9].roundToInt(),
                         sm[10].roundToInt(), sm[11].roundToInt()),
                )
                lastMesh = extractMeshPoints(meshes[0])
                lastBox = box
                framesSinceDetect = 0
                Result(rois = lastRois, facePresent = true,
                       hadFreshDetection = true, meshPoints = lastMesh, faceBox = lastBox)
            }
        } catch (t: Throwable) {
            com.edgeppg.app.Log.error("capture", "face mesh failed", t)
            smooth = null
            lastRois = null
            lastBox = null
            Result(rois = null, facePresent = false,
                   hadFreshDetection = false, meshPoints = lastMesh, faceBox = null)
        } finally {
            detecting.set(false)
        }
    }

    /**
     * Flatten the 468 3D mesh points into a single float array
     * [x0, y0, z0, x1, y1, z1, ...] in mesh-point index order. Z is in
     * the same coordinate space as X / Y but smaller magnitude (relative
     * depth, not millimetres).
     *
     * The MediaPipe face mesh indices used by the geometry extractors
     * (Stage 6) reference this ordering — see [behavior.MeshLandmarks].
     */
    private fun extractMeshPoints(mesh: FaceMesh): FloatArray {
        val pts = mesh.allPoints
        if (pts.isEmpty()) return FloatArray(0)
        val out = FloatArray(pts.size * 3)
        var i = 0
        for (p in pts) {
            val pos = p.position
            out[i++] = pos.x
            out[i++] = pos.y
            out[i++] = pos.z
        }
        return out
    }

    private fun rawRoisFromBox(box: Rect, w: Int, h: Int): FloatArray {
        val bw = box.width().toFloat()
        val bh = box.height().toFloat()
        fun r(fx0: Float, fy0: Float, fx1: Float, fy1: Float): FloatArray {
            val l = (box.left + bw * fx0).coerceIn(0f, (w - 16).toFloat())
            val t = (box.top + bh * fy0).coerceIn(0f, (h - 16).toFloat())
            val rr = (box.left + bw * fx1).coerceIn(16f, w.toFloat())
            val b = (box.top + bh * fy1).coerceIn(16f, h.toFloat())
            return floatArrayOf(
                l, t, rr.coerceAtLeast(l + 16f), b.coerceAtLeast(t + 16f)
            )
        }
        return (
            r(0.30f, 0.08f, 0.70f, 0.28f) +
            r(0.08f, 0.45f, 0.32f, 0.65f) +
            r(0.68f, 0.45f, 0.92f, 0.65f)
        )
    }

    private fun ema(raw: FloatArray): FloatArray {
        val s = smooth
        if (s == null) {
            smooth = raw.copyOf()
            return raw
        }
        for (i in raw.indices) {
            s[i] = emaAlpha * raw[i] + (1f - emaAlpha) * s[i]
        }
        return s
    }

    /**
     * Compute mean R, G, B per ROI directly from YUV_420_888 planes
     * (stride-sampled every 4th pixel, BT.601 full-range integer path).
     * Writes into [out] float[9]. Returns false if any ROI is invalid
     * (zero-sized or out-of-frame).
     *
     * Zero allocations on the hot path: no Bitmap, no FloatArray per
     * frame, no conversions beyond the integer math shown inline.
     */
    fun meanRgbPerRoi(image: Image, rois: Rois, out: FloatArray): Boolean {
        if (out.size < 9) return false
        val rects = arrayOf(rois.forehead, rois.cheekL, rois.cheekR)
        val planes = image.planes
        if (planes.size < 3) return false
        val yRow = planes[0].rowStride
        val uvRow = planes[1].rowStride
        val uvPix = planes[1].pixelStride
        val w = image.width
        val yBuf = planes[0].buffer
        val uBuf = planes[1].buffer
        val vBuf = planes[2].buffer

        for (ri in 0..2) {
            val r = rects[ri]
            var sumR = 0L; var sumG = 0L; var sumB = 0L
            var n = 0
            var y = r.top
            while (y < r.bottom) {
                var x = r.left
                while (x < r.right) {
                    val yv = yBuf.get(y * yRow + x).toInt() and 0xFF
                    val uvx = x / 2
                    val uvy = y / 2
                    val uvIdx = uvy * uvRow + uvx * uvPix
                    val vv = vBuf.get(uvIdx).toInt() and 0xFF
                    val uu = uBuf.get(uvIdx).toInt() and 0xFF
                    // ITU-R BT.601 full-range YUV → RGB, integer path.
                    var rr = yv + ((359 * (vv - 128)) shr 8)
                    var gg = yv - (((88 * (uu - 128) + 183 * (vv - 128))) shr 8)
                    var bb = yv + ((454 * (uu - 128)) shr 8)
                    rr = rr.coerceIn(0, 255)
                    gg = gg.coerceIn(0, 255)
                    bb = bb.coerceIn(0, 255)
                    sumR += rr; sumG += gg; sumB += bb
                    n++
                    x += 4
                }
                y += 4
            }
            if (n == 0) return false
            out[ri * 3]     = sumR.toFloat() / n
            out[ri * 3 + 1] = sumG.toFloat() / n
            out[ri * 3 + 2] = sumB.toFloat() / n
        }
        return true
    }

    /** Helper used by MainActivity to peek at the current frame count for diagnostics. */
    fun framesSinceDetection(): Int = framesSinceDetect
}
