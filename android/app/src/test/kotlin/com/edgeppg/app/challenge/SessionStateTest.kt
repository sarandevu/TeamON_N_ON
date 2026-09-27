package com.edgeppg.app.challenge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Stage 15 Task 6 — JVM tests for [SessionStateMachine].
 *
 * The machine has 7 states (Architecture §11) and a configurable
 * retry policy. We assert the documented transitions, the retry
 * semantics, the terminal-DONE condition, and that invalid
 * transitions raise.
 */
class SessionStateTest {

    @Test
    fun documented_states_present() {
        // Architecture §11 enumerates these seven.
        val expected = setOf(
            "CAPTURE", "QUALITY_CHECK", "BASELINE", "RANDOMIZED_CHALLENGE",
            "MOTION_BLINK_CHECK", "PROCESSING", "DONE",
        )
        val actual = SessionState.entries.map { it.name }.toSet()
        assertEquals(expected, actual)
    }

    @Test
    fun happy_path_advances_in_order() {
        val m = SessionStateMachine(maxRetries = 1)
        assertEquals(SessionState.CAPTURE, m.current)
        m.begin()
        assertEquals(SessionState.QUALITY_CHECK, m.current)
        m.qualityPass()
        assertEquals(SessionState.BASELINE, m.current)
        m.baselineComplete()
        assertEquals(SessionState.RANDOMIZED_CHALLENGE, m.current)
        m.challengeComplete()
        assertEquals(SessionState.MOTION_BLINK_CHECK, m.current)
        m.motionBlinkPass()
        assertEquals(SessionState.PROCESSING, m.current)
        m.processingComplete("decision:LIVE")
        assertEquals(SessionState.DONE, m.current)
    }

    @Test
    fun quality_fail_with_retries_remaining_restarts() {
        val m = SessionStateMachine(maxRetries = 2)
        m.begin()
        m.qualityFail("low-light")
        // The machine drops back to CAPTURE so the operator can
        // restart the quality window.
        assertEquals(SessionState.CAPTURE, m.current)
    }

    @Test
    fun quality_fail_exhausts_retries_terminates_at_done() {
        val m = SessionStateMachine(maxRetries = 1)
        m.begin()
        m.qualityFail("dark")
        assertEquals(SessionState.CAPTURE, m.current) // retry #1
        m.begin() // operator restarts
        m.qualityFail("still-dark")
        // retries exhausted; final state is DONE per the machine.
        assertEquals(SessionState.DONE, m.current)
    }

    @Test
    fun motion_blink_fail_exhausts_retries_terminates_at_done() {
        val m = SessionStateMachine(maxRetries = 0)
        m.begin()
        m.qualityPass()
        m.baselineComplete()
        m.challengeComplete()
        m.motionBlinkFail("blink")
        assertEquals(SessionState.DONE, m.current)
    }

    @Test
    fun transition_history_is_appended() {
        val m = SessionStateMachine(maxRetries = 1)
        m.begin()
        m.qualityPass()
        m.baselineComplete()
        m.challengeComplete()
        m.motionBlinkPass()
        m.processingComplete("decision:LIVE")
        // Six transitions: begin, qualityPass, baselineComplete,
        // challengeComplete, motionBlinkPass, processingComplete.
        assertEquals(6, m.history.size)
        assertEquals(SessionState.QUALITY_CHECK, m.history[1].from)
        assertEquals(SessionState.DONE, m.history.last().to)
    }

    @Test
    fun invalid_transition_raises() {
        val m = SessionStateMachine(maxRetries = 1)
        // We start in CAPTURE; baselineComplete() requires BASELINE.
        // The source guards with require(), so IllegalArgumentException.
        try {
            m.baselineComplete()
            assertFalse("expected IllegalArgumentException", true)
        } catch (e: IllegalArgumentException) {
            // expected — message names the rejected call.
            assertTrue(e.message!!.contains("baselineComplete"))
        }
    }

    @Test
    fun reset_returns_to_capture_with_no_history() {
        val m = SessionStateMachine(maxRetries = 1)
        m.begin()
        m.qualityPass()
        m.reset()
        assertEquals(SessionState.CAPTURE, m.current)
        assertEquals(0, m.history.size)
    }
}
