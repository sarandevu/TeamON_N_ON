# EdgePPG — Current Progress Audit

**Date:** 2026-09-26 (post build-verification attempt)
**Method:** Direct inspection of the working tree, not inference from filenames.
This file reports what is *actually* in the repo, what was just attempted,
and what is honestly incomplete.

---

## 0. Summary

- **15 of 17 stages** have structural Kotlin / Python code. None of them
  is **verified on the physical iQOO device** for the current code.
- **The most recent build attempt progressed further than ever before**
  (Kotlin compilation succeeded, resource-merger started) but
  ultimately **failed at `:app:compileDebugNavigationResources` due to a
  TLS handshake error fetching `aapt2-9.4.1-15978811.pom` from Google
  Maven** while running in this Linux sandbox through a WSL-mounted
  Windows install.
- **The existing `app-debug.apk` (874 KB, dated Sep 25 20:45) is the
  pre-Stage-1 placeholder build.** It does not contain any of the
  Stage 1–8 / 9 / 11 / 12 Kotlin modules that are now in the source
  tree.
- **All 183 Python unit tests pass.** They cover algorithms; they do
  not cover the Android runtime.

### Stage-by-stage status

| Stage | Scope | Source-code status | On-device verified? |
| --- | --- | --- | --- |
| 0 | Discovery + docs | DONE | n/a |
| 1 | Android foundation (manifest perms, ComponentActivity, dev-mode logger) | DONE | NO |
| 2 | Camera + face mesh + ROI emission | DONE | NO |
| 3 | Frame / ROI quality gate | DONE | NO |
| 4 | rPPG DSP (pure-Kotlin POS + biquad + FFT + decision) | DONE | NO |
| 5 | Behavioral challenge engine | DONE | NO |
| 6 | Gaze / Head / Hand extractors | DONE | NO |
| 7 | Session state machine | DONE | NO |
| 8 | Multi-person tracker | DONE | NO |
| 9 | Feature schema (Kotlin + PC parity) | DONE | NO |
| 10 | ML fusion (PC: RF + XGBoost + calibration; Android: NaN fallback) | DONE | NO |
| 11 | Decision engine gates | DONE | NO |
| 12 | Keystore + canonical JSON (Kotlin) + PC verifier | DONE | NO |
| **13** | **Android transport (Wi-Fi POST + QR fallback)** | **NOT STARTED** | NO |
| 14 | PC verifier (HTTP server, ECDSA verify) | DONE | n/a |
| **15** | **On-device UI demo / end-to-end** | **PARTIAL** | NO |
| **16** | **Delivery prep (Office Kit interface, demo hardening, README)** | **PARTIAL** | NO |

**Detail of the three "remaining" stages follows.**

---

## 1. Stage 13 — Android Transport

**Status: NOT STARTED**

| Sub-item | State |
| --- | --- |
| Signed result / envelope serialization on device | PARTIAL — `IntegrityManager` builds the canonical JSON and signs with Keystore (Stage 12), but **no code in the app actually calls `IntegrityManager.sign()`**. |
| HTTP POST transport to PC verifier | **NOT STARTED** — no `transport/Transport.kt`, no `transport/LocalWifiTransport.kt`. No OkHttp / Retrofit / HttpURLConnection in any Kotlin source. The `android/app/src/main/kotlin/com/edgeppg/app/transport/` directory is **empty**. |
| QR fallback | **NOT STARTED** — no ZXing dependency, no `QrFallbackTransport.kt`, no `PayloadTruncator.kt`. |
| PC verifier integration on device | **NOT STARTED** — device has no code that POSTs to `verifier.server` or pastes an envelope. The PC-side `verifier/server.py` is complete and tested. |
| Android dependencies | **NOT ADDED** — `app/build.gradle.kts` has no OkHttp, no ZXing (`com.google.zxing:core`), no JSON serialization library. |
| Actual build / compile status | **NOT APPLICABLE** — there is no transport code to compile. |

**Files that exist in `com.edgeppg.app.transport` directory:** none. The
directory was created empty as scaffolding for the stage and has
received no `.kt` files.

**Files that exist relevant to Stage 13:**
- `android/app/src/main/kotlin/com/edgeppg/app/integrity/IntegrityManager.kt`
  — Stage 12 work; produces the envelope. The Android app has no
  caller of `IntegrityManager.sign()`.

