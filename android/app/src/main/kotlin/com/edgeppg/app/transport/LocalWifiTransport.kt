package com.edgeppg.app.transport

import com.edgeppg.app.integrity.IntegrityManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Stage 13 — Local Wi-Fi primary transport.
 *
 * POSTs the signed envelope as JSON to the PC verifier's
 * `POST /api/result` endpoint. Per Architecture §10 and
 * Requirements §FR-TR-1, this is the primary transport.
 *
 * The verifier URL is configurable via [baseUrl]; default is
 * `http://10.0.2.2:8080` (the Android emulator alias for the host
 * machine) which is harmless on a real device — the operator can
 * override at construction time with the laptop's LAN IP.
 *
 * No cloud. No Internet. The phone talks only to the laptop's
 * verifier on the local network.
 */
class LocalWifiTransport(
    private val baseUrl: String = DEFAULT_BASE_URL,
    private val path: String = DEFAULT_PATH,
    private val client: OkHttpClient = defaultClient(),
) : Transport {

    override suspend fun send(envelope: IntegrityManager.Envelope): TransportResult =
        withContext(Dispatchers.IO) {
            val t0 = System.currentTimeMillis()
            val payload = encodeEnvelope(envelope)
            val candidateUrls = if (baseUrl == DEFAULT_BASE_URL) {
                listOf(
                    "http://10.2.37.235:8080$path",
                    "http://127.0.0.1:8080$path",
                    "http://172.20.10.3:8080$path",
                    "http://10.0.2.2:8080$path",
                )
            } else {
                listOf(baseUrl.trimEnd('/') + path)
            }
            var lastErr: Exception? = null
            for (candidateUrl in candidateUrls) {
                val request = try {
                    Request.Builder()
                        .url(candidateUrl)
                        .post(payload.toRequestBody(JSON))
                        .build()
                } catch (e: IllegalArgumentException) {
                    return@withContext TransportResult.localError(
                        "bad-url:${e.message}",
                        System.currentTimeMillis() - t0,
                    )
                }
                try {
                    return@withContext client.newCall(request).execute().use { resp ->
                        val body = resp.body?.string().orEmpty()
                        val ms = System.currentTimeMillis() - t0
                        parseResponse(resp.code, body, ms)
                    }
                } catch (e: Exception) {
                    lastErr = e
                }
            }
            TransportResult.localError(
                "network-error:${lastErr?.javaClass?.simpleName ?: "Exception"}:${lastErr?.message ?: ""}",
                System.currentTimeMillis() - t0,
            )
        }

    /**
     * Mirror of `verifier/server.py:handle_result` JSON output.
     * Returns null on malformed responses (the caller treats null as
     * `ok=false` with a generic reason).
     */
    private fun parseResponse(httpStatus: Int, body: String, ms: Long): TransportResult {
        return try {
            val obj = JSONObject(body)
            val ok = obj.optBoolean("ok", false)
            val decision = obj.optJSONObject("telemetry")?.optString("decision")?.takeIf { it.isNotEmpty() }
            val telemetry = obj.optJSONObject("telemetry")?.let { jsonToMap(it) }
            val reason = obj.optString("reason").takeIf { it.isNotEmpty() }
            TransportResult(
                ok = ok,
                reason = if (ok) null else (reason ?: "verifier-rejected"),
                decision = decision,
                telemetry = telemetry,
                telemetrySha256 = obj.optString("telemetry_sha256").takeIf { it.isNotEmpty() },
                receiptPath = null,
                serverVersion = obj.optString("server_version").takeIf { it.isNotEmpty() },
                httpStatus = httpStatus,
                roundTripMs = ms,
                // Full decoded body: verification callers use the
                // typed fields above; Join Call callers read `action`
                // / `session_seed` / `verifier_nonce` from here.
                rawResponse = jsonToMap(obj),
            )
        } catch (e: Exception) {
            TransportResult(
                ok = false,
                reason = "parse-error:${e.javaClass.simpleName}",
                decision = null,
                telemetry = null,
                telemetrySha256 = null,
                receiptPath = null,
                serverVersion = null,
                httpStatus = httpStatus,
                roundTripMs = ms,
            )
        }
    }

    companion object {
        // Android emulator's loopback to the host machine. On a real
        // iQOO the operator should construct with the laptop's LAN IP.
        const val DEFAULT_BASE_URL: String = "http://10.0.2.2:8080"
        const val DEFAULT_PATH: String = "/api/result"
        private val JSON = "application/json; charset=utf-8".toMediaType()

        private fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

        private fun encodeEnvelope(e: IntegrityManager.Envelope): String =
            JSONObject().apply {
                put("data", e.data)
                put("sig", e.sig)
                put("alg", e.alg)
                put("keyAlias", e.keyAlias)
            }.toString()

        private fun jsonToMap(obj: JSONObject): Map<String, Any?> {
            val out = LinkedHashMap<String, Any?>()
            val it = obj.keys()
            while (it.hasNext()) {
                val k = it.next()
                val v = obj.opt(k)
                out[k] = if (v == JSONObject.NULL) null else v
            }
            return out
        }
    }
}
