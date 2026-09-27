package com.edgeppg.app.integrity

/**
 * Stage 16 Task 3 — Office Kit interface + NoOp default.
 *
 * Per `Requirements §FR-VER-3` and `docs/ANDROID_ENVIRONMENT.md`,
 * Office Kit is a "vendor-specific mobile-to-PC integration suite"
 * that the verifier may support as an **optional, additive** transport
 * layer. It SHALL NOT replace or compromise the baseline standalone
 * verifier path.
 *
 * This file declares the interface and a `NoOp` default. The
 * baseline flow (per Stage 13: `LocalWifiTransport` +
 * `QrFallbackTransport` posting to `verifier/server.py`) does not
 * depend on Office Kit and is the canonical EdgePPG path. A real
 * vendor implementation would be a separate AAR / module that
 * implements [OfficeKit] and is registered at app start; the
 * absence of that registration is exactly the same as the current
 * behaviour. Per the claim-discipline rule, this file does not
 * claim a working Office Kit integration unless verified on the
 * target vendor's SDK.
 *
 * The interface surface is intentionally minimal — it is the
 * seam the vendor SDK would plug into, not a behaviour contract
 * the rest of the system depends on.
 */
interface OfficeKit {

    /**
     * Whether this Office Kit implementation is actually available
     * on the device. The NoOp default always returns `false`. A
     * real vendor implementation returns `true` after its SDK is
     * registered (e.g. via `initSdk` in `Application.onCreate`).
     */
    val isAvailable: Boolean

    /**
     * Optional alternative transport for the signed envelope. The
     * baseline path uses [com.edgeppg.app.transport.Transport]
     * directly; this hook exists so a vendor SDK can offer its
     * own delivery (e.g. proprietary pairing, push notification)
     * without changing the rest of the app.
     *
     * The NoOp default returns `false` ("not handled by Office
     * Kit") which signals the caller to fall back to the baseline
     * [com.edgeppg.app.transport.Transport].
     */
    fun tryDeliver(envelope: IntegrityManager.Envelope): Boolean
}

/**
 * Default Office Kit implementation. `isAvailable` is `false`;
 * `tryDeliver` always returns `false`. The baseline app flow
 * uses this — every envelope goes through the canonical
 * [com.edgeppg.app.transport.Transport] path.
 */
object NoOpOfficeKit : OfficeKit {
    override val isAvailable: Boolean = false
    override fun tryDeliver(envelope: IntegrityManager.Envelope): Boolean = false
}
