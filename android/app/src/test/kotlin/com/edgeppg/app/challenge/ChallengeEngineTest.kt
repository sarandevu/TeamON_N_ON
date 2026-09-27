package com.edgeppg.app.challenge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * Stage 15 Task 6 — JVM tests for [ChallengeEngine].
 *
 * The engine is pure Kotlin: it consumes a seed hex string, hashes
 * it, and produces a list of [ChallengeSpec]. We assert:
 *  - documented sequence length (default 5)
 *  - same seed → same sequence (deterministic)
 *  - different seeds → different sequences (per-session
 *    unpredictability, per FR-SESS-3 / SC-FUNC-3)
 *  - applicant vs trusted are independent streams (different salts)
 *  - the sequence always contains at least one RemainStill
 *  - the random pool is exercised across seeds (we sweep 64 seeds)
 */
class ChallengeEngineTest {

    private val engine = ChallengeEngine()

    @Test
    fun documented_sequence_length_is_5() {
        val s = engine.generateApplicant(SEED_A)
        assertEquals(5, s.size)
    }

    @Test
    fun same_seed_same_sequence() {
        val a = engine.generateApplicant(SEED_A)
        val b = engine.generateApplicant(SEED_A)
        assertEquals(a, b)
    }

    @Test
    fun different_seeds_different_sequences() {
        val a = engine.generateApplicant(SEED_A)
        val b = engine.generateApplicant(SEED_B)
        // We don't assert full inequality (a coin-flip-style engine
        // could match by chance) but the documented salt + SHA-256
        // derivation means a 32-byte seed change always produces a
        // different sequence.
        assertNotEquals(a, b)
    }

    @Test
    fun applicant_and_trusted_are_independent() {
        val a = engine.generateApplicant(SEED_A)
        val t = engine.generateTrusted(SEED_A)
        // The two streams are salted differently inside the engine;
        // applicant and trusted lists must not be equal.
        assertNotEquals(a, t)
    }

    @Test
    fun every_sequence_contains_remain_still() {
        // The engine guarantees at least one RemainStill per the
        // documented "motion-contamination gating" requirement.
        for (i in 0 until 64) {
            val seed = "%02x".format(i).repeat(32)
            val s = engine.generateApplicant(seed)
            assertTrue(
                "seed ${"%02x".format(i)}: no RemainStill in $s",
                s.any { it is ChallengeSpec.RemainStill },
            )
        }
    }

    @Test
    fun every_sequence_has_known_modalities() {
        // All non-still challenges must be Gaze, Head, or Hand —
        // the documented ChallengeSpec sealed type.
        for (i in 0 until 64) {
            val seed = "%02x".format(i).repeat(32)
            val s = engine.generateApplicant(seed)
            for (spec in s) {
                assertTrue(
                    "spec is not a known ChallengeSpec subtype: $spec",
                    spec is ChallengeSpec.Gaze
                        || spec is ChallengeSpec.Head
                        || spec is ChallengeSpec.Hand
                        || spec is ChallengeSpec.RemainStill
                        || spec is ChallengeSpec.OpticalFlash,
                )
            }
        }
    }

    @Test
    fun timeouts_are_positive() {
        // Per FR-BEH-* every behavioral challenge has a deadline.
        for (i in 0 until 64) {
            val seed = "%02x".format(i).repeat(32)
            val s = engine.generateApplicant(seed)
            for (spec in s) {
                assertTrue(
                    "non-positive timeout for $spec",
                    spec.timeoutMs > 0,
                )
            }
        }
    }

    @Test
    fun length_within_documented_range() {
        // The Kotlin docstring says "sequenceLength must be 4..8";
        // the `require()` lives in buildSequence, so the constraint
        // fires on generation, not construction. Verify it fires.
        val seed = "00".repeat(32)
        try {
            ChallengeEngine(sequenceLength = 3).generateApplicant(seed)
            assertFalse("expected IllegalArgumentException for length=3", true)
        } catch (e: IllegalArgumentException) {
            // expected
        }
        try {
            ChallengeEngine(sequenceLength = 9).generateApplicant(seed)
            assertFalse("expected IllegalArgumentException for length=9", true)
        } catch (e: IllegalArgumentException) {
            // expected
        }
    }

    companion object {
        // 32-byte hex seeds; full coverage of [0x00, 0x01) for byte 0.
        private val SEED_A = "00".repeat(32)
        private val SEED_B = "ff".repeat(32)
    }
}
