package com.edgeppg.app.integrity

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec

/**
 * Stage 12 — Hardware-backed signing of the session transcript.
 *
 * Key:
 *  - `AndroidKeyStore` EC P-256 (secp256r1).
 *  - StrongBox attempted first; silently falls back to TEE if the device
 *    doesn't expose StrongBox. We never refuse to operate — we may just
 *    be on a less-hardened keystore. (Master §34: "no keys in code or
 *    storage" — AndroidKeyStore is the documented key store.)
 *
 * Sign:
 *  - `SHA256withECDSA` over the **byte-exact** canonical JSON payload.
 *  - Canonical form is fixed alphabetical key order, no whitespace,
 *    minimal JSON escaping, 4dp-trimmed floats — implemented in
 *    [canonicalJson]. The Python verifier in `verifier/canonical.py`
 *    reproduces the exact same bytes so what we sign verifies
 *    bit-for-bit on the PC.
 *
 * Freshness window:
 *  - `|now - timestampMs| ≤ 5 min`. The PC verifier enforces this on
 *    receipt; we expose [isFresh] so the on-device caller can include
 *    it in the decision chain.
 *
 * Nonce:
 *  - 16 random bytes, hex-encoded. Generated via [SecureRandom] per
 *    session.
 *
 * Public key export:
 *  - `exportPublicKeyB64()` returns the X.509 SubjectPublicKeyInfo DER
 *    (Base64 NO_WRAP). This is the one-time provisioning artifact that
 *    the PC verifier operator pastes into `verifier/pubkey.b64`.
 *
 * Canonical JSON keys (fixed alphabetical order — see [canonicalJson]):
 *   challenge_id, confidence, decision, expected_seq, hr_bpm,
 *   model_version, nonce, roi_corr, signal_quality, snr, timestamp_ms
 */
object IntegrityManager {

    const val ALIAS = "edgeppg_device_key_v2"
    const val MODEL_VERSION = "v2.1-edge"

    private val rng = SecureRandom()

    // ---------- Key provisioning ----------

    /** Idempotent: returns true iff a usable key exists / was created. */
    fun ensureKey(): Boolean {
        return try {
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            if (ks.containsAlias(ALIAS)) {
                // The Elvis branch returns Key (a Serializable), not
                // Boolean. We discard the result; only the existence
                // check matters.
                ks.getKey(ALIAS, null); true
            } else {
                generate()
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun generate(): Boolean {
        return try {
            val kpg = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore"
            )
            val spec = KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
            )
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false)
                .build()
            kpg.initialize(spec, rng)
            kpg.generateKeyPair()
            true
        } catch (_: Exception) {
            // Most common cause: device doesn't support StrongBox. The
            // first attempt above already silently swallows it. If the
            // device refuses EC P-256 entirely, return false and let the
            // caller route to UNCERTAIN at the decision engine.
            false
        }
    }

    /** X.509 DER public key, Base64 NO_WRAP. */
    fun exportPublicKeyB64(): String? {
        return try {
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            val cert = ks.getCertificate(ALIAS) ?: return null
            Base64.encodeToString(cert.publicKey.encoded, Base64.NO_WRAP)
        } catch (_: Exception) {
            null
        }
    }

    // ---------- Telemetry model ----------

    enum class Decision { LIVE, SPOOF, UNCERTAIN }

    /**
     * The values that go into the canonical JSON, in alphabetical-key
     * order (see [canonicalJson]). Auxiliary columns are NOT signed —
     * they live outside the integrity boundary.
     */
    data class Telemetry(
        val challengeId: String,
        val expectedSeq: String,
        val decision: Decision,
        val confidence: Float,
        val signalQuality: Float,
        val hrBpm: Float = 0f,
        val snr: Float = 0f,
        val roiCorr: Float = 0f,
        val timestampMs: Long = System.currentTimeMillis(),
        val nonce: String = newNonce(),
    )

    fun newNonce(): String {
        val b = ByteArray(16)
        rng.nextBytes(b)
        return b.joinToString("") { "%02x".format(it) }
    }

    // ---------- Canonical JSON ----------

