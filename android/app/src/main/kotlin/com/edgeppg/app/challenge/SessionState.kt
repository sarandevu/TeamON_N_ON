package com.edgeppg.app.challenge

/**
 * Stage 5 / 7 — Session state machine (Architecture §11, FR-SESS-5).
 *
 * Documented states:
 *   CAPTURE → QUALITY_CHECK → BASELINE → RANDOMIZED_CHALLENGE →
 *   MOTION_BLINK_CHECK → PROCESSING → DONE
 *
 * Transitions:
 *   - Quality failures in QUALITY_CHECK or MOTION_BLINK_CHECK route to
 *     UNCERTAIN (Architecture §8 / FR-GATE-3) — never to SPOOF. The
 *     retry counter is configurable (default 1, per FR-SESS-6); the
 *     state machine consumes it without hardcoding a number.
 *   - The state machine emits a [Transition] record for every move so
 *     the audit trail (Stage 11 / 15) can show which path was taken.
 */
enum class SessionState {
    CAPTURE,
    QUALITY_CHECK,
    BASELINE,
    RANDOMIZED_CHALLENGE,
    MOTION_BLINK_CHECK,
    PROCESSING,
    DONE,
}

/**
 * Audit-friendly transition record. The decision engine (Stage 11) and
 * the verifier (Stage 12) read these to know *why* the session
 * terminated.
 */
data class Transition(
    val from: SessionState,
    val to: SessionState,
    val reason: String,
)

/**
 * Pure state machine — no Android, no UI, no networking. Drives the
 * capture session from CAPTURE through DONE.
 *
 * Retry semantics:
 *  - `maxRetries` is configurable; the default is 1, matching FR-SESS-6.
 *  - A retry may only be triggered from QUALITY_CHECK or
 *    MOTION_BLINK_CHECK (the documented quality-failure points).
 *  - When `maxRetries` is exceeded, the machine transitions to DONE
 *    with reason "retries-exhausted"; the decision engine must then
 *    route to UNCERTAIN (FR-GATE-3).
 */
class SessionStateMachine(
    private val maxRetries: Int = 1,
) {
    private var state: SessionState = SessionState.CAPTURE
    private var retriesRemaining: Int = maxRetries
    private val transitions: MutableList<Transition> = mutableListOf()

    val current: SessionState get() = state
    val history: List<Transition> get() = transitions.toList()

    /** Reset to the initial state. Used between sessions. */
    fun reset() {
        state = SessionState.CAPTURE
        retriesRemaining = maxRetries
        transitions.clear()
    }

    private fun move(to: SessionState, reason: String) {
        transitions.add(Transition(state, to, reason))
        state = to
    }

    /** Begin a session. Always the first transition. */
    fun begin(): Transition {
        if (state != SessionState.CAPTURE) error(
            "begin() called from state=$state, expected CAPTURE"
        )
        // We start by moving to QUALITY_CHECK; the state machine holds
        // the CAPTURE marker until begin() is called.
        move(SessionState.QUALITY_CHECK, "begin")
        return transitions.last()
    }

    /**
     * Pass the quality check. Move to BASELINE.
     */
    fun qualityPass(): Transition {
        require(state == SessionState.QUALITY_CHECK) {
            "qualityPass() called from state=$state, expected QUALITY_CHECK"
        }
        move(SessionState.BASELINE, "quality-pass")
        return transitions.last()
    }

    /**
     * Fail the quality check. Either retry (if any retries remain) or
     * terminate as DONE with reason "retries-exhausted".
     *
     * The decision engine routes DONE-after-retries-exhausted to
     * UNCERTAIN (FR-GATE-3). UNCERTAIN is legitimate.
     */
    fun qualityFail(reason: String): Transition {
        require(state == SessionState.QUALITY_CHECK) {
            "qualityFail() called from state=$state, expected QUALITY_CHECK"
        }
        if (retriesRemaining > 0) {
            retriesRemaining--
            move(SessionState.QUALITY_CHECK, "quality-fail-retry:$reason")
            // Move back to CAPTURE for the retry round.
            move(SessionState.CAPTURE, "restart-for-retry")
            return transitions.last()
        }
        move(SessionState.DONE, "retries-exhausted:$reason")
        return transitions.last()
    }

    /** Baseline capture finished. Move to RANDOMIZED_CHALLENGE. */
    fun baselineComplete(): Transition {
        require(state == SessionState.BASELINE) {
            "baselineComplete() called from state=$state"
        }
        move(SessionState.RANDOMIZED_CHALLENGE, "baseline-complete")
        return transitions.last()
    }

    /** Randomized challenge sequence finished. Move to MOTION_BLINK_CHECK. */
    fun challengeComplete(): Transition {
        require(state == SessionState.RANDOMIZED_CHALLENGE) {
            "challengeComplete() called from state=$state"
        }
        move(SessionState.MOTION_BLINK_CHECK, "challenge-complete")
        return transitions.last()
    }

    /**
     * Pass motion/blink check. Move to PROCESSING.
     */
    fun motionBlinkPass(): Transition {
        require(state == SessionState.MOTION_BLINK_CHECK) {
            "motionBlinkPass() called from state=$state"
        }
        move(SessionState.PROCESSING, "motion-blink-pass")
        return transitions.last()
    }

    /**
     * Fail motion/blink check. Either retry (if any retries remain) or
     * terminate as DONE with reason "retries-exhausted".
     */
    fun motionBlinkFail(reason: String): Transition {
        require(state == SessionState.MOTION_BLINK_CHECK) {
            "motionBlinkFail() called from state=$state"
        }
        if (retriesRemaining > 0) {
            retriesRemaining--
            move(SessionState.MOTION_BLINK_CHECK,
                "motion-blink-fail-retry:$reason")
            move(SessionState.RANDOMIZED_CHALLENGE, "restart-challenge")
            return transitions.last()
        }
        move(SessionState.DONE, "retries-exhausted:$reason")
        return transitions.last()
    }

    /**
     * Processing finished. Final transition to DONE with the supplied
     * reason (typically "decision:LIVE" / "decision:SPOOF" /
     * "decision:UNCERTAIN").
     */
    fun processingComplete(reason: String): Transition {
        require(state == SessionState.PROCESSING) {
            "processingComplete() called from state=$state"
        }
        move(SessionState.DONE, reason)
        return transitions.last()
    }
}