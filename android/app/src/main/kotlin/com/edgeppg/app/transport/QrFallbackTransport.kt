package com.edgeppg.app.transport

import com.edgeppg.app.integrity.IntegrityManager
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.WriterException
import com.google.zxing.common.BitMatrix
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Stage 13 — QR fallback transport.
 *
 * Renders the signed envelope as a QR code on-device. The user scans
 * it (or pastes the JSON into the verifier dashboard's textarea) and
 * the PC verifier processes the envelope via its existing
 * `POST /api/result` path. Per Architecture §10 and FR-TR-2 this is
 * the fallback path when local Wi-Fi is not available.
 *
 * `send()` is suspending so the contract matches [Transport]; it
 * performs the encoding off the main thread and returns a
 * `TransportResult` with `ok=true` and the envelope JSON in
 * `telemetry["envelope_json"]`. The verifier has no signature of
 * its own here — the QR is a transport layer, not a verifier side.
 *
 * QR capacity: a 2.9 KB QR at error-correction L holds a fully
 * padded envelope (~412 bytes today) with plenty of headroom.
 */
class QrFallbackTransport(
    private val qrSizePx: Int = DEFAULT_QR_SIZE_PX,
    private val errorCorrection: ErrorCorrectionLevel = ErrorCorrectionLevel.L,
) : Transport {

    /**
     * Build the QR payload string for an envelope. Same JSON shape
     * the verifier consumes via `/api/result`:
     * `{data, sig, alg, keyAlias}`.
     */
    fun encodeEnvelope(envelope: IntegrityManager.Envelope): String =
        JSONObject().apply {
            put("data", envelope.data)
            put("sig", envelope.sig)
            put("alg", envelope.alg)
            put("keyAlias", envelope.keyAlias)
        }.toString()

    /**
     * Render the QR code for the envelope as a ZXing [BitMatrix].
     * The UI is responsible for drawing the bit matrix on the screen
     * (e.g. via a `Bitmap` + `ImageView`).
     */
    fun renderQr(envelope: IntegrityManager.Envelope): BitMatrix =
        renderQrFromString(encodeEnvelope(envelope))

    fun renderQrFromString(payload: String): BitMatrix {
        val hints = mapOf<EncodeHintType, Any>(
            EncodeHintType.ERROR_CORRECTION to errorCorrection,
            EncodeHintType.MARGIN to 1,
            EncodeHintType.CHARACTER_SET to "UTF-8",
        )
        return QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, qrSizePx, qrSizePx, hints)
    }

    override suspend fun send(envelope: IntegrityManager.Envelope): TransportResult =
        withContext(Dispatchers.Default) {
            val t0 = System.currentTimeMillis()
            val payload = encodeEnvelope(envelope)
            try {
                // Refuse silently-truncating; if the payload exceeds the
                // documented QR capacity, fall through to the local Wi-Fi
                // path. We never chop the envelope.
                PayloadTruncator.checkQrFits(payload)
                renderQrFromString(payload)
                TransportResult(
                    ok = true,
                    reason = null,
                    decision = null,
                    telemetry = mapOf(
                        "transport" to "qr",
                        "envelope_json" to payload,
                        "qr_size_px" to qrSizePx,
                    ),
                    telemetrySha256 = null,
                    receiptPath = null,
                    serverVersion = null,
                    httpStatus = 0, // 0 = never hit the wire
                    roundTripMs = System.currentTimeMillis() - t0,
                )
            } catch (e: PayloadTruncator.QrOverflowException) {
                TransportResult.localError(
                    "qr-overflow:${e.message}",
                    System.currentTimeMillis() - t0,
                )
            } catch (e: WriterException) {
                TransportResult.localError(
                    "qr-encode-failed:${e.message ?: e.javaClass.simpleName}",
                    System.currentTimeMillis() - t0,
                )
            } catch (e: IllegalArgumentException) {
                TransportResult.localError(
                    "qr-payload-too-large:${e.message ?: ""}",
                    System.currentTimeMillis() - t0,
                )
            } catch (e: Exception) {
                TransportResult.localError(
                    "qr-unexpected:${e.javaClass.simpleName}:${e.message ?: ""}",
                    System.currentTimeMillis() - t0,
                )
            }
        }

    companion object {
        // 480 px is comfortable for a phone scanner at arm's length.
        const val DEFAULT_QR_SIZE_PX: Int = 480
    }
}
