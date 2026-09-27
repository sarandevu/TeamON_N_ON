package com.edgeppg.app.transport

/**
 * Stage 13 — Payload size guard.
 *
 * Per Architecture §10 / FR-TR-2 the QR fallback must NOT silently
 * truncate payloads that exceed its capacity. A truncated envelope
 * would still verify cryptographically (the truncated bytes are not
 * the signed bytes) but the verifier would reject it as malformed,
 * and the user would have scanned a useless QR. We fail loud instead.
 *
 * The check is conservative: the upper bound is the documented QR
 * capacity at our chosen error-correction level (L ≈ 2.9 KB of
 * binary data; ~1.7 KB after the QR's mode + length + ECC overhead
 * is subtracted; we round down to 1.5 KB to leave headroom for
 * future envelope field additions).
 *
 * Local Wi-Fi transport is NOT subject to this limit; the
 * architecture caps the HTTP body at 256 KB. We only enforce the
 * QR bound on payloads that are about to be encoded as a QR.
 */
object PayloadTruncator {

    /** Max bytes the QR fallback will encode without raising. */
    const val MAX_QR_PAYLOAD_BYTES: Int = 1500

    class QrOverflowException(actualBytes: Int) :
        IllegalStateException(
            "QR payload $actualBytes bytes exceeds the documented " +
                "max of $MAX_QR_PAYLOAD_BYTES bytes; refusing to " +
                "truncate (would produce a useless QR). Use the " +
                "LocalWi-Fi transport instead, or shorten the " +
                "envelope fields."
        )

    /**
     * Throws [QrOverflowException] if the payload exceeds
     * [MAX_QR_PAYLOAD_BYTES]. Call this BEFORE handing the payload
     * to ZXing. Returns the payload unchanged on success so the
     * call site can chain.
     */
    @Throws(QrOverflowException::class)
    fun checkQrFits(payload: String): String {
        val bytes = payload.toByteArray(Charsets.UTF_8).size
        if (bytes > MAX_QR_PAYLOAD_BYTES) {
            throw QrOverflowException(bytes)
        }
        return payload
    }
}