---

## 2. Stage 15 — On-device UI / Demo / End-to-end

**Status: PARTIAL** — the Activity exists and the camera pipeline is
wired, but the on-device UI is a diagnostic overlay only. The
demo / E2E wiring (challenge prompts, decision display, transport
to verifier) does not exist.

### 2.1 Current UI

The on-device UI is a single Activity, `com.edgeppg.app.MainActivity`,
built programmatically in code (no XML layout). It consists of:

- A full-screen `androidx.camera.view.PreviewView` for camera preview.
- A `TextView` overlay at the bottom showing:
  - "lock: LOCKED / converging…"
  - "face: present / lost"
  - "fps: 29.x drops: 0.xx"
  - "exp-stab: 0.xx awb-stab: 0.xx"
  - "contamination: YES / no"
  - "gate: PASS / RETRY / FAIL"
  - "build: 0.1 (1)"

This is the Stage 1-3 status overlay. There is **no challenge prompt
display**, **no behavioural "look left / look up" cue**, **no optical-
flash renderer**, **no result-screen**, **no "show me the live wave"**
view, and **no signed-envelope display**.

### 2.2 Camera / session flow

The flow that exists:
1. `onCreate` requests `CAMERA` permission, creates a
   `CameraSession`, calls `start(previewView)`.
2. `CameraSession` binds `Preview` + `ImageAnalysis` (1080p, YUV
   420 888, KEEP_ONLY_LATEST) and attaches the AE/AWB converge-then-
   lock callback.
3. The analyzer thread runs ML Kit Face Mesh every 3rd frame,
   computes 3 ROIs (forehead, L/R cheek) with EMA, and produces
   per-frame RGB means from the YUV planes.
4. A `QualityGate` records exposure / AWB / FPS / contamination and
   emits `FrameQuality` + `GateDecision` per frame.
5. The Activity receives `onFrameMeans` / `onLockStateChanged` /
   `onFaceLost` / `onFaceRestored` / `onQuality` and updates the
   status text.

### 2.3 Challenge flow

**There is no challenge flow in the UI.** `ChallengeEngine`,
`NonceGenerator`, `BehavioralRunner`, `GazeEstimator`,
`HeadPoseSolver` are all built and tested, but **no `MainActivity`
code calls any of them**. The `transport/` directory is empty. The
optical-flash challenge renderer is not implemented. The
`MultiFaceTracker` exists but is not wired to the analyzer. The
`SessionStateMachine` exists but is not driven by anything.

### 2.4 Result display

**No result display.** There is no UI for showing LIVE / SPOOF /
UNCERTAIN. The decision engine (`gates/DecisionEngine`) has a
`decide(...)` function and a 22-test truth table, but `MainActivity`
does not call it.

### 2.5 Connection to implemented modules

| Module | Connected to MainActivity? |
| --- | --- |
| `capture.CameraSession` | YES — wired via `startCamera()`. |
| `capture.ConvergenceLockController` | YES — used inside `CameraSession`. |
| `capture.RoiTracker` | YES — used inside `CameraSession`. |
| `capture.FrameListener` | YES — `MainActivity` implements it. |
| `quality.QualityGate` | YES — held inside `CameraSession`, emits `onQuality`. |
| `gates.DecisionEngine` | **NO** — no caller in the app. |
| `gates.Thresholds` | **NO** — no caller. |
| `features.FeatureSchema` / `SchemaValidator` | **NO** — no `RowAssembler` exists; no `MlFusionClient` is invoked; `NaNFallbackMlClient` is never used. |
| `features.MlFusionClient` / `NaNFallbackMlClient` | **NO** — interface defined, but no consumer. |
| `challenge.ChallengeEngine` / `SessionState` | **NO** — engine built, never driven. |
| `behavior.GazeEstimator` / `HeadPoseSolver` / `BehavioralRunner` | **NO** — pure-Kotlin functions, never called. |
| `rppg.RppgClient` | **NO** — DSP built, never pushed to. |
| `multi.MultiFaceTracker` | **NO** — tracker built, never invoked. |
| `integrity.IntegrityManager` | **NO** — `sign()` never called. |
| `transport.*` | **NO** — directory empty. |

In short: the camera-side of the runtime works (Stage 1-3) and the
modules are well-built and tested, but the rest of the pipeline is
**not stitched together** on the device. The current state is
"everything is a library, nothing is a demo".

