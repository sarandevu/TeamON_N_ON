package com.edgeppg.app.transport

import com.edgeppg.app.integrity.IntegrityManager

/**
 * Stage 13 — Transport interface.
 *
 * Per `Architecture §10` and `Requirements §FR-TR-1..4`:
 *  - Primary transport: local Wi-Fi (POST to the PC verifier).
 *  - Fallback transport: QR code rendered on-device for the user to
 *    scan / paste into the verifier dashboard.
 *  - Never use the clipboard (FR-TR-4).
 *  - No cloud / internet — the phone is offline by spec (NFR-OFF-1).
 *
 * The interface consumes the [IntegrityManager.Envelope] produced by
 * Stage 12 (canonical JSON signed with the AndroidKeyStore ECDSA P-256
 * key). Implementations are siblings: [LocalWifiTransport] (Task 3) and
 * [QrFallbackTransport] (Task 4). Each returns a [TransportResult]
 * without throwing — every error path is a structured `Ok=false` value,
 * matching the contract of the PC-side `verifier/verify.py`.
 *
 * Suspending so the caller can `await` the round-trip; both
 * implementations will be coroutine-friendly.
 */
interface Transport {

    /**
     * Send a signed envelope to the verifier.
     *
     * Implementations MUST NOT throw. Network failures, malformed
     * responses, and verifier-side rejections all become
     * [TransportResult] values. The only "fatal" failure is an
     * inability to even construct the request (e.g. no envelope
     * provided), which raises [IllegalArgumentException].
     *
     * @param envelope the signed transcript produced by
     *   `IntegrityManager.sign(...)`. Already-validated for canonical
     *   JSON byte form by `IntegrityManager.canonicalJson`.
     */
    suspend fun send(envelope: IntegrityManager.Envelope): TransportResult
}

/**
 * Verifier-side verdict, mirroring the wire shape returned by
 * `verifier/server.py` (the PC's HTTP intake). The fields are
 * deliberately a superset of the documented envelope payload so the
 * UI can show "what did the verifier see" without re-parsing
 * canonical JSON.
 *
 * The fields are nullable / optional because not every transport
 * produces every field:
 *  - `ok=true` ⇒ `telemetry` and `decision` are populated;
 *    `reason=null`.
 *  - `ok=false` ⇒ `reason` is populated; `telemetry` and `decision`
 *    may still be present if the server echoed them back.
 */
data class TransportResult(
    val ok: Boolean,
    val reason: String?,
    val decision: String?,
    val telemetry: Map<String, Any?>?,
    val telemetrySha256: String?,
    val receiptPath: String?,
    val serverVersion: String?,
    val httpStatus: Int,
    val roundTripMs: Long,
    /**
     * Full decoded response body, when the transport received one.
     * Verification responses only populate the typed fields above;
     * control-plane responses (e.g. `CALL_JOIN_RESPONSE` with
     * `action` / `session_seed` / `verifier_nonce`) are exposed here
     * so callers can read them without a schema change. Null when
     * nothing reached the wire or the body did not parse.
     */
    val rawResponse: Map<String, Any?>? = null,
) {
    companion object {
        /**
         * Result for "the transport could not even attempt a send"
         * (e.g. no envelope, no network at all). Distinct from
         * "the verifier rejected the envelope" — the former never
         * reached the wire, the latter did.
         */
        fun localError(reason: String, roundTripMs: Long = 0L): TransportResult =
            TransportResult(
                ok = false,
                reason = reason,
                decision = null,
                telemetry = null,
                telemetrySha256 = null,
                receiptPath = null,
                serverVersion = null,
                httpStatus = 0,
                roundTripMs = roundTripMs,
                rawResponse = null,
            )

        /**
         * Build a `TransportResult` from a complete result. Used by
         * implementations that successfully reached the wire and got
         * a structured verifier response back.
         */
        fun from(
            ok: Boolean,
            reason: String? = null,
            decision: String? = null,
            telemetry: Map<String, Any?>? = null,
            telemetrySha256: String? = null,
            receiptPath: String? = null,
            serverVersion: String? = null,
            httpStatus: Int = 200,
            roundTripMs: Long = 0L,
            rawResponse: Map<String, Any?>? = null,
        ): TransportResult = TransportResult(
            ok = ok,
            reason = reason,
            decision = decision,
            telemetry = telemetry,
            telemetrySha256 = telemetrySha256,
            receiptPath = receiptPath,
            serverVersion = serverVersion,
            httpStatus = httpStatus,
            roundTripMs = roundTripMs,
            rawResponse = rawResponse,
        )
    }
}
