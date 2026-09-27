package com.edgeppg.app.behavior

import com.edgeppg.app.challenge.BehavioralObservation
import com.edgeppg.app.challenge.BehavioralOutcome
import com.edgeppg.app.challenge.ChallengeSpec
import com.edgeppg.app.challenge.GazeDirection
import com.edgeppg.app.challenge.HandGesture
import com.edgeppg.app.challenge.HeadOrientation
import kotlin.math.abs

/**
 * Stage 6 — Behavioral observation matcher.
 *
 * Compares a [ChallengeSpec] against the most recent [GazeEstimate],
 * [HeadPose], and (optional) hand observation, and produces a
 * [BehavioralObservation]. The actual `kotlinx.coroutines`-driven
 * runner that schedules the prompts and waits for timeouts lives in
 * the on-device Activity (Stage 15). This class is the **pure
 * matcher** that decides match / wrong / timeout / contaminated.
 *
 * Output feeds the per-modality feature aggregator (Stage 9 row
 * assembler): `gaze_accuracy`, `head_accuracy`, `hand_accuracy`,
 * `challenge_timing_error`, etc.
 */
object BehavioralRunner {

    /**
     * Compute one observation. Pass null for any observation that
     * isn't available yet (face lost, estimator returned NaN, etc.).
     *
     * @param requested the challenge spec.
     * @param startedAtMs / [nowMs] wall-clock timestamps for latency.
     * @param gaze the latest [GazeEstimate], or null.
     * @param pose the latest [HeadPose], or null.
     * @param gesture the latest observed [HandGesture], or null.
     * @param contaminationFlag if true, the observation is recorded as
     *   contaminated — typically because a large RGB step happened
     *   during the response window.
     */
    fun observe(
        requested: ChallengeSpec,
        startedAtMs: Long,
        nowMs: Long,
        gaze: GazeEstimate? = null,
        pose: HeadPose? = null,
        gesture: HandGesture? = null,
        contaminationFlag: Boolean = false,
    ): BehavioralObservation {
        val latencyMs = abs(nowMs - startedAtMs)
        val timedOut = nowMs - startedAtMs > requested.timeoutMs

        if (contaminationFlag) {
            return BehavioralObservation(requested,
                BehavioralOutcome.CONTAMINATED, latencyMs, success = false)
        }

        val matched = when (requested) {
            is ChallengeSpec.Gaze -> matchGaze(requested.direction, gaze)
            is ChallengeSpec.Head -> matchHead(requested.orientation,
                                                pose)
            is ChallengeSpec.Hand -> matchHand(requested.gesture, gesture)
            is ChallengeSpec.RemainStill -> matchStill(gaze, pose, gesture)
            // Optical flashes are passive stimuli — there is no
            // behavioral response to match against. The coroutine
            // driver (BehaviourRunner) emits its own MATCH observation
            // for OpticalFlash; if a non-coroutine caller reaches this
            // path, treat it as "no response" (null).
            is ChallengeSpec.OpticalFlash -> null
        }

        val outcome = when {
            timedOut && matched == null -> BehavioralOutcome.TIMEOUT
            matched == true -> BehavioralOutcome.MATCH
            matched == false -> BehavioralOutcome.WRONG
            else -> BehavioralOutcome.TIMEOUT
        }
        val success = outcome == BehavioralOutcome.MATCH
        return BehavioralObservation(requested, outcome, latencyMs, success)
    }

    private fun matchGaze(
        requested: GazeDirection,
        gaze: GazeEstimate?,
    ): Boolean? {
        if (gaze == null) return null
        if (requested == GazeDirection.CENTER) {
            return gaze.direction == GazeDirection.CENTER
        }
        return gaze.direction == requested
    }

    private fun matchHead(
        requested: HeadOrientation,
        pose: HeadPose?,
    ): Boolean? {
        if (pose == null) return null
        // Map the request to the relevant axis and check magnitude.
        return when (requested) {
            HeadOrientation.TURN_LEFT -> pose.yawDeg > 12f
            HeadOrientation.TURN_RIGHT -> pose.yawDeg < -12f
            HeadOrientation.TURN_UP -> pose.pitchDeg > 8f
            HeadOrientation.TURN_DOWN -> pose.pitchDeg < -8f
            HeadOrientation.NOD -> abs(pose.rollDeg) > 10f
            HeadOrientation.SHAKE_NO -> abs(pose.rollDeg) > 10f
        }
    }

    private fun matchHand(
        requested: HandGesture,
        observed: HandGesture?,
    ): Boolean? {
        if (observed == null) return null
        return observed == requested
    }

    /**
     * RemainStill succeeds when no detectable motion / gesture happened
     * during the window. Without the gesture observation we treat it as
     * MATCH (the still hold wasn't broken). The contamination flag is
     * checked separately above — if it's set, this challenge fails.
     */
    private fun matchStill(
        gaze: GazeEstimate?,
        pose: HeadPose?,
        gesture: HandGesture?,
    ): Boolean {
        if (gesture != null) return false  // a hand gesture is a motion event
        // Tiny head / gaze shifts are fine; large ones aren't.
        if (pose != null && pose.available &&
            (abs(pose.yawDeg) > 18f || abs(pose.pitchDeg) > 12f)
        ) return false
        if (gaze != null && gaze.direction != GazeDirection.CENTER) return false
        return true
    }
}