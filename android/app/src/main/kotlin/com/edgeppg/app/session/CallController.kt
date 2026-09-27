package com.edgeppg.app.session

import com.edgeppg.app.challenge.NonceGenerator
import com.edgeppg.app.integrity.IntegrityManager
import com.edgeppg.app.transport.Transport
import com.edgeppg.app.transport.TransportResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * VKYC call orchestration (spec `docs/vkyc-call-dashboard-spec.md`,
 * Phase 2). Sits *above* the verification pipeline: it handles the
 * scheduled-call → Join Call handshake, then hands a PC-provided
 * `session_seed` to [SessionController.start] for the unchanged
 * verification flow.
 *
 * Call State (§5.1) is independent from Transport State, Verification
 * State, and Verification Result — this class tracks Call State only:
 * ```
 * IDLE → SCHEDULED → JOINING → CONNECTED → COMPLETED
 *                            ↘ FAILED
 * ```
 * (`IDLE` = no call entered yet; the spec's five states start at
 * SCHEDULED. COMPLETED is set by the caller once the verification
 * result it asked for has arrived.)
 *
 * No Android imports: fully JVM-testable. The Join Call goes out
 * through the existing [Transport] interface as an
 * [IntegrityManager.Envelope] whose `data` is the join JSON
 * (§8.4) — no new transport, no new protocol. The join payload is
 * built without org.json (Android-only at runtime) so this class
 * stays on the plain JVM.
 */
enum class CallState {
    IDLE,
    SCHEDULED,
    JOINING,
    CONNECTED,
    COMPLETED,
    FAILED,
}

/** Externally-visible call snapshot for the dashboard UI. */
data class CallView(
    val state: CallState,
    val callId: String,
    val applicantRef: String,
    val scheduledTime: String,
    /** PC-provided challenge seed once CONNECTED, else null. */
    val sessionSeed: String?,
    /** Last failure reason, else null. */
    val lastError: String?,
)

class CallController(
    private val nonceGenerator: NonceGenerator = NonceGenerator(),
) {
    private val _view = MutableStateFlow(
        CallView(
            state = CallState.IDLE,
            callId = "",
            applicantRef = "",
            scheduledTime = "",
            sessionSeed = null,
            lastError = null,
        )
    )
    val view: StateFlow<CallView> = _view.asStateFlow()

    /**
     * Record the scheduled call the operator entered (IDLE → SCHEDULED).
     * Blank call id or applicant ref is rejected with no state change.
     */
    fun setScheduled(
        callId: String,
        applicantRef: String,
        scheduledTime: String = "",
    ): CallView {
        val id = callId.trim()
        val ref = applicantRef.trim()
        if (id.isEmpty() || ref.isEmpty()) {
            return _view.value
        }
        val v = CallView(
            state = CallState.SCHEDULED,
            callId = id,
            applicantRef = ref,
            scheduledTime = scheduledTime.trim(),
            sessionSeed = null,
            lastError = null,
        )
        _view.value = v
        return v
    }

    /**
     * Send the Join Call and await the PC's `CALL_JOIN_RESPONSE`.
     * Only valid from SCHEDULED; any other state returns the current
     * view unchanged. Never throws — every failure becomes FAILED
     * with a reason.
     */
    suspend fun join(transport: Transport): CallView {
        val cur = _view.value
        if (cur.state != CallState.SCHEDULED) {
            return cur
        }
        _view.value = cur.copy(state = CallState.JOINING, lastError = null)
        val payload = buildJoinPayload(
            callId = cur.callId,
            applicantRef = cur.applicantRef,
        )
        // §8.4: reuse the Envelope structure so this rides the
        // existing Transport with no new protocol. Unsigned per the
        // spec's TBD resolution (start unsigned for simplicity).
        val envelope = IntegrityManager.Envelope(
            data = payload,
            sig = "",
            alg = "SHA256withECDSA",
            keyAlias = IntegrityManager.ALIAS,
        )
        val result: TransportResult = try {
            transport.send(envelope)
        } catch (t: Throwable) {
            fail("join-transport-threw:${t.javaClass.simpleName}")
            return _view.value
        }
        if (!result.ok) {
            fail(result.reason ?: "join-rejected")
            return _view.value
        }
        val raw = result.rawResponse
        val action = raw?.get("action") as? String
        val seed = raw?.get("session_seed") as? String
        if (action != "START_VERIFICATION" || seed.isNullOrBlank()) {
            fail(raw?.get("reason") as? String ?: "join-bad-response")
            return _view.value
        }
        val v = _view.value.copy(
            state = CallState.CONNECTED,
            sessionSeed = seed,
            lastError = null,
        )
        _view.value = v
        return v
    }

    /**
     * Mark the call COMPLETED once the verification result for it has
     * arrived. Only valid from CONNECTED; anything else is a no-op
     * returning the current view.
     */
    fun markCompleted(): CallView {
        val cur = _view.value
        if (cur.state != CallState.CONNECTED) {
            return cur
        }
        val v = cur.copy(state = CallState.COMPLETED)
        _view.value = v
        return v
    }

    /** Reset to IDLE (e.g. "Start new session" after DONE). */
    fun reset() {
        _view.value = CallView(
            state = CallState.IDLE,
            callId = "",
            applicantRef = "",
            scheduledTime = "",
            sessionSeed = null,
            lastError = null,
        )
    }

    private fun fail(reason: String) {
        _view.value = _view.value.copy(state = CallState.FAILED, lastError = reason)
    }

    companion object {
        /**
         * Join Call request body (§8.2 Option A). Minimal control
         * fields only: no feature vectors, sensor input, key
         * material, verification outcomes, or templates (§8.3).
         */
        fun buildJoinPayload(
            callId: String,
            applicantRef: String,
            nonce: String,
            timestampMs: Long,
        ): String =
            "{\"type\":\"CALL_JOIN_REQUEST\"," +
                "\"call_id\":\"${jsonEscape(callId)}\"," +
                "\"applicant_ref\":\"${jsonEscape(applicantRef)}\"," +
                "\"nonce\":\"${jsonEscape(nonce)}\"," +
                "\"timestamp_ms\":$timestampMs}"

        /** Minimal JSON string escaper (stdlib-only, JVM-safe). */
        fun jsonEscape(s: String): String {
            val sb = StringBuilder(s.length + 2)
            for (c in s) when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> if (c < ' ') sb.append("\\u%04x".format(c.code)) else sb.append(c)
            }
            return sb.toString()
        }
    }

    private fun buildJoinPayload(callId: String, applicantRef: String): String =
        buildJoinPayload(
            callId = callId,
            applicantRef = applicantRef,
            nonce = nonceGenerator.nonceHex(),
            timestampMs = System.currentTimeMillis(),
        )
}
