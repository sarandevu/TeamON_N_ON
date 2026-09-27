package com.edgeppg.app.challenge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Stage 15 Task 6 — JVM tests for [NonceGenerator].
 *
 * Per the integrity contract: sessionId is a UUIDv4 string; nonce
 * and seed are 32-hex (16-byte / 32-byte) random values from a
 * [java.security.SecureRandom]. We assert:
 *  - sessionId is well-formed (UUID format)
 *  - two distinct sessionId()s are not equal
 *  - nonceHex() and seedHex() produce the documented lengths
 *  - two distinct nonces are not equal
 */
class NonceGeneratorTest {

    private val gen = NonceGenerator()

    @Test
    fun session_id_is_uuid_format() {
        val id = gen.sessionId()
        // UUIDv4: 8-4-4-4-12 hex with hyphens, version digit 4 in 3rd group.
        val regex = Regex(
            "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        assertTrue("sessionId not UUID: $id", regex.matches(id))
    }

    @Test
    fun session_ids_are_distinct() {
        // 64 draws should all be unique with overwhelming probability.
        // (UUIDv4 has 122 bits of entropy; collision probability
        // across 64 draws is ~ 2^-116.)
        val ids = (1..64).map { gen.sessionId() }.toSet()
        assertEquals(64, ids.size)
    }

    @Test
    fun nonce_hex_is_32_chars() {
        val n = gen.nonceHex()
        assertEquals(32, n.length)
        assertTrue("non-hex char in nonce", n.all { it in '0'..'9' || it in 'a'..'f' })
    }

    @Test
    fun seed_hex_default_is_64_chars() {
        val s = gen.seedHex()
        assertEquals(64, s.length)
        assertTrue("non-hex char in seed", s.all { it in '0'..'9' || it in 'a'..'f' })
    }

    @Test
    fun seed_hex_respects_byte_count() {
        // We allow operators to request a different byte count
        // (still hex-encoded, 2 chars per byte).
        for (n in listOf(8, 16, 32, 64)) {
            val s = gen.seedHex(n)
            assertEquals(n * 2, s.length)
        }
    }

    @Test
    fun nonces_are_distinct() {
        val ns = (1..64).map { gen.nonceHex() }.toSet()
        assertEquals(64, ns.size)
    }

    @Test
    fun seeds_are_distinct() {
        val ss = (1..64).map { gen.seedHex() }.toSet()
        assertEquals(64, ss.size)
    }

    @Test
    fun new_session_packs_three_distinct_values() {
        val s = gen.newSession()
        assertNotEquals(s.sessionId, s.nonce)
        assertNotEquals(s.sessionId, s.seed)
        assertNotEquals(s.nonce, s.seed)
    }
}
