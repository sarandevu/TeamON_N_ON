package com.edgeppg.app.challenge

/**
 * Stage 5 — Behavioral challenge specification.
 *
 * Per-session randomized challenges covering gaze, head, hand, and a
 * stillness hold. Each instruction has a deadline (timeout); the
 * behavioral runner emits a [BehavioralObservation] once the deadline
 * is reached or the response is detected.
 *
 * Per FR-SESS-3:
 *   "looking left, right, up, or down, turning the head, nodding,
 *    remaining still, raising a specific hand, or performing simple
 *    gestures."
 *
 * The `ChallengingSubject` enum tells the engine whether a challenge
 * is for the applicant or the trusted participant (multi-person mode).
 */
enum class ChallengingSubject { APPLICANT, TRUSTED_PARTICIPANT }

sealed class ChallengeSpec {
    abstract val subject: ChallengingSubject
    abstract val timeoutMs: Long

    /** Look in a specific direction. */
    data class Gaze(
        val direction: GazeDirection,
        override val subject: ChallengingSubject,
        override val timeoutMs: Long = 7_000L,
    ) : ChallengeSpec()

    /** Turn or tilt the head to a specific orientation. */
    data class Head(
        val orientation: HeadOrientation,
        override val subject: ChallengingSubject,
        override val timeoutMs: Long = 7_000L,
    ) : ChallengeSpec()

    /** Raise a specific hand or perform a simple gesture. */
    data class Hand(
        val gesture: HandGesture,
        override val subject: ChallengingSubject,
        override val timeoutMs: Long = 7_000L,
    ) : ChallengeSpec()

    /** Hold still for the duration (motion-contamination detector). */
    data class RemainStill(
        val durationMs: Long,
        override val subject: ChallengingSubject,
        override val timeoutMs: Long = durationMs + 2_000L,
    ) : ChallengeSpec()

    /**
     * Optical flash challenge (FR-OPT-1). The renderer draws a
     * full-screen overlay in [color] for [durationMs] with a
     * brightness delta of [deltaPct] above ambient. The on-device
     * correlation with the camera's RGB measurement is performed by
     * the Stage 4 rPPG DSP in the temporal separation window
     * (FR-OPT-3) — the renderer is intentionally simple.
     */
    data class OpticalFlash(
        val color: OpticalColor,
        val deltaPct: Int,
        val durationMs: Long,
        override val subject: ChallengingSubject,
        override val timeoutMs: Long = durationMs + 1_000L,
    ) : ChallengeSpec()
}

enum class OpticalColor {
    WHITE,   // 0 — neutral baseline flash
    WARM,    // 1 — red-shifted
    COOL,    // 2 — blue-shifted
}

enum class GazeDirection { LEFT, RIGHT, UP, DOWN, CENTER }

enum class HeadOrientation {
    TURN_LEFT, TURN_RIGHT, TURN_UP, TURN_DOWN, NOD, SHAKE_NO
}

enum class HandGesture {
    RAISE_LEFT, RAISE_RIGHT, POINT, THUMBS_UP, OPEN_PALM,
}

/**
 * Observation recorded after each challenge completes. The behavioral
 * runner (Stage 6) emits one per challenge; the feature aggregator
 * (Stage 6 / 9) reduces these into the frozen-schema accuracy /
 * latency / consistency features.
 */
data class BehavioralObservation(
    val spec: ChallengeSpec,
    val observed: BehavioralOutcome,
    val latencyMs: Long,
    val success: Boolean,
)

enum class BehavioralOutcome {
    MATCH,        // observed == requested direction / gesture
    WRONG,        // observed != requested (e.g. looking LEFT when asked RIGHT)
    TIMEOUT,      // no detectable response within timeout
    CONTAMINATED, // response coincided with motion contamination
}