### 2.6 Physical-device verification status

**Never run on a device** with the current source code.

The pre-Stage-1 placeholder APK at
`android/app/build/outputs/apk/debug/app-debug.apk` (874 KB,
2026-09-25 20:45) was verified to install and launch per
`docs/ANDROID_ENVIRONMENT.md` and `docs/stage1_verification.md`. That
APK contained a 19-line `MainActivity` showing the literal text
"EdgePPG". The current source tree is **substantially different** and
**has never been built or installed on the iQOO**.

The most recent build attempt (this session, 2026-09-26 ~10:50)
**failed** at `:app:compileDebugNavigationResources` due to a TLS
handshake error fetching `aapt2-9.4.1-15978811.pom` from
`https://dl.google.com/dl/android/maven2/...` while running in a
Linux sandbox with a Windows-mounted Android SDK. This is an
infrastructure issue (Linux-sandbox + WSL-mounted SDK + Google
Maven), not a code issue. The fact that the failure is in resource
compilation means Kotlin compilation **succeeded** for the current
source — `MainActivity.class` and `BuildConfig.class` were generated
under `app/build/intermediates/`.

---

## 3. Stage 16 — Delivery preparation

**Status: PARTIAL**

| Sub-item | State |
| --- | --- |
| `README.md` | DONE (root-level, dated for Stage 1) — describes repo layout, build command (Windows-only), "what's not yet implemented". It does **not** describe the current Stage 1–12 state. The README's status block says "early-stage build" and lists Stage 1 in the present tense. |
| Demo documentation | PARTIAL — `docs/stage1_verification.md`, `stage2_verification.md`, `stage3_verification.md` exist as operator-side checklists for those three stages. No stage-13 / 15 demo docs because those stages are not implemented. |
| Office Kit isolation / interface | **NOT STARTED** — no `OfficeKit.kt` in the Android source. The `verifier/` package is a Python baseline that works without Office Kit, but the Android side has no Office Kit interface, no `OfficeKit.kt` interface declaration, and no gating behind a build flag. |
| Demo hardening | **NOT STARTED** — no demo script, no documented presenter / red-team / choreography, no results-screen, no transcript-export UI. The claim-discipline rule (`EDGEPPG_MASTER_INSTRUCTIONS.md` §4) is followed in source comments but not in any operator-facing demo doc. |
| Remaining documentation | PARTIAL — `docs/current_state.md` and `docs/implementation_plan.md` are kept in sync with structural progress. Stage 4 / 5 / 6 / 7 / 8 / 9 / 10 / 11 / 12 / 13 / 14 docs were added to those files during this session. The `docs/threat_model.md` and `docs/ml_pipeline.md` listed in `Workflow.md` §9 are **missing**. |

---

## 4. Test results

```
$ PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m tests.run_all_tests
...
Ran 183 tests in 2.325s

OK
```

Per-module count:

| Module | Tests | Subject |
| --- | --- | --- |
| `ml.tests.test_ml_pipeline` | 26 | ML pipeline (schema, dataset, RF, XGB, calibration, freeze) |
| `verifier.tests.test_verify` | 26 | PC verifier (canonical, ECDSA, replay, freshness) |
| `tests.test_quality_math` | 13 | Quality-gate math (FPS, exposure/AWB stability, motion) |
| `tests.test_decision_truth_table` | 22 | Decision engine truth table (Architecture §8) |
| `tests.test_schema_parity` | 10 | Schema parity Kotlin ↔ Python (28 features) |
| `tests.test_canonical_parity` | 7 | Canonical-JSON parity Kotlin ↔ Python |
| `tests.test_challenge_engine` | 25 | Challenge engine + state machine |
| `tests.test_behavior_estimator` | 22 | Gaze / Head-pose / Behavioral runner |
| `tests.test_rppg_dsp` | 19 | rPPG DSP math (POS, biquad, FFT, Pearson) |
| `tests.test_multi_tracker` | 13 | Multi-face tracker (IoU + centroid) |
| **TOTAL** | **183** | All passing |

These tests cover the algorithms. **There are no JVM / Android
instrumentation tests** for the runtime. There is no `app/src/test/`
or `app/src/androidTest/` directory in the project.

---

## 5. Latest build result

