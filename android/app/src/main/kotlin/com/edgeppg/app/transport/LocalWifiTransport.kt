package com.edgeppg.app.transport

import com.edgeppg.app.integrity.IntegrityManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Stage 13 — Local Wi-Fi & USB primary transport.
 *
 * POSTs the signed envelope as JSON to the PC verifier's
 * `POST /api/result` endpoint. Also supports:
 * - Live real-time progress streaming (`POST /api/live`)
 * - Auto-syncing active scheduled/waiting calls (`GET /api/calls`)
 */
class LocalWifiTransport(
    private val baseUrl: String = DEFAULT_BASE_URL,
    private val path: String = DEFAULT_PATH,
    private val client: OkHttpClient = defaultClient(),
) : Transport {

    var activeCallId: String? = null
    var activeApplicantRef: String? = null

    private fun getCandidateBaseUrls(): List<String> {
        return if (baseUrl == DEFAULT_BASE_URL) {
            listOf(
                "http://127.0.0.1:8080",
                "http://10.65.167.49:8080",
                "http://10.0.2.2:8080",
                "http://10.2.37.235:8080",
            )
        } else {
            listOf(baseUrl.trimEnd('/'))
        }
    }

    override suspend fun send(envelope: IntegrityManager.Envelope): TransportResult =
        withContext(Dispatchers.IO) {
            val t0 = System.currentTimeMillis()
            val payload = encodeEnvelope(envelope)
            val candidateUrls = getCandidateBaseUrls().map { "$it$path" }
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
     * Send real-time telemetry metrics to the PC verifier dashboard.
     * Non-blocking, fast 1-second timeout.
     */
    suspend fun sendLiveProgress(jsonPayload: String): Boolean =
        withContext(Dispatchers.IO) {
            for (base in getCandidateBaseUrls()) {
                val url = "$base/api/live"
                try {
                    val req = Request.Builder()
                        .url(url)
                        .post(jsonPayload.toRequestBody(JSON))
                        .build()
                    client.newCall(req).execute().use { resp ->
                        if (resp.isSuccessful) return@withContext true
                    }
                } catch (_: Exception) {}
            }
            false
        }

    /**
     * Fetch active call from PC verifier (WAITING or SCHEDULED).
     * Returns Triple(callId, applicantRef, applicantName) or null if offline.
     */
    suspend fun fetchActiveCall(): Triple<String, String, String>? =
        withContext(Dispatchers.IO) {
            for (base in getCandidateBaseUrls()) {
                val url = "$base/api/calls"
                try {
                    val req = Request.Builder().url(url).get().build()
                    client.newCall(req).execute().use { resp ->
                        if (!resp.isSuccessful) return@use
                        val body = resp.body?.string().orEmpty()
                        val json = JSONObject(body)
                        val calls = json.optJSONArray("calls") ?: JSONArray()
                        var waitingCall: Triple<String, String, String>? = null
                        var scheduledCall: Triple<String, String, String>? = null
                        var lastCall: Triple<String, String, String>? = null

                        for (i in 0 until calls.length()) {
                            val c = calls.optJSONObject(i) ?: continue
                            val cid = c.optString("call_id", "")
                            val ref = c.optString("applicant_ref", "")
                            val name = c.optString("applicant_name", ref)
                            val status = c.optString("status", "")
                            if (cid.isEmpty()) continue
                            val t = Triple(cid, ref, name)
                            lastCall = t
                            if (status == "WAITING" && waitingCall == null) {
                                waitingCall = t
                            } else if (status == "SCHEDULED" && scheduledCall == null) {
                                scheduledCall = t
                            }
                        }
                        val chosen = waitingCall ?: scheduledCall ?: lastCall
                        if (chosen != null) return@withContext chosen
                    }
                } catch (_: Exception) {}
            }
            null
        }

    private fun encodeEnvelope(e: IntegrityManager.Envelope): String =
        JSONObject().apply {
            put("data", e.data)
            put("sig", e.sig)
            put("alg", e.alg)
            put("keyAlias", e.keyAlias)
            if (!activeCallId.isNullOrBlank()) {
                put("call_id", activeCallId)
            }
            if (!activeApplicantRef.isNullOrBlank()) {
                put("applicant_ref", activeApplicantRef)
            }
        }.toString()

    /**
     * Mirror of `verifier/server.py:handle_result` JSON output.
     */
    private fun parseResponse(httpStatus: Int, body: String, ms: Long): TransportResult {
        return try {
            val obj = JSONObject(body)
            val ok = obj.optBoolean("ok", false)
            val decision = obj.optJSONObject("telemetry")?.optString("decision")?.takeIf { it.isNotEmpty() }
            val telemetry = obj.optJSONObject("telemetry")?.let { jsonToMap(it) }
            val reason = obj.optString("reason").takeIf { it.isNotEmpty() }
            val receipt = obj.optString("receipt").takeIf { it.isNotEmpty() }
            TransportResult(
                ok = ok,
                reason = if (ok) null else (reason ?: "verifier-rejected"),
                decision = decision,
                telemetry = telemetry,
                telemetrySha256 = obj.optString("telemetry_sha256").takeIf { it.isNotEmpty() },
                receiptPath = receipt,
                serverVersion = obj.optString("server_version").takeIf { it.isNotEmpty() },
                httpStatus = httpStatus,
                roundTripMs = ms,
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
        const val DEFAULT_BASE_URL: String = "http://10.0.2.2:8080"
        const val DEFAULT_PATH: String = "/api/result"
        private val JSON = "application/json; charset=utf-8".toMediaType()

        private fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(1, TimeUnit.SECONDS)
            .readTimeout(3, TimeUnit.SECONDS)
            .writeTimeout(3, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

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
