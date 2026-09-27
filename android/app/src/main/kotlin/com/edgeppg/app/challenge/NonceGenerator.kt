package com.edgeppg.app.challenge

import java.security.SecureRandom

/**
 * Stage 5 — Cryptographic nonce / session id generation.
 *
 * Backed by [SecureRandom]. Per-session values:
 *   - `sessionId`: a UUIDv4 string — globally unique.
 *   - `nonce`:    16 random bytes hex — used for replay protection.
 *   - `seed`:     32 random bytes hex — drives challenge generation.
 *
 * Per Architecture §4 the nonce and seed are fresh per session. We do
 * not reuse them; the PC verifier rejects replays.
 */
class NonceGenerator(
    private val rng: SecureRandom = SecureRandom(),
) {
    fun sessionId(): String = java.util.UUID.randomUUID().toString()

    fun nonceHex(byteCount: Int = 16): String {
        val b = ByteArray(byteCount)
        rng.nextBytes(b)
        return b.joinToString("") { "%02x".format(it) }
    }

    fun seedHex(byteCount: Int = 32): String = nonceHex(byteCount)

    /** Pair the three values together for one session. */
    fun newSession(): SessionTokens = SessionTokens(
        sessionId = sessionId(),
        nonce = nonceHex(),
        seed = seedHex(),
    )
}

data class SessionTokens(
    val sessionId: String,
    val nonce: String,
    val seed: String,
)