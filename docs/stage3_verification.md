# Stage 3 — Frame/ROI quality gate: verification

Operator-side checklist for Stage 3 on the verified Windows host. The
build cannot be exercised from this Linux sandbox; verification happens on
Windows. The **math** behind the Quality Gate is verified in
`tests/test_quality_math.py` — a Python re-implementation that mirrors
the Kotlin code so the algorithms can be unit-tested in the verified venv.

## Files changed in Stage 3

| File | Change |
| --- | --- |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/FrameQuality.kt` | New. Per-frame snapshot data class. |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/FrameMetrics.kt` | New. FPS / drop rate / jitter over a rolling window (120 frames). |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/ExposureStability.kt` | New. `1 - CoV(SENSOR_EXPOSURE_TIME * SENSOR_SENSITIVITY)`. |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/AwbStability.kt` | New. `1 - mean(CoV(R/G), CoV(B/G))`. Null-safe for LEGACY devices. |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/MotionContamination.kt` | New. Per-frame RGB step detector; emits a contamination flag after `streakThreshold` consecutive spikes. |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/QualityGate.kt` | New. Composes everything into a `FrameQuality` snapshot and a `GateDecision ∈ {PASS, RETRY, FAIL}`. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/FrameListener.kt` | Added `onQuality(quality, gate)` with a default no-op so Stage-2 listeners stay compatible. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/CameraSession.kt` | Added a parallel Camera2 capture callback that feeds exposure / sensitivity / AWB gains into the Quality Gate. Emits `onQuality` after every analyzer frame. |
| `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | Status overlay now shows fps / drops / exp-stab / awb-stab / contamination / gate decision. `framesInWindow` switched from `Int` to `AtomicInteger` to remove the analyzer ↔ heartbeat race. |
| `tests/test_quality_math.py` | New. 13 tests covering the math behind FrameMetrics, ExposureStability, AwbStability, MotionContamination. |
| `tests/run_all_tests.py` | Now also loads `tests.test_quality_math`. |

## What Stage 3 does

For every analyzer frame (after AE+AWB lock):

1. `FrameMetrics.record(timestampNs)` → updates the rolling window; on
   demand we read FPS / drop rate / jitter.
2. `ExposureStability.record(exposureNs, sensitivityIso)` → updates the
   rolling CoV of `exposureNs × sensitivityIso`. Null-safe for LEGACY
   devices that don't report one of the two.
3. `AwbStability.record(r, g, b)` → updates rolling CoVs of R/G and B/G.
   Null-safe.
4. `MotionContamination.observe(rgbMeans)` → tracks inter-frame max
   channel step; flips `contaminationFlag = true` after 3 consecutive
   spikes.
5. `QualityGate.decide(hasFace, lockState)` → returns `PASS` / `RETRY`
   / `FAIL`. The decision engine (Stage 11) will eventually consume
   `GateDecision.FAIL → UNCERTAIN` (Architecture §8 / FR-GATE-3) and
   `RETRY → configurable retry path` (Architecture §11 / FR-SESS-6).

All values that aren't observable yet are surfaced as NaN. The Quality
Gate never silently zero-fills — Architecture §11 forbids that, and the
`tests/test_quality_math.py` covers the NaN contract explicitly.

## Steps to verify on Windows

```powershell
cd E:\EdgePPG\android
.\gradlew.bat clean
.\gradlew.bat assembleDebug
adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
adb logcat -s "EdgePPG/*:V"
```

Expected runtime behaviour:

1. Status overlay shows:
   ```
   EdgePPG — Stage 2/3
   lock: LOCKED  face: present
   fps: 29.x  drops: 0.xx
   exp-stab: 0.xx  awb-stab: 0.xx
   contamination: no  gate: PASS
   build: 0.1 (1)
   ```
2. Under steady indoor light: `gate` reaches `PASS` after ~120 frames
   (~4 s) of buffer fill.
3. Under low light: `exp-stab` drops, `gate` may become `FAIL` →
   decision engine (Stage 11) will route to `UNCERTAIN`.
4. During a quick head turn or blink: `contamination` flips to `YES`
   for a few frames; `gate` may go `FAIL` for the duration.

## What to check if the build fails

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Camera2CameraInfo.addSessionCaptureCallback` symbol not found | CameraX version mismatch. | Confirm `1.4.1` in `app/build.gradle.kts`. |
| `COLOR_CORRECTION_GAINS` returns null on every frame | The device may not expose AWB gains (LEGACY level). The `AwbStability` will return NaN; the gate may fail with `awb-stab: —`. | Expected behaviour on some devices; gate goes `RETRY` until other signals recover. |
| `gate: RETRY` indefinitely | AE/AWB never converged, or face never detected. | Check lighting, face in frame, device logs. |

## Acceptance criteria for Stage 3

- [x] `QualityGate.record(...)` takes one frame's worth of evidence; no
      per-frame allocations on the analyzer thread.
- [x] `FrameMetrics.fps()` is NaN with fewer than 2 samples; never
      zero-fills.
- [x] `FrameMetrics.dropRate()` is NaN with fewer than 4 samples.
- [x] `ExposureStability.stability()` is NaN with fewer than 8 samples,
      and stays NaN when the device reports `null` for either input.
- [x] `AwbStability.stability()` is NaN with fewer than 8 samples, and
      stays NaN on LEGACY devices (null gains).
- [x] `MotionContamination.observe(...)` returns `True` after
      `streakThreshold` consecutive >-threshold steps; resets on any
      non-spike.
- [x] `QualityGate.decide(...)` returns `PASS` only when lock, face, FPS,
      drop rate, exposure stability, AWB stability, and contamination all
      satisfy thresholds; never returns `PASS` with `contaminationFlag ==
      true`.
- [x] `CameraSession` attaches a Camera2 capture callback that publishes
      exposure / sensitivity / AWB into the gate.
- [x] `FrameListener.onQuality(...)` is invoked per frame with a snapshot
      + decision; the default is a no-op so existing callers are
      unaffected.
- [x] All Quality-Gate math is mirrored in `tests/test_quality_math.py`
      and all 13 tests pass.
- [ ] On-Windows `./gradlew.bat assembleDebug` succeeds.
- [ ] APK installs and launches on the iQOO.
- [ ] Status overlay shows real `fps`, `drops`, `exp-stab`, `awb-stab`,
      `contamination`, `gate` values.
- [ ] Under steady light `gate` reaches `PASS`.
- [ ] Under motion / blink `contamination` flips to `YES`; `gate` flips
      to `FAIL`.