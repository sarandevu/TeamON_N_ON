# Stage 2 — Camera acquisition + face mesh + ROI emission: verification

Operator-side checklist for Stage 2 on the verified Windows host. The build
cannot be exercised from this Linux sandbox; verification happens on Windows.

## Files changed in Stage 2

| File | Change |
| --- | --- |
| `android/app/build.gradle.kts` | Added `com.google.mlkit:face-mesh-detection:16.0.0-beta1`. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/FrameListener.kt` | New. Callback surface for the analyzer thread. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/ConvergenceLockController.kt` | New. AE/AWB converge-then-lock watcher. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/RoiTracker.kt` | New. ML Kit Face Mesh → 3 ROIs (forehead, L/R cheek) with EMA smoothing + zero-alloc RGB mean sampling from YUV_420_888. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/CameraSession.kt` | New. Owns the `ProcessCameraProvider`, binds `Preview` + `ImageAnalysis`, drives the analyzer. |
| `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | Rewritten: PreviewView + status overlay; FPS counter via `lifecycleScope` heartbeat; handles `FrameListener`. |
| `android/app/src/main/res/values/styles.xml` | Switched to `Theme.Material.NoActionBar` with a black window background so the camera preview is visible. |
| `docs/implementation_plan.md`, `docs/current_state.md` | Stage 2 progress recorded. |

## What Stage 2 does

1. Acquires the front camera via CameraX 1.4.1.
2. Renders the camera preview into a full-screen `PreviewView`.
3. Streams `YUV_420_888` frames at 1080p target to a single-threaded
   analyzer executor with `STRATEGY_KEEP_ONLY_LATEST`.
4. Runs ML Kit Face Mesh (468-pt) on every 3rd frame; reuses the last
   smoothed ROIs on skipped frames. Bounded wait of 33 ms (1 frame budget)
   on the detector's async completion.
5. Computes mean R/G/B per ROI directly from the YUV planes (stride-sampled
   every 4th pixel, BT.601 full-range integer path), zero per-frame heap
   allocations on the analyzer thread.
6. Watches `CONTROL_AE_STATE` / `CONTROL_AWB_STATE` via a Camera2 session
   capture callback. Once both report `CONVERGED`, rebinds the use-cases
   with `CONTROL_AE_LOCK = true` and `CONTROL_AWB_LOCK = true`. Frames
   emitted before the lock are dropped — they would corrupt the rPPG
   signal with auto-exposure / AWB drift.

## Steps to verify on Windows

```powershell
cd E:\EdgePPG\android
.\gradlew.bat clean
.\gradlew.bat assembleDebug
# APK at E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk

adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
```

Expected runtime behaviour:

1. On first launch, the Android camera permission prompt appears.
2. Once granted, the front-camera preview is visible full-screen.
3. The status overlay at the bottom shows:
   ```
   EdgePPG — Stage 2
   lock: converging…   (then)  lock: LOCKED
   face: present       (or)    face: lost
   fps:  29.x
   dev_mode: true
   build: 0.1 (1)
   ```
4. `adb logcat -s "EdgePPG/*:V"` shows:
   ```
   I/EdgePPG/stage: [stage2] MainActivity.onCreate — preview view, status overlay wired
   I/EdgePPG/stage: [stage2] CAMERA permission=GRANTED — starting session
   I/EdgePPG/stage: [stage2] AE/AWB LOCKED — DSP frames will start
   I/EdgePPG/capture: face restored
   ```

## What to check if the build fails

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Manifest merger failed: uses-feature camera.front required=true` | iQOO 15 has a front camera; this should not fail on the verified device. If a different device is connected, the build will refuse. | Use the iQOO. |
| `CameraX version conflict` | Some other dependency pulls a different CameraX. | `.\gradlew.bat dependencies --configuration debugRuntimeClasspath` and resolve the conflict. |
| `ML Kit Face Mesh not found` | Wrong artifact. | Confirm `com.google.mlkit:face-mesh-detection:16.0.0-beta1` is in `app/build.gradle.kts`. |
| `PreviewView not bound` | `setSurfaceProvider` mis-called. | Check `CameraSession.bindUseCases` — we use `preview.setSurfaceProvider(previewView.surfaceProvider)`. |
| Black screen | The analyzer thread is dropping all frames because AE/AWB never converges (very low light). | Verify the front camera is not covered; rotate device; the Quality Gate (Stage 3) will route to UNCERTAIN in that case once wired. |

## Acceptance criteria for Stage 2

- [x] `CameraSession` binds `Preview` + `ImageAnalysis` with Camera2
      interop AE/AWB lock options on the locked-rebind path.
- [x] `ConvergenceLockController` watches AE/AWB state, fires
      `onConverged` exactly once, treats null-AWB as converged, refuses
      to lock on `FLASH_REQUIRED`.
- [x] `RoiTracker` produces 3 ROIs (forehead, L cheek, R cheek) from the
      ML Kit Face Mesh bounding box with documented fractional coords.
- [x] `RoiTracker.meanRgbPerRoi` is zero-alloc on the hot path
      (no Bitmap, no per-frame FloatArray allocation, reused buffer).
- [x] `FrameListener` is documented and stable; no PII / key material
      ever crosses the callback.
- [x] `MainActivity` requests CAMERA permission via the modern Activity
      Result API and binds `CameraSession` on grant.
- [ ] On-Windows `./gradlew.bat assembleDebug` succeeds.
- [ ] APK installs and launches on the iQOO.
- [ ] Front-camera preview is visible full-screen.
- [ ] Logcat shows `AE/AWB LOCKED` after a brief converge window.
- [ ] Logcat shows `face restored` / `face lost` toggling as the user
      moves in and out of frame.
- [ ] FPS readout in the overlay is ≥ 25 fps under normal light.

The last six items are operator-verified at this checkpoint.
