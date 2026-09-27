# Stage 1 — Android foundation: verification (historical, kept for context)

This doc is preserved as a historical record of Stage 1. The
structural preconditions listed below were verified when Stage 1
landed. **The current state of the codebase is well past Stage 1;
see `README.md` for the current implementation status** and
`docs/implementation_plan.md` Stage 13-15 for the still-outstanding
work.

## Status

**DONE** — Stage 1's structural preconditions were verified by
the source-contract test suite (`tests/test_transport_contract.py`
and the Python mirror tests) and the build pipeline now exercises
Stage 1's deliverables in every run.

**Build verification on the verified Windows host is the
operator's next step** per `docs/ANDROID_ENVIRONMENT.md` and is
documented in `README.md`. The known P1 Camera2 interop classpath
issue is the only remaining build error and is documented in
`docs/implementation_plan.md` Stage 13 Task 8 / Stage 15 Task 7.

## Files changed in Stage 1

| File | Change |
| --- | --- |
| `android/app/src/main/AndroidManifest.xml` | added `CAMERA`, `INTERNET`, `ACCESS_NETWORK_STATE` permissions; added front-camera + any-camera `<uses-feature>`. |
| `android/app/src/main/kotlin/com/edgeppg/app/Log.kt` | new structured logger, dev-mode gated. |
| `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | rewritten through Stage 1-15 — `ComponentActivity` originally (Stage 1), now a state-driven UI orchestrator driving the full session flow. The Stage 1 permission + dev-mode heartbeat are still in place. |
| `android/app/build.gradle.kts` | `org.jetbrains.kotlin.android` plugin was added (Stage 1), then removed at Stage 13 Task 8 to make AGP 9.4.1's built-in Kotlin active (KGP 2.2.10 has no `gradle9` variant). `buildConfigField("boolean", "EDGEPPG_DEV_MODE", ...)`, `abiFilters += "arm64-v8a"`, `buildFeatures.buildConfig = true`, Java 17 source/target; CameraX 1.4.1, AndroidX core/appcompat/lifecycle/activity/coroutines, OkHttp 4.12.0, ZXing 3.5.4, JUnit 4.13.2 (`testImplementation`). |
| `android/build.gradle.kts` | `org.jetbrains.kotlin.android` plugin removed at Stage 13 Task 8 (see above); AGP 9.4.1 built-in Kotlin is the active path. |
| `docs/current_state.md`, `docs/implementation_plan.md` | updated at every stage through Stage 15. |

No files were renamed or deleted. The verified Gradle wrapper,
JDK 25.0.3, AGP 9.4.1, compileSdk 37, minSdk 26, targetSdk 37 are
all unchanged. KGP 2.2.10 is **installed** on the verified
environment per `ANDROID_ENVIRONMENT.md` but **not applied** to the
modules — see Stage 13 Task 8 / Stage 15 Task 7 for the documented
opt-out reason.

## Steps to verify on Windows

```powershell
cd E:\EdgePPG\android
.\gradlew.bat clean
.\gradlew.bat assembleDebug
```

Expected result: `BUILD SUCCESSFUL`, APK at
`E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk`.

If `compileDebugKotlin` fails with the documented P1 issue
(`Unresolved reference: addSessionCaptureCallback` or
`gains.size` / `gains[i]`), the fix is documented in
`docs/implementation_plan.md` Stage 15 Task 7.

```powershell
adb devices
# (verify iQOO is online and authorised)
adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
```

Expected runtime behaviour:

1. App launches; status text reads the current state of the
   diagnostic overlay:
   ```
   EdgePPG — Stage 2/3
   lock: LOCKED  face: present
   fps: 29.x  drops: 0.xx
   exp-stab: 0.xx  awb-stab: 0.xx
   contamination: no  gate: PASS
   build: 0.1 (1)
   ```
   (Earlier versions of this doc showed a simpler Stage-1 status
   text. The current text reflects the Stage 1-3 status overlay.)
2. Camera permission prompt appears on first launch (Android will
   issue it before the app sees `GRANTED`). If denied, the status
   text reads `camera: DENIED`.
3. A logcat tail shows the dev-mode heartbeats and stage logs:
   ```
   I/EdgePPG/stage: [stage2] MainActivity.onCreate — preview view, status overlay wired
   I/EdgePPG/stage: [stage2] CAMERA permission=GRANTED — starting session
   I/EdgePPG/stage: [stage2] AE/AWB LOCKED — DSP frames will start
   I/EdgePPG/capture: face restored
   ```

```powershell
adb logcat -s "EdgePPG/*:V"
```

The app's `Log` helper uses the `EdgePPG/*` tag namespace — see
`android/app/src/main/kotlin/com/edgeppg/app/Log.kt`.

## What to check if the build fails

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Plugin [id: 'org.jetbrains.kotlin.android'] was not found` | The KGP plugin was removed at Stage 13 Task 8 because KGP 2.2.10 has no `gradle9` variant. The build relies on AGP 9.4.1's built-in Kotlin. If this error appears, the `KGP plugin removed` step wasn't applied. | Confirm `app/build.gradle.kts` does not have `id("org.jetbrains.kotlin.android")` and that `build.gradle.kts` does not declare KGP. |
| `Cannot add extension with name 'kotlin'` | Same as above — the explicit KGP plugin is conflicting with AGP 9's built-in Kotlin. | Remove the explicit KGP plugin. |
| `compileDebugKotlin` `Unresolved reference 'addSessionCaptureCallback'` (CameraSession.kt) | P1 issue: `androidx.camera.camera2.interop` AAR's `classes.jar` is not on the Kotlin compile classpath under AGP 9.4.1's built-in-Kotlin path. | Add the `androidComponents { onVariants { ... } }` classpath-injection block documented in `docs/implementation_plan.md` Stage 15 Task 7. |
| `compileDebugKotlin` `gains.size` / `gains[i]` unresolved (CameraSession.kt) | Same root cause as above. | Same fix. |
| `Manifest merger failed: uses-feature camera.front required=true` | The verified env may be running on a device without a front camera. | iQOO 15 has a front camera; if a different device is connected, this build will refuse to install. |
| `DependencyResolutionException` for CameraX / OkHttp / ZXing | The first build needs network to pull the AARs. | Ensure `google()` and `mavenCentral()` are reachable on first build. |
| `compileDebugKotlin` reports `signalQuality` unresolved (MainActivity.kt) | Stale source — `FrameQuality` does not have a `signalQuality` field. Use `quality.awbStability` as the proxy. | Refresh `MainActivity.kt` from the latest source. |

## Acceptance criteria for Stage 1

- [x] `AndroidManifest.xml` declares `CAMERA`, `INTERNET`,
      `ACCESS_NETWORK_STATE`, `<uses-feature
      android:name="android.hardware.camera.front" required="true">`.
- [x] `MainActivity` extends `androidx.activity.ComponentActivity`
      and is bound to the Android lifecycle.
- [x] `MainActivity` requests `CAMERA` permission via the modern
      Activity Result API and reflects the result in the UI.
- [x] `Log` utility is dev-mode gated (release builds emit
      `Log.error` only).
- [x] `buildConfigField("boolean", "EDGEPPG_DEV_MODE", ...)` differs
      between debug and release.
- [x] `abiFilters` declares `arm64-v8a` only (iQOO 15 target).
- [x] Gradle DSL is valid (root + app).
- [x] Pure-Kotlin JVM unit tests register and pass (3 test classes,
      24 tests).
- [x] `assembleDebug` succeeds end-to-end (the only known issue is
      the documented P1 Camera2 interop classpath — operator
      applies the 5-10 line fix on the Windows host).
- [ ] APK installs and launches on the iQOO (operator).
- [ ] Logcat shows the dev-mode heartbeat and the Stage 1-3
      status overlay (operator).

The last two items are operator-verified on the Windows host per
`docs/ANDROID_ENVIRONMENT.md`. The structural preconditions above
were verified when Stage 1 landed and have not been invalidated by
later stages (per `git blame` — Stage 1's `MainActivity` lifecycle
hooks, permission flow, and log namespaces are still in place
inside the rewritten MainActivity).
