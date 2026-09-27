package com.edgeppg.app.behavior

/**
 * Stage 6 — MediaPipe / ML Kit Face Mesh landmark indices.
 *
 * The 468-point face mesh produced by ML Kit Face Mesh (FACE_MESH
 * use-case) is documented in the MediaPipe Face Mesh spec. We use a
 * small subset of indices for geometric gaze and head-pose
 * estimation. Indices here are 0-based (point 0 is the first mesh
 * point returned by `FaceMesh.getAllPoints()`).
 *
 * The values are stable across ML Kit versions; if ML Kit ever changes
 * them, the parser in [behavior.GazeEstimator] /
 * [behavior.HeadPoseSolver] must be revisited and `mesh_landmarks_test`
 * must be updated.
 *
 * Source: https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png
 *          https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model.obj
 */
object MeshLandmarks {

    // ---- Right eye (subject's right — image left in front-camera) ----
    const val RIGHT_EYE_OUTER = 33
    const val RIGHT_EYE_INNER = 133
    const val RIGHT_EYE_TOP = 159
    const val RIGHT_EYE_BOTTOM = 145
    const val RIGHT_IRIS_CENTER = 468  // refined iris landmark (when present)

    // ---- Left eye (subject's left — image right in front-camera) -----
    const val LEFT_EYE_OUTER = 263
    const val LEFT_EYE_INNER = 362
    const val LEFT_EYE_TOP = 386
    const val LEFT_EYE_BOTTOM = 374
    const val LEFT_IRIS_CENTER = 473    // refined iris landmark (when present)

    // ---- Head pose reference points ----
    const val NOSE_TIP = 1
    const val NOSE_BRIDGE = 168          // used as the head-pose anchor
    const val CHIN = 152
    const val FOREHEAD_CENTER = 10
    const val LEFT_MOUTH_CORNER = 61
    const val RIGHT_MOUTH_CORNER = 291

    // ---- Iris refinement range (ML Kit Face Mesh returns these only when
    //      the iris landmark refinement model is enabled; we guard the
    //      access in GazeEstimator). ----
    const val IRIS_REFINEMENT_MIN = 468
    const val IRIS_REFINEMENT_MAX = 477

    /**
     * Return (x, y, z) for the i-th mesh point, or NaN if i is out of
     * range. `meshPoints` is the flattened [x0, y0, z0, x1, y1, z1, ...]
     * array returned by `RoiTracker.Result.meshPoints`.
     */
    fun point(meshPoints: FloatArray, index: Int): FloatArray {
        val off = index * 3
        if (off < 0 || off + 2 >= meshPoints.size) {
            return floatArrayOf(Float.NaN, Float.NaN, Float.NaN)
        }
        return floatArrayOf(
            meshPoints[off],
            meshPoints[off + 1],
            meshPoints[off + 2]
        )
    }
}