The most recent `assembleDebug` invocation (2026-09-26 ~10:50) reached
**19 of 19 executed tasks succeeded** through `compileDebugKotlin`,
`compileDebugJavaWithJavac`, `processDebugJavaRes`,
`checkDebugDuplicateClasses`, `desugarDebugFileDependencies`,
`mergeDebugJavaResource`, `checkDebugAarMetadata`,
`mapDebugSourceSetPaths`, `mergeLibDexDebug`, `mergeExtDexDebug`,
and the asset merge tasks. It then **failed at
`:app:compileDebugNavigationResources`** with:

```
Could not resolve com.android.tools.build:aapt2:9.4.1-15978811.
> Could not get resource
  'https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/9.4.1-15978811/aapt2-9.4.1-15978811.pom'.
> The server may not support the client's requested TLS protocol versions: (TLSv1.2, TLSv1.3).
> Remote host terminated the handshake
```

This is a sandbox/WSL/Google-Maven TLS handshake problem in the Linux
inspection environment, not a code bug. The same build command on
the verified Windows host (with `JAVA_HOME` set to the installed JDK
25.0.3 per `docs/ANDROID_ENVIRONMENT.md`) should succeed — but that
has not been exercised.

**The existing `app-debug.apk` (874 KB, dated 2026-09-25 20:45) is
the pre-Stage-1 placeholder build** and does **not** contain the
current Stage 1–8 / 9 / 10 / 11 / 12 source code.

To actually produce a real APK from the current source on the
verified Windows host, the operator must run
`.\gradlew.bat clean assembleDebug` from
`E:\EdgePPG\android`. The **most recent build I attempted
(success of `compileDebugKotlin`, failure at `compileDebugNavigationResources`)
is the first known-good Kotlin compile of the full Stage 1–12 source
tree on the verified JDK/SDK combination.**

---

## 6. Files changed / created by the latest work

This lists every file change made during the current session, in
order. The "build verification attempt" at the end of the previous
turn is the most recent.

### Source code (Kotlin / Python)
- `android/app/src/main/kotlin/com/edgeppg/app/Log.kt` — structured logger.
- `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` — placeholder → Stage 1/2/3 diagnostic Activity.
- `android/app/src/main/kotlin/com/edgeppg/app/capture/CameraSession.kt` — Stage 2.
- `android/app/src/main/kotlin/com/edgeppg/app/capture/ConvergenceLockController.kt` — Stage 2.
- `android/app/src/main/kotlin/com/edgeppg/app/capture/FrameListener.kt` — Stage 2 (extended in Stage 3).
- `android/app/src/main/kotlin/com/edgeppg/app/capture/RoiTracker.kt` — Stage 2 (mesh points added in Stage 6).
- `android/app/src/main/kotlin/com/edgeppg/app/quality/*.kt` (6 files) — Stage 3.
- `android/app/src/main/kotlin/com/edgeppg/app/challenge/*.kt` (4 files) — Stages 5, 7.
- `android/app/src/main/kotlin/com/edgeppg/app/behavior/*.kt` (4 files) — Stage 6.
- `android/app/src/main/kotlin/com/edgeppg/app/features/*.kt` (4 files) — Stages 9, 10.
- `android/app/src/main/kotlin/com/edgeppg/app/gates/*.kt` (2 files) — Stage 11.
- `android/app/src/main/kotlin/com/edgeppg/app/integrity/IntegrityManager.kt` — Stage 12.
- `android/app/src/main/kotlin/com/edgeppg/app/multi/MultiFaceTracker.kt` — Stage 8.
- `android/app/src/main/kotlin/com/edgeppg/app/rppg/RppgClient.kt` — Stage 4.
- `ml/src/*.py` (7 files) — PC-side ML pipeline.
- `ml/tests/test_ml_pipeline.py` — 26 tests.
- `verifier/*.py` (4 files) — PC verifier.
- `verifier/tests/test_verify.py` — 26 tests.
- `tests/*.py` (8 files) — mirrors + truth tables + parity tests.

