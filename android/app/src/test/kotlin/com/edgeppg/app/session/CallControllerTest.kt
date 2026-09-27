package com.edgeppg.app.session

import com.edgeppg.app.integrity.IntegrityManager
import com.edgeppg.app.transport.Transport
import com.edgeppg.app.transport.TransportResult
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Phase 2 — JVM tests for [CallController].
 *
 * Uses a fake [Transport]; no network, no Android. Asserts the Call
 * State machine (§5.1), the Join Call envelope shape (§8.2–8.3), and
 * that the existing `Transport.send()` is the only wire path (§9).
 */
class CallControllerTest {

    private class FakeTransport(
        var fn: (IntegrityManager.Envelope) -> TransportResult =
            { TransportResult.localError("unused") },
    ) : Transport {
        val sent = mutableListOf<IntegrityManager.Envelope>()
        override suspend fun send(
            envelope: IntegrityManager.Envelope,
        ): TransportResult {
            sent.add(envelope)
            return fn(envelope)
        }
    }

    private fun joinOk(seed: String = "s".repeat(64)) = TransportResult.from(
        ok = true,
        rawResponse = mapOf(
            "type" to "CALL_JOIN_RESPONSE",
            "ok" to true,
            "action" to "START_VERIFICATION",
            "session_seed" to seed,
        ),
    )

    @Test
    fun initial_state_is_idle() {
        val c = CallController()
        val v = c.view.value
        assertEquals(CallState.IDLE, v.state)
        assertNull(v.sessionSeed)
        assertNull(v.lastError)
    }

    @Test
    fun set_scheduled_moves_idle_to_scheduled() {
        val c = CallController()
        val v = c.setScheduled("call-1", "APP-1", "2026-09-27T10:00")
        assertEquals(CallState.SCHEDULED, v.state)
        assertEquals("call-1", v.callId)
        assertEquals("APP-1", v.applicantRef)
    }

    @Test
    fun set_scheduled_rejects_blank_fields() {
        val c = CallController()
        c.setScheduled("", "APP-1")
        assertEquals(CallState.IDLE, c.view.value.state)
        c.setScheduled("call-1", "   ")
        assertEquals(CallState.IDLE, c.view.value.state)
    }

    @Test
    fun join_from_wrong_state_is_noop() {
        val c = CallController()
        val transport = FakeTransport()
        val v: CallView = runBlocking { c.join(transport) }
        assertEquals(CallState.IDLE, v.state)
        assertTrue(transport.sent.isEmpty())
    }

    @Test
    fun join_success_reaches_connected_with_seed() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        val transport = FakeTransport { joinOk("a".repeat(64)) }
        val v: CallView = runBlocking { c.join(transport) }
        assertEquals(CallState.CONNECTED, v.state)
        assertEquals("a".repeat(64), v.sessionSeed)
        assertNull(v.lastError)
        // Exactly one envelope went out, through Transport.send().
        assertEquals(1, transport.sent.size)
    }

    @Test
    fun join_envelope_has_control_fields_only() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        var captured: IntegrityManager.Envelope? = null
        val transport = FakeTransport {
            captured = it
            joinOk()
        }
        runBlocking { c.join(transport) }
        val env = captured
        assertNotNull(env)
        val body = JSONObject(env!!.data)
        assertEquals("CALL_JOIN_REQUEST", body.getString("type"))
        assertEquals("call-1", body.getString("call_id"))
        assertEquals("APP-1", body.getString("applicant_ref"))
        assertTrue(body.getString("nonce").length >= 8)
        assertTrue(body.getLong("timestamp_ms") > 0)
        // §8.3: no biometrics, results, keys, or templates.
        val raw = env.data
        for (forbidden in listOf("LIVE", "SPOOF", "UNCERTAIN", "feature",
                "frame", "template", "embedding")) {
            assertFalse("join payload must not contain $forbidden",
                raw.contains(forbidden))
        }
    }

    @Test
    fun join_transport_failure_goes_failed() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        val transport = FakeTransport {
            TransportResult.localError("network-error:ConnectException")
        }
        val v: CallView = runBlocking { c.join(transport) }
        assertEquals(CallState.FAILED, v.state)
        assertEquals("network-error:ConnectException", v.lastError)
    }

    @Test
    fun join_bad_response_goes_failed() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        val transport = FakeTransport {
            TransportResult.from(ok = true, rawResponse = mapOf("ok" to true))
        }
        val v: CallView = runBlocking { c.join(transport) }
        assertEquals(CallState.FAILED, v.state)
        assertEquals("join-bad-response", v.lastError)
    }

    @Test
    fun join_rejection_reason_surfaces() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        val transport = FakeTransport {
            TransportResult.from(ok = false, reason = "unknown-call")
        }
        val v: CallView = runBlocking { c.join(transport) }
        assertEquals(CallState.FAILED, v.state)
        assertEquals("unknown-call", v.lastError)
    }

    @Test
    fun mark_completed_only_from_connected() {
        val c = CallController()
        // Not connected yet: no-op.
        c.setScheduled("call-1", "APP-1")
        c.markCompleted()
        assertEquals(CallState.SCHEDULED, c.view.value.state)
        // After a successful join: completes.
        val transport = FakeTransport { joinOk() }
        runBlocking { c.join(transport) }
        c.markCompleted()
        assertEquals(CallState.COMPLETED, c.view.value.state)
    }

    @Test
    fun reset_returns_to_idle() {
        val c = CallController()
        c.setScheduled("call-1", "APP-1")
        c.reset()
        val v = c.view.value
        assertEquals(CallState.IDLE, v.state)
        assertEquals("", v.callId)
        assertNull(v.sessionSeed)
    }

    @Test
    fun build_join_payload_escapes_quotes() {
        val s = CallController.buildJoinPayload(
            callId = "call-\"x\"",
            applicantRef = "A\\B",
            nonce = "n123",
            timestampMs = 42L,
        )
        // Must still parse as JSON with the raw values intact.
        val obj = JSONObject(s)
        assertEquals("call-\"x\"", obj.getString("call_id"))
        assertEquals("A\\B", obj.getString("applicant_ref"))
        assertEquals("CALL_JOIN_REQUEST", obj.getString("type"))
    }
}
