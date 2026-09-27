package com.edgeppg.app.behavior

import com.edgeppg.app.challenge.GazeDirection
import kotlin.math.abs

/**
 * Stage 6 — Geometric gaze direction estimator.
 *
 * Per `TechStack §11`: "landmark-based geometric computation" is the
 * documented first choice. We compute the iris-center-to-eye-corner
 * ratio and classify into LEFT / RIGHT / UP / DOWN / CENTER using
 * thresholds on the normalised offsets.
 *
 * The estimator is **unilateral**: it looks at one eye and picks a
 * direction. We use the **right eye** (subject's right, image left in a
 * front camera) by convention — the same convention ML Kit's iris
 * landmarks use.
 *
 * Confidence: returned by `estimateWithConfidence` as a 0..1 number —
 * the smaller the offset magnitude, the closer to "CENTER". The
 * `BehavioralRunner` (Stage 6 wire-up) folds confidence into a per-
 * challenge accuracy / latency calculation; a low-confidence
 * observation isn't WRONG, it's just uncertain.
 */
object GazeEstimator {

    /** Threshold for x / y normalised offset above which we report
     *  LEFT / RIGHT / UP / DOWN rather than CENTER. */
    private const val CENTER_THRESHOLD = 0.18f

    /** Threshold below which we report UNKNOWN (low signal). */
    private const val MIN_OFFSET = 0.02f

    /**
     * Classify gaze direction from a single eye's landmarks. Returns
     * `UNKNOWN` when the eye landmarks are unavailable or the offsets are
     * too small to mean anything.
     *
     * `meshPoints` is the flattened 468-point face-mesh array
     * (`RoiTracker.Result.meshPoints`).
     */
    fun estimate(meshPoints: FloatArray): GazeEstimate {
        val outer = MeshLandmarks.point(meshPoints, MeshLandmarks.RIGHT_EYE_OUTER)
        val inner = MeshLandmarks.point(meshPoints, MeshLandmarks.RIGHT_EYE_INNER)
        val top = MeshLandmarks.point(meshPoints, MeshLandmarks.RIGHT_EYE_TOP)
        val bottom = MeshLandmarks.point(meshPoints, MeshLandmarks.RIGHT_EYE_BOTTOM)

        if (outer.any { it.isNaN() } || inner.any { it.isNaN() } ||
            top.any { it.isNaN() } || bottom.any { it.isNaN() }
        ) {
            return GazeEstimate(GazeDirection.CENTER, 0f, eyeAvailable = false)
        }

        val eyeWidth = abs(inner[0] - outer[0])
        val eyeHeight = abs(bottom[1] - top[1])
        if (eyeWidth < 1f || eyeHeight < 1f) {
            // Degenerate: face too far / partial occlusion.
            return GazeEstimate(GazeDirection.CENTER, 0f, eyeAvailable = false)
        }

        // Iris x position in [0, 1] inside the eye box (0 = outer corner,
        // 1 = inner corner). 0.5 == CENTER.
        val iris = MeshLandmarks.point(meshPoints, MeshLandmarks.RIGHT_IRIS_CENTER)
        val irisX = if (iris.any { it.isNaN() }) 0.5f else iris[0]
        val irisY = if (iris.any { it.isNaN() }) 0.5f else iris[1]
        val xNorm = ((irisX - outer[0]) / eyeWidth).coerceIn(-1f, 2f) - 0.5f
        val yNorm = ((irisY - top[1]) / eyeHeight).coerceIn(-1f, 2f) - 0.5f

        val direction = when {
            abs(xNorm) < CENTER_THRESHOLD && abs(yNorm) < CENTER_THRESHOLD ->
                GazeDirection.CENTER
            abs(xNorm) >= CENTER_THRESHOLD ->
                if (xNorm > 0) GazeDirection.RIGHT else GazeDirection.LEFT
            else ->
                if (yNorm > 0) GazeDirection.DOWN else GazeDirection.UP
        }

        // Confidence: 1.0 at the centre, decreasing as |offset| grows.
        val conf = when (direction) {
            GazeDirection.CENTER -> 1f - (abs(xNorm) + abs(yNorm))
            GazeDirection.LEFT, GazeDirection.RIGHT ->
                (abs(xNorm) - CENTER_THRESHOLD).coerceIn(0f, 1f)
            GazeDirection.UP, GazeDirection.DOWN ->
                (abs(yNorm) - CENTER_THRESHOLD).coerceIn(0f, 1f)
        }

        if (abs(xNorm) < MIN_OFFSET && abs(yNorm) < MIN_OFFSET) {
            return GazeEstimate(GazeDirection.CENTER, 0f, eyeAvailable = true)
        }
        return GazeEstimate(direction, conf, eyeAvailable = true)
    }
}

/** Single-frame gaze classification with confidence. */
data class GazeEstimate(
    val direction: GazeDirection,
    val confidence: Float,
    val eyeAvailable: Boolean,
)