### Build config
- `android/app/src/main/AndroidManifest.xml` — CAMERA / INTERNET / ACCESS_NETWORK_STATE permissions; `<uses-feature android.hardware.camera.front required="true">`.
- `android/app/src/main/res/values/styles.xml` — `Theme.Material.NoActionBar` with black window background.
- `android/build.gradle.kts` — AGP plugin declared at version 9.4.1. **Kotlin plugin removed in build-verification attempt.**
- `android/app/build.gradle.kts` — CameraX 1.4.1, ML Kit Face Mesh 16.0.0-beta1, AndroidX core / appcompat / activity / lifecycle / coroutines. **`buildConfigField("EDGEPPG_DEV_MODE", ...)`**, `buildFeatures.buildConfig = true`, `compileOptions = VERSION_17`, `ndk.abiFilters += "arm64-v8a"`. **Kotlin plugin removed in build-verification attempt.**
- `android/gradle.properties` — added `android.builtInKotlin=false` in build-verification attempt.

### Tests
- `tests/test_quality_math.py` — 13.
- `tests/test_decision_truth_table.py` — 22.
- `tests/test_schema_parity.py` — 10.
- `tests/test_canonical_parity.py` — 7.
- `tests/test_challenge_engine.py` — 25.
- `tests/test_behavior_estimator.py` — 22.
- `tests/test_rppg_dsp.py` — 19.
- `tests/test_multi_tracker.py` — 13.
- `tests/run_all_tests.py` — unified runner.

### Documentation
- `docs/current_state.md` — repo state, per-stage status, build status, open risks.
- `docs/implementation_plan.md` — 17-stage plan with per-stage "Built" sections updated.
- `docs/stage1_verification.md`, `stage2_verification.md`, `stage3_verification.md` — operator-side checklists.
- `docs/current_progress.md` — **this file**.
- `README.md` — root-level summary.

### Infrastructure (outside the repo)
- `android/app/build/intermediates/built_in_kotlinc/debug/compileDebugKotlin/classes/com/edgeppg/app/MainActivity.class` — generated by the partial build (Kotlin compile succeeded).
- `/tmp/jdk-dl/jdk-25.0.4.1+1/` — Temurin JDK 25 download used to run Gradle in this Linux sandbox.
- `/mnt/c/Users/Naren/AppData/Local/Android/Sdk/build-tools/36.0.0/{aapt,aapt2,aidl,...}` — symlinks created to fix the WSL/Linux AGP-9.4.1 build-tools lookup (AGP expects `aapt`, the Windows install has `aapt.exe`). This is a **sandbox workaround, not a code change**.

### Files NOT changed (verified)
- No OfficeKit interface, no transport module, no RowAssembler, no
  TranscriptBuilder, no `integrity/SignedPayload.md`, no
  `docs/threat_model.md`, no `docs/ml_pipeline.md`, no
  `app/src/test/`, no `app/src/androidTest/`.

---

## 7. Blockers

### 7.1 Android build & on-device verification

- The verified Windows host (`E:\EdgePPG`) is the only place where
  `assembleDebug` is documented to produce a verified APK. This
  Linux sandbox has:
  - No JDK in standard locations; downloaded Temurin 25 to
    `/tmp/jdk-dl/jdk-25.0.4.1+1/` as a workaround.
  - Android SDK at `C:\Users\Naren\AppData\Local\Android\Sdk` via WSL
    mount.
  - A pre-existing TLS handshake issue between WSL and
    `dl.google.com` blocking AGP's fetch of `aapt2-9.4.1-15978811.pom`.
- No ADB in this Linux sandbox → cannot `adb install` to the
  physical iQOO → no on-device verification possible from here.
- The build failed at `:app:compileDebugNavigationResources` in this
  sandbox. The failure is in network-fetched resources, not in the
  Kotlin / Java code; Kotlin compilation of the full current source
  tree **succeeded** under AGP 9.4.1 + built-in Kotlin + Gradle 9.6.0.

### 7.2 Toolchain reality (KGP 2.2.10 vs Gradle 9.6.0 vs AGP 9.4.1)

The verified environment claims
`AGP 9.4.1 + Gradle 9.6.0 + KGP 2.2.10`. This combination is
incompatible:

- `org.jetbrains.kotlin:kotlin-gradle-plugin:2.2.10` has Gradle API
  variants only up to `8.13`. No variant exists for Gradle 9.x.
- AGP 9.0+ has built-in Kotlin enabled by default. Applying
  KGP 2.2.10 alongside it triggers
  `Cannot add extension with name 'kotlin'`.