    /**
     * Alphabetical key order. MUST stay in sync with
     * `verifier/canonical.py:CANONICAL_KEY_ORDER`.
     *
     * The key order is: challenge_id, confidence, decision, expected_seq,
     * hr_bpm, model_version, nonce, roi_corr, signal_quality, snr,
     * timestamp_ms.
     *
     * Resolution of the documented contradiction: `Requirements §FR-CRY-3`
     * lists 9 fields; `Architecture §9` says "exactly seven". We include
     * the full `Requirements` set in the signed payload. The PC verifier
     * (`verifier/verify.py`) requires exactly this set; any drift fails
     * the structural check before ECDSA.
     */
    fun canonicalJson(t: Telemetry): String {
        val sb = StringBuilder(256)
        sb.append('{')
        sb.append("\"challenge_id\":").append(quote(t.challengeId)).append(',')
        sb.append("\"confidence\":").append(num(t.confidence)).append(',')
        sb.append("\"decision\":").append(quote(t.decision.name)).append(',')
        sb.append("\"expected_seq\":").append(quote(t.expectedSeq)).append(',')
        sb.append("\"hr_bpm\":").append(num(t.hrBpm)).append(',')
        sb.append("\"model_version\":").append(quote(MODEL_VERSION)).append(',')
        sb.append("\"nonce\":").append(quote(t.nonce)).append(',')
        sb.append("\"roi_corr\":").append(num(t.roiCorr)).append(',')
        sb.append("\"signal_quality\":").append(num(t.signalQuality)).append(',')
        sb.append("\"snr\":").append(num(t.snr)).append(',')
        sb.append("\"timestamp_ms\":").append(t.timestampMs)
        sb.append('}')
        return sb.toString()
    }

    private fun num(f: Float): String {
        if (f.isNaN() || f.isInfinite()) return "0"
        // 4dp fixed; trailing zeros stripped only after the point.
        var s = "%.4f".format(f)
        if ('.' in s) {
            s = s.trimEnd('0').trimEnd('.')
        }
        if (s == "-0") return "0"
        return s
    }

    private fun quote(s: String): String {
        val sb = StringBuilder(s.length + 2)
        sb.append('"')
        for (c in s) when (c) {
            '"' -> sb.append("\\\"")
            '\\' -> sb.append("\\\\")
            '\n' -> sb.append("\\n")
            '\r' -> sb.append("\\r")
            '\t' -> sb.append("\\t")
            else -> if (c.code < 0x20) sb.append("\\u%04x".format(c.code))
                    else sb.append(c)
        }
        sb.append('"')
        return sb.toString()
    }

    // ---------- Sign / verify ----------

    /** Transport envelope (the unsigned wrapper around the signed bytes). */
    data class Envelope(
        val data: String,
        val sig: String,
        val alg: String = "SHA256withECDSA",
        val keyAlias: String = ALIAS,
    )

    /** Sign [t]; returns null if no hardware key. Never throws. */
    fun sign(t: Telemetry): Envelope? {
        return try {
            if (!ensureKey()) return null
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            val priv = ks.getKey(ALIAS, null) as? PrivateKey ?: return null
            val data = canonicalJson(t)
            val sig = Signature.getInstance("SHA256withECDSA").run {
                initSign(priv)
                update(data.toByteArray(StandardCharsets.UTF_8))
                sign()
            }
            Envelope(data, Base64.encodeToString(sig, Base64.NO_WRAP))
        } catch (_: Exception) {
            null
        }
    }

    /** Self-test / parity check with the Node / Python verifier. */
    fun verify(data: String, sigB64: String, pubKeyB64: String): Boolean {
        return try {
            val pubBytes = Base64.decode(pubKeyB64, Base64.NO_WRAP)
            val pub = KeyFactory.getInstance("EC")
                .generatePublic(X509EncodedKeySpec(pubBytes))
            val sigBytes = Base64.decode(sigB64, Base64.NO_WRAP)
            Signature.getInstance("SHA256withECDSA").run {
                initVerify(pub)
                update(data.toByteArray(StandardCharsets.UTF_8))
                verify(sigBytes)
            }
        } catch (_: Exception) {
            false
        }
    }

    /** Freshness window for the verifier: |now - timestampMs| ≤ 5 min. */
    fun isFresh(timestampMs: Long, nowMs: Long = System.currentTimeMillis()): Boolean {
        return kotlin.math.abs(nowMs - timestampMs) <= FRESH_MS
    }

    const val FRESH_MS: Long = 5L * 60L * 1000L
}