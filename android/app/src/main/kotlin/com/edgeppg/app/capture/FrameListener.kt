package com.edgeppg.app.capture

import com.edgeppg.app.quality.FrameQuality
import com.edgeppg.app.quality.QualityGate

/**
 * Callback surface for the camera capture pipeline (Stages 2 → 3).
 *
 * Stage-2 contract:
 *  - `onFrameMeans` is invoked from the analyzer thread at most once per
 *    analyzed frame. Implementations must be non-blocking; the analyzer
 *    thread is single-threaded and `KEEP_ONLY_LATEST` is in effect.
 *  - `rgbMeans` is a length-9 float array in [0, 255]:
 *      [rForehead, gForehead, bForehead,
 *       rLeftCheek, gLeftCheek, bLeftCheek,
 *       rRightCheek, gRightCheek, bRightCheek]
 *    The same array instance is reused across calls — copy out what you
 *    need before crossing threads.
 *  - `timestampNs` is the SENSOR_TIMESTAMP (`ImageInfo.timestamp`) in
 *    nanoseconds. We use this for rPPG signal timing (Stage 4); wall-clock
 *    time is never used for signal analysis.
 *  - `frameNumber` is a monotonically increasing counter local to the
 *    capture session — useful for FPS / drop-rate diagnostics (Stage 3).
 *  - `onLockStateChanged` fires exactly once when AE + AWB converge
 *    (Stage-2 `ConvergenceLockController`); `locked=true` indicates the
 *    use-cases have been re-bound with `CONTROL_AE_LOCK` /
 *    `CONTROL_AWB_LOCK`.
 *  - `onFaceLost` fires when the face detector returns no mesh. After
 *    `onFaceLost`, `onFrameMeans` will not fire until a face is detected
 *    again. The pipeline never silently emits zeroed means.
 *  - `onFaceRestored` fires symmetrically when a previously lost face is
 *    detected again. Helpful for the quality gate (Stage 3) and the UI
 *    (Stage 15).
 *
 * Stage-3 additions:
 *  - `onQuality` fires after each frame with the latest [FrameQuality]
 *    snapshot. Implementations may ignore it for now; the UI (Stage 15)
 *    and the decision engine (Stage 11) will subscribe.
 *  - `gateDecision` is the current [QualityGate.GateDecision]. The
 *    decision engine (Stage 11) treats FAIL → UNCERTAIN and RETRY → the
 *    configurable retry path (Architecture §11).
 */
interface FrameListener {
    fun onFrameMeans(
        rgbMeans: FloatArray,
        timestampNs: Long,
        frameNumber: Long,
    )

    fun onLockStateChanged(locked: Boolean)

    fun onFaceLost()

    fun onFaceRestored()

    fun onQuality(quality: FrameQuality, gate: QualityGate.GateDecision) {
        // Default no-op so Stage-2 listeners can ignore Stage-3 callbacks
        // without ceremony. Stage 11 / Stage 15 implement the meaningful
        // behaviour.
    }

    fun onCameraFrame(frameNumber: Long, timestampNs: Long) {}

    fun onPhoneDetected(isDetected: Boolean, reason: String) {}
}