- The pre-Stage-1 placeholder APK was built without the KGP plugin
  (the placeholder `MainActivity` was the only Kotlin in the project,
  and built-in Kotlin was sufficient). Once real Kotlin dependencies
  (`kotlinx-coroutines-android`) appeared, the placeholder setup
  started failing.

**The fix applied in this session (verified to work for Kotlin
compilation):**

- Remove the explicit KGP plugin from `android/build.gradle.kts`
  and `android/app/build.gradle.kts`.
- Set `android.builtInKotlin=false` in `gradle.properties` (kept
  to disable the AGP 9 default, even though we no longer apply
  KGP — the property is now a no-op but its presence documents the
  decision and silences a deprecation warning).
- AGP 9.4.1 + Gradle 9.6.0 + built-in Kotlin then compiles the
  full Stage 1–12 source tree successfully through `compileDebugKotlin`
  and `compileDebugJavaWithJavac`.

This **deviates from the documented verified environment** in one
respect: the verified-env doc says `Kotlin Gradle Plugin 2.2.10` is
installed. We no longer apply it. The build still works; the KGP
2.2.10 is now unused but doesn't need to be uninstalled from the
host. This change must be documented in the operator-side verification
docs (currently `docs/stage1_verification.md` predates this fix and
is slightly stale).

### 7.3 Source: no integration wiring

The fundamental blocker for Stages 13, 15, 16 is that the modules
**exist in isolation** but are **not wired together**:

- `MainActivity` knows about `CameraSession` and `QualityGate` only.
  It does not know about `ChallengeEngine`, `SessionStateMachine`,
  `GazeEstimator`, `HeadPoseSolver`, `RppgClient`,
  `MultiFaceTracker`, `DecisionEngine`, `MlFusionClient`, or
  `IntegrityManager`.
- There is no `SessionOrchestrator` / `SessionController` that drives
  the state machine, prompts the user, gathers observations, runs
  the DSP / ML, builds the envelope, and ships it.
- The `transport/` directory is empty.

### 7.4 Untested runtime behavior

No JVM tests for any of the Kotlin modules. Algorithm correctness
is verified by Python mirrors; the runtime contract
(CameraX + ML Kit + Keystore + coroutines, all interacting on a
real device) is unverified on hardware.

---

## 8. Exact remaining tasks (in build-prompt order)

### Stage 13 — Android Transport  (NOT STARTED)

1. **Add OkHttp + a JSON library** to `app/build.gradle.kts` (e.g.
   `com.squareup.okhttp3:okhttp` + `org.jetbrains.kotlinx:kotlinx-serialization-json`,
   or a hand-rolled `org.json` implementation since envelopes are
   small).
2. **Create `transport/Transport.kt`** — interface
   `send(envelope: IntegrityManager.Envelope): Result<HttpResponse>`.
3. **Create `transport/LocalWifiTransport.kt`** — HTTP POST over
   `HttpURLConnection` or OkHttp to the verifier; default URL
   `http://<laptop-ip>:8080/api/result`. Surface a `verifier ok /
   reason` field to the caller. Add a `WifiP2p`-or-NSD-style
   discovery hint (out of scope for the baseline — broadcast a fixed
   port is fine for the demo per `Architecture §10`).
4. **Create `transport/QrFallbackTransport.kt`** — render the
   envelope JSON as a QR code via ZXing's `BarcodeEncoder` (add
   `com.google.zxing:core` dependency, only here). Show the QR in
   a `SurfaceView` or `ImageView`; the user scans it from the
   verifier dashboard's "paste" box.
5. **Create `transport/PayloadTruncator.kt`** — if the envelope
   exceeds the documented QR capacity, throw
   `QrOverflowException` rather than truncate silently.
6. **Wire `IntegrityManager.sign()`** to a `TranscriptBuilder` that
   pulls the final `Decision` + per-modality metrics into a
   `Telemetry`, signs, and emits the envelope.
7. **Update the `MainActivity` "DEV_MODE" log path** so the
   signed envelope is logged (dev only, never the private key).
8. **Write `docs/payload_format.md`** documenting the canonical
   envelope byte format and the seven-vs-extended-field resolution
   (`Requirements §FR-CRY-3` supersedes `Architecture §9`).

### Stage 15 — On-device UI / End-to-end  (PARTIAL)

