package com.edgeppg.app.challenge

import java.security.MessageDigest
import kotlin.random.Random

/**
 * Stage 5 — Per-session randomized challenge sequence.
 *
 * Given a per-session seed (from [NonceGenerator.seedHex]), the engine
 * generates a sequence of [ChallengeSpec] items covering gaze / head /
 * hand / still-hold instructions. Sequences are deterministic for the
 * same seed (so the PC verifier can reproduce them when needed) and
 * per-session unpredictable (different sessions → different seeds →
 * different sequences).
 *
 * The applicant and the trusted participant each get their own
 * independent sequence per `FR-SESS-4`.
 *
 * Distribution policy (heuristic — calibrated once real data lands):
 *   - 4–6 challenges per sequence.
 *   - Modalities are mixed: gaze + head + hand + at least one
 *     RemainStill for motion-contamination gating.
 *   - Same-modality repeats are spaced out so the user isn't asked to
 *     "look left" then "look left" in a row.
 */
class ChallengeEngine(
    private val sequenceLength: Int = 5,
) {

    /**
     * Generate an applicant sequence.
     *
     * @param seedHex 64-char hex seed (32 bytes) from the per-session seed.
     */
    fun generateApplicant(seedHex: String): List<ChallengeSpec> {
        val rng = seededRng(seedHex, salt = "applicant")
        return buildSequence(rng, ChallengingSubject.APPLICANT)
    }

    /**
     * Generate an independent trusted-participant sequence.
     *
     * @param seedHex 64-char hex seed (32 bytes) from the per-session seed.
     */
    fun generateTrusted(seedHex: String): List<ChallengeSpec> {
        val rng = seededRng(seedHex, salt = "trusted")
        return buildSequence(rng, ChallengingSubject.TRUSTED_PARTICIPANT)
    }

    private fun buildSequence(
        rng: Random,
        subject: ChallengingSubject,
    ): List<ChallengeSpec> {
        require(sequenceLength in 4..8) {
            "sequenceLength must be 4..8; got $sequenceLength"
        }
        // Pool of possible challenges; we pick with replacement but avoid
        // immediate same-modality repeats.
        val allGaze = GazeDirection.entries
        val allHead = HeadOrientation.entries
        val allHand = HandGesture.entries

        val out = mutableListOf<ChallengeSpec>()
        var prevModality: String? = null

        repeat(sequenceLength) {
            // 35% gaze, 30% head, 20% hand, 15% still-hold (last slot).
            var modality = if (it == sequenceLength - 1 && prevModality != "still") {
                "still"
            } else {
                val r = rng.nextDouble()
                when {
                    r < 0.35 -> "gaze"
                    r < 0.65 -> "head"
                    r < 0.85 -> "hand"
                    else -> "still"
                }
            }
            // Force a different modality if the draw would repeat.
            // Bounded retry — at most 8 attempts to avoid pathological
            // loops while still guaranteeing (with high probability) no
            // GAZE→GAZE / HEAD→HEAD / HAND→HAND consecutive pairs.
            if (modality != "still" && prevModality != null) {
                var attempts = 0
                while (modality == prevModality && attempts < 8) {
                    val r = rng.nextDouble()
                    modality = when {
                        r < 0.35 -> "gaze"
                        r < 0.65 -> "head"
                        r < 0.85 -> "hand"
                        else -> "still"
                    }
                    attempts++
                }
            }
            when (modality) {
                "gaze" -> out.add(ChallengeSpec.Gaze(
                    direction = allGaze.random(rng),
                    subject = subject,
                ))
                "head" -> out.add(ChallengeSpec.Head(
                    orientation = allHead.random(rng),
                    subject = subject,
                ))
                "hand" -> out.add(ChallengeSpec.Hand(
                    gesture = allHand.random(rng),
                    subject = subject,
                ))
                "still" -> out.add(ChallengeSpec.RemainStill(
                    durationMs = 1_500L + rng.nextInt(0, 1_500),
                    subject = subject,
                ))
            }
            prevModality = modality
        }

        // Guarantee at least one RemainStill. If we never picked it,
        // replace the last challenge with one.
        if (out.none { it is ChallengeSpec.RemainStill }) {
            out[out.size - 1] = ChallengeSpec.RemainStill(
                durationMs = 2_000L,
                subject = subject,
            )
        }

        return out
    }

    /**
     * Derive a [Random] from a hex seed + a salt string. The salt
     * differentiates the applicant stream from the trusted stream even
     * though they share the per-session seed.
     */
    private fun seededRng(seedHex: String, salt: String): Random {
        val digest = MessageDigest.getInstance("SHA-256").apply {
            update(hexToBytes(seedHex))
            update(salt.toByteArray(Charsets.UTF_8))
        }.digest()
        // Random(seed=...) takes a Long — use the first 8 bytes.
        var seed = 0L
        for (i in 0 until 8) {
            seed = (seed shl 8) or (digest[i].toLong() and 0xffL)
        }
        return Random(seed)
    }

    private fun hexToBytes(hex: String): ByteArray {
        require(hex.length % 2 == 0) { "odd hex string length" }
        return ByteArray(hex.length / 2) { i ->
            val hi = Character.digit(hex[i * 2], 16)
            val lo = Character.digit(hex[i * 2 + 1], 16)
            require(hi >= 0 && lo >= 0) { "non-hex char at $i" }
            ((hi shl 4) or lo).toByte()
        }
    }
}