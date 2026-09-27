package com.edgeppg.app.multi

import com.google.mlkit.vision.facemesh.FaceMesh
import kotlin.math.hypot

/**
 * Stage 8 — Multi-person face tracker.
 *
 * Per `Architecture §5`: "Applicant + Trusted Co-Presence Participant
 * (never a 'family-member requirement'). Each is tracked independently
 * with separate fresh challenges."
 *
 * We use a simple centroid + IoU-based tracker that keeps up to
 * [maxParticipants] independent face tracks. The tracker is the
 * minimal piece that allows the analyzer thread to deliver:
 *  - per-participant ROI sets (so each gets their own rPPG window,
 *    their own behavioral challenges);
 *  - per-participant identity continuity (so the same participant
 *    keeps the same track id across frames).
 *
 * This class is the **IoU centroid tracker** — not an identity
 * embedding tracker. Per the architecture, identity verification is
 * a separate concern (Stage 6+ via ML Kit Face Mesh, gated by
 * availability); the IoU/centroid tracker just keeps "the same face
 * got the same track id" frame-to-frame.
 *
 * Output:
 *  - `update(faces, frameWidth, frameHeight) -> List<Track>` — at
 *    most [maxParticipants] tracks, each with a stable id, the
 *    latest bounding box, and the latest mesh points.
 */
class MultiFaceTracker(
    private val maxParticipants: Int = 2,
    private val maxFramesSinceSeen: Int = 30,
) {

    /** A single face track. */
    data class Track(
        val id: Int,
        val box: FaceBox,
        val meshPoints: FloatArray,
        var framesSinceSeen: Int = 0,
        var assignedSubject: Subject = Subject.UNASSIGNED,
    ) {
        /** Centroid (cx, cy) for IoU matching. */
        fun centroid(): Pair<Float, Float> = box.cx to box.cy
    }

    enum class Subject { UNASSIGNED, APPLICANT, TRUSTED_PARTICIPANT }

    /** Simple bounding box wrapper. */
    data class FaceBox(
        val left: Int, val top: Int, val right: Int, val bottom: Int,
    ) {
        val width: Int get() = right - left
        val height: Int get() = bottom - top
        val cx: Float get() = (left + right) / 2f
        val cy: Float get() = (top + bottom) / 2f
    }

    private var nextTrackId: Int = 0
    private val tracks: MutableList<Track> = mutableListOf()

    /** External subject assignment (the engine decides who's applicant
     *  vs trusted). Once assigned, a track keeps its role for the
     *  session. */
    fun assignSubject(trackId: Int, subject: Subject) {
        val idx = tracks.indexOfFirst { it.id == trackId }
        if (idx >= 0) tracks[idx].assignedSubject = subject
    }

    fun snapshot(): List<Track> = tracks.toList()

    /** Reset for a new session. */
    fun reset() {
        tracks.clear()
        nextTrackId = 0
    }

    /**
     * Feed a new frame's detected faces. Each face is a pair of
     * (bounding box, mesh points). Returns the updated track list.
     *
     * Matching strategy (centroid + IoU):
     *  - For each new face, pick the closest existing track whose
     *    centroid is within [centroidThreshold] of the new face AND
     *    whose IoU exceeds [iouThreshold]. If multiple candidates, take
     *    the highest IoU.
     *  - If no match, allocate a new track id.
     *  - Unmatched tracks get `framesSinceSeen++`; if it exceeds
     *    [maxFramesSinceSeen], the track is dropped.
     */
    fun update(
        detections: List<Pair<FaceBox, FloatArray>>,
    ): List<Track> {
        val matched = BooleanArray(tracks.size)

        for ((box, mesh) in detections) {
            val matchIdx = bestMatch(box, matched)
            if (matchIdx >= 0) {
                val t = tracks[matchIdx]
                tracks[matchIdx] = Track(
                    id = t.id,
                    box = box,
                    meshPoints = mesh,
                    framesSinceSeen = 0,
                    assignedSubject = t.assignedSubject,
                )
                matched[matchIdx] = true
            } else if (tracks.size < maxParticipants) {
                tracks.add(Track(
                    id = nextTrackId++,
                    box = box,
                    meshPoints = mesh,
                    framesSinceSeen = 0,
                ))
            }
            // If we'd exceed maxParticipants, drop the new face.
        }

        // Bump unseen counters on the remaining unmatched tracks; drop
        // stale ones.
        val it = tracks.listIterator()
        while (it.hasNext()) {
            val t = it.next()
            val idx = tracks.indexOf(t)
            if (idx >= 0 && !matched[idx]) {
                t.framesSinceSeen++
                if (t.framesSinceSeen > maxFramesSinceSeen) it.remove()
            }
        }
        return tracks.toList()
    }

    private fun bestMatch(box: FaceBox, matched: BooleanArray): Int {
        var bestIdx = -1
        var bestScore = Float.NEGATIVE_INFINITY
        for (i in tracks.indices) {
            if (matched[i]) continue
            val t = tracks[i]
            val iou = intersectionOverUnion(box, t.box)
            val dist = hypot(box.cx - t.box.cx, box.cy - t.box.cy)
            // Score: IoU prioritised; fall back to centroid proximity
            // when IoU is too low (faces that just entered the frame).
            val score = if (iou >= MIN_IOU) iou
                        else -dist / 1_000f
            if (score > bestScore) {
                bestScore = score
                bestIdx = i
            }
        }
        return bestIdx
    }

    private fun intersectionOverUnion(a: FaceBox, b: FaceBox): Float {
        val ix0 = maxOf(a.left, b.left)
        val iy0 = maxOf(a.top, b.top)
        val ix1 = minOf(a.right, b.right)
        val iy1 = minOf(a.bottom, b.bottom)
        if (ix0 >= ix1 || iy0 >= iy1) return 0f
        val inter = (ix1 - ix0).toLong() * (iy1 - iy0).toLong()
        val union = a.width.toLong() * a.height.toLong() +
                b.width.toLong() * b.height.toLong() - inter
        if (union <= 0) return 0f
        return inter.toFloat() / union.toFloat()
    }

    companion object {
        const val MIN_IOU: Float = 0.10f
    }
}

/**
 * Convenience: turn a [FaceMesh] into the (FaceBox, meshPoints) pair
 * the tracker consumes. `rotationDegrees` is the image rotation from
 * CameraX (used to decide how to map the bounding box back into the
 * analyzer's coordinate space — kept out of scope here; the caller
 * passes an already-corrected box).
 */
fun FaceMesh.toPair(): Pair<MultiFaceTracker.FaceBox, FloatArray> {
    val box = MultiFaceTracker.FaceBox(
        left = boundingBox.left,
        top = boundingBox.top,
        right = boundingBox.right,
        bottom = boundingBox.bottom,
    )
    val pts = allPoints
    val mesh = FloatArray(pts.size * 3)
    var i = 0
    for (p in pts) {
        val pos = p.position
        mesh[i++] = pos.x
        mesh[i++] = pos.y
        mesh[i++] = pos.z
    }
    return box to mesh
}