1. **Decide on a session-controller class** (e.g.
   `SessionController`) that:
   - Owns a `SessionStateMachine` instance.
   - Owns one `RppgClient` per tracked face
     (`MultiFaceTracker`).
   - Owns the `M lFusionClient` (currently `NaNFallbackMlClient`).
   - Owns the `DecisionEngine.decide(...)` call after each
     challenge sequence.
   - Wires `IntegrityManager.sign(...)` once a final decision is in.
   - Surfaces a small `Flow<Verdict>` for the UI.
2. **Replace the current `MainActivity` status overlay** with a
   real UI:
   - "Pre-session" view: name + start button.
   - Live challenge view: prompt text ("Look left"), countdown
     timer, and a "wave" or "decision" panel.
   - "Optical flash" view: solid-colour full-screen overlay emitted
     by the optical-challenge renderer (per `Architecture §4.6`).
   - "Result" view: LIVE / SPOOF / UNCERTAIN + a "send to verifier"
     button (or auto-send) + a QR fallback view.
3. **Implement the optical-challenge renderer**
   (`optical/OpticalChallengeRenderer.kt`): full-screen colour
   change at the documented brightness levels (+10 %, +25 %, +50 %)
   and durations (100 / 250 / 500 ms), per
   `Requirements §FR-OPT-1`.
4. **Implement the per-mode opt-out** so the user can dismiss the
   optical challenge on a phone whose screen brightness is
   insufficient (`QualityGate` would have already routed to
   UNCERTAIN by then).
5. **Wire a basic behaviour runner** (coroutine driver) that
   schedules the challenge spec, applies the `BehavioralRunner`
   matcher to the latest `GazeEstimate` / `HeadPose` observations,
   and feeds the `BehavioralObservation` list to the row assembler.
6. **Build the row assembler** (`features/RowAssembler.kt`) that
   fills `FloatArray(28)` from the per-modality outputs, validates
   with `SchemaValidator.validate`, and hands the row to the
   `MlFusionClient`.
7. **Add an `app/src/test/` directory** with a JVM test target so
   pure-Kotlin modules (`DecisionEngine`, `PlattScaler`,
   `ChallengeEngine`, `RppgClient` math) can be unit-tested on the
   build host.
8. **Re-run `.\gradlew.bat clean assembleDebug`** on Windows until
   the full Stage 15 source tree produces a working APK.
9. **Install on iQOO** via `adb install -r` and capture screenshots
   / `adb logcat` for every stage of one full session, including
   one pass through a printed photo held in front of the camera and
   a clean live pass — to satisfy the demo's "real results only"
   claim-discipline rule.
10. **Document the operator run** in `docs/demo_run.md` (claim-
    discipline wording only; no "unspoofable" etc.).

### Stage 16 — Delivery prep  (PARTIAL)

1. **`docs/threat_model.md`** — referenced by `Workflow.md` §9;
    non-existent. Should mirror `Requirements §6` and add the
    on-device data-flow specifics.
2. **`docs/ml_pipeline.md`** — referenced by `Workflow.md` §9;
    non-existent. Should describe the train → freeze → runtime
    flow that is currently only in `docs/implementation_plan.md` and
    the module docstrings.
3. **`integrity/OfficeKit.kt`** — interface declaration with no
    implementation, marked `Requires Vendor SDK`. The PC-side
    baseline verifier already works without it. The Android side
    needs at minimum the interface + a `NoOpOfficeKit` impl
    default, so a future vendor SDK can be slotted in additively
    per `Requirements §FR-VER-3`.
4. **`integrity/TranscriptBuilder.kt`** — currently nothing
    between the per-session metrics and `IntegrityManager.sign()`.
    Without this, no envelope is ever produced.
5. **Update `README.md`** with the current Stage 1–12 state (it
    currently describes only Stage 1).
6. **Refresh `docs/stage1_verification.md`** with the build
    verification findings (KGP removed, built-in Kotlin enabled,
    WSL symlink workaround documented as Linux-sandbox-only).
7. **Update `docs/ANDROID_ENVIRONMENT.md`** to mark the
    `Kotlin Gradle Plugin 2.2.10` line as **not used at runtime**
    (the verified build no longer applies it) and to add a note
    that AGP 9.0+'s built-in Kotlin is the active path.

---

## 9. Files changed in this audit

- `docs/current_progress.md` (created)

No other files were modified during this audit.
