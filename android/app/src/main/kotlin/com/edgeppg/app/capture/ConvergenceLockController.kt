package com.edgeppg.app.capture

import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult

/**
 * Watches `CONTROL_AE_STATE` and `CONTROL_AWB_STATE` via Camera2 capture
 * callbacks and fires [onConverged] exactly once when both report
 * `CONVERGED`. The caller is then expected to rebind use-cases with
 * `CONTROL_AE_LOCK = true` and `CONTROL_AWB_LOCK = true` so that exposure
 * and white balance stop drifting during the rPPG window.
 *
 * Why "converge-then-lock" matters (Architecture §4.1, v2-1 page 1):
 *  Locking exposure before AE converges freezes a bad exposure and destroys
 *  POS SNR. We watch the convergence state for a few frames and only then
 *  commit to the locked configuration.
 *
 * Robustness:
 *  * `null` AWB state on LEGACY-level devices (some front cameras) is
 *    treated as converged once AE converges — we never deadlock waiting
 *    for a state that never arrives.
 *  * `FLASH_REQUIRED` AE state means AE gave up (scene too dark). We do
 *    NOT lock in that case; the Quality Gate (Stage 3) routes to
 *    `UNCERTAIN` and the UI shows the low-light warning.
 *
 * API note: the callback is set on the Camera2 use-case via
 * `Camera2Interop.Extender(builder).setSessionCaptureCallback(callback)`
 * (CameraX 1.4.x). The use-case Extender is the documented public API;
 * `Camera2CameraInfo.addSessionCaptureCallback` does NOT exist in
 * 1.4.1.
 *
 * The controller exposes a single public method [onCaptureResult] that
 * the caller invokes from inside its `setSessionCaptureCallback`
 * callback. This keeps the controller's convergence state
 * encapsulated and avoids leaking the `addSessionCaptureCallback` API
 * into this file.
 */
class ConvergenceLockController(
    private val onLockState: (locked: Boolean) -> Unit = {},
) {
    @Volatile var isLocked: Boolean = false
        private set

    @Volatile private var fired = false
    @Volatile private var aeConverged = false
    @Volatile private var awbConverged = false

    /**
     * Process a single `TotalCaptureResult` from the camera session.
     * Called from inside the use-case Extender's
     * `setSessionCaptureCallback` callback. When both AE and AWB
     * have reported CONVERGED, this fires [onConverged] exactly once
     * and locks the session via `session.stopRepeating()`.
     *
     * `onLockState(true)` is fired before `session.stopRepeating()` so
     * the caller can observe the transition.
     */
    fun onCaptureResult(
        session: CameraCaptureSession,
        result: TotalCaptureResult,
        onConverged: () -> Unit,
    ) {
        if (isLocked || fired) return
        val ae = result.get(CaptureResult.CONTROL_AE_STATE)
        val awb = result.get(CaptureResult.CONTROL_AWB_STATE)

        if (ae == CaptureResult.CONTROL_AE_STATE_CONVERGED) {
            aeConverged = true
        }
        if (awb == null ||
            awb == CaptureResult.CONTROL_AWB_STATE_CONVERGED
        ) {
            awbConverged = true
        }
        // FLASH_REQUIRED means AE gave up (too dark) — keep unlocked
        // so the Quality Gate can route to UNCERTAIN.
        if (aeConverged && awbConverged && !fired) {
            fired = true
            isLocked = true
            onLockState(true)
            onConverged()
        }
    }

    fun reset() {
        isLocked = false
        fired = false
        aeConverged = false
        awbConverged = false
        onLockState(false)
    }
}
