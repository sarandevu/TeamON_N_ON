# EdgePPG — README

> **Status (2026-09-26, post Stage 15):** structural implementation of
> Stages 1-15 is complete on the source side. PC-side tests pass
> (274/274 — the implementation_plan.md details the new
> integration tests). The Android app source compiles structurally
> but `assembleDebug` against AGP 9.4.1's built-in-Kotlin path
> has a known P1 Camera2 interop classpath issue documented in
> `docs/implementation_plan.md` Stage 13 Task 8 / Stage 15 Task 7.
> Device verification on the iQOO is **pending final integration**
> (operator's next step on the verified Windows host per
> `docs/ANDROID_ENVIRONMENT.md`).

This README does **not** claim the system is unspoofable,
deepfake-proof, medical-grade, or guaranteed to detect attacks. All
such claims are forbidden by the claim-discipline rule
(`EDGEPPG_MASTER_INSTRUCTIONS.md` §4).

---

## What this repo currently contains

| Path | State |
| --- | --- |
| `android/` | AGP 9.4.1 + Gradle 9.6.0 + built-in Kotlin (KGP 2.2.10 removed; KGP has no `gradle9` variant). All Stage 1-15 source modules present. Pure-Kotlin JVM tests pass; full APK build is pending the documented P1 Camera2 interop fix. |
| `android/app/src/main/kotlin/com/edgeppg/app/quality/` | Stage 3: `FrameQuality`, `FrameMetrics`, `ExposureStability`, `AwbStability`, `MotionContamination`, `QualityGate`. |
| `android/app/src/main/kotlin/com/edgeppg/app/capture/` | Stage 2: `CameraSession` (CameraX + AE/AWB lock), `ConvergenceLockController`, `RoiTracker` (face mesh + YUV→RGB), `FrameListener`. |
| `android/app/src/main/kotlin/com/edgeppg/app/rppg/` | Stage 4: pure-Kotlin rPPG DSP — POS, biquad bandpass, radix-2 FFT, Pearson ROI correlation. NDK port gated on profiling. |
| `android/app/src/main/kotlin/com/edgeppg/app/challenge/` | Stage 5 + 7: `ChallengeEngine` (per-seed randomised sequence), `ChallengeSpec` (Gaze / Head / Hand / RemainStill / OpticalFlash), `NonceGenerator`, `SessionStateMachine` (7 states, configurable retries). |
| `android/app/src/main/kotlin/com/edgeppg/app/behavior/` | Stage 6: `GazeEstimator` (iris-geometry), `HeadPoseSolver` (cheek-mouth-forehead asymmetry), `BehavioralRunner` (pure matcher), `BehaviourRunner` (coroutine driver), `MeshLandmarks`. |
| `android/app/src/main/kotlin/com/edgeppg/app/multi/` | Stage 8: `MultiFaceTracker` (IoU + centroid hysteresis, up to 2 participants). |
| `android/app/src/main/kotlin/com/edgeppg/app/features/` | Stage 9 + 10: `FeatureSchema` + `SchemaValidator` (28 features, byte-exact parity with PC), `MlFusionClient` interface, `NaNFallbackMlClient` (placeholder, returns NaN), `RowAssembler` (session → row). |
| `android/app/src/main/kotlin/com/edgeppg/app/gates/` | Stage 11: `DecisionEngine` (Architecture §8 verbatim), `Thresholds` (placeholder 0.80/0.20). |
| `android/app/src/main/kotlin/com/edgeppg/app/integrity/` | Stage 12: `IntegrityManager` (AndroidKeyStore ECDSA P-256 + canonical JSON). Stage 13 + 16: `TranscriptBuilder` (session → telemetry + sign), `OfficeKit` interface + `NoOpOfficeKit` (vendor seam; baseline flow unchanged). |
| `android/app/src/main/kotlin/com/edgeppg/app/transport/` | Stage 13: `Transport` interface, `LocalWifiTransport` (OkHttp 4.12.0), `QrFallbackTransport` (ZXing 3.5.4), `PayloadTruncator` (`QrOverflowException` at 1.5 KB cap). |
| `android/app/src/main/kotlin/com/edgeppg/app/optical/` | Stage 15: `OpticalFlashOverlay` (full-screen colour flash, FR-OPT-1). |
| `android/app/src/main/kotlin/com/edgeppg/app/session/` | Stage 15: `SessionController` — orchestrator that wires everything together. |
| `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | Stage 15: state-driven UI (permission → camera → quality → challenges → motion/blink → result). |
| `ml/src/` | PC-side ML pipeline. `feature_schema.py` (28-feature contract), `dataset.py` (GroupShuffleSplit on `subject_id`), `train_rf.py` / `train_xgb.py` (synthetic-fixture only), `calibration.py` (Platt scaling + thresholds), `evaluate.py` (refuses to fabricate), `freeze_model.py` (refuses without held-out metrics). |
| `verifier/` | Python baseline PC verifier. ECDSA P-256 / SHA-256 over the canonical envelope (`verifier.canonical.canonical_payload` mirrors the Kotlin byte-exact), 5-minute freshness window, replay-nonce LRU, offline receipt writer, stdlib HTTP server with a minimal dashboard. |
| `tests/` | Python unit tests (no pytest dependency): 274 tests across ML pipeline, PC verifier, quality math, decision truth-table, schema / canonical parity, challenge engine, behaviour estimator, rPPG DSP math, multi-tracker, transport contract (including the new TranscriptBuilder ↔ verifier round-trip), RowAssembler, JVM test target. |
| `models/` | `edgeppg_rf_v1.{joblib,manifest.json}` and `edgeppg_xgb_v1.{joblib,manifest.json}` — synthetic-fixture artifacts with `status: UNTRAINED_NO_REAL_DATA`. No `edgeppg_frozen.*` yet (freezing requires real held-out metrics, which do not exist). |
| `docs/` | Engineering docs (`Requirements.md`, `TechStack.md`, `Architecture.md`, `Workflow.md`, `EDGEPPG_MASTER_INSTRUCTIONS.md`, `ANDROID_ENVIRONMENT.md`) + state (`current_state.md`, `current_progress.md`, `implementation_plan.md`) + stage verification (`stage1_verification.md`, `stage2_verification.md`, `stage3_verification.md`) + **new** protocol-level docs (`payload_format.md`, `threat_model.md`, `ml_pipeline.md`, `demo_run.md`). |

---

## How to run the PC-side tests

```powershell
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m pip install cryptography   # one-time
.\.venv\Scripts\python.exe -m tests.run_all_tests
```

Expected: `Ran 274 tests in N seconds — OK`.

## How to start the PC verifier

```powershell
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m verifier.server --port 8080
# Open http://localhost:8080/ in a browser.
# Until pubkey.b64 is provisioned, every signature verifies as bad-pubkey.
```

The phone and the laptop must be on the same local Wi-Fi network.
On a real iQOO, edit the `LocalWifiTransport()` URL in
`MainActivity.kt` to the laptop's LAN IP, then rebuild. For QR
fallback, the phone shows a QR code; the user scans / pastes the
JSON into the verifier dashboard.

## How to regenerate the synthetic-fixture artifacts (pipeline self-test)

```powershell
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m ml.src.train_rf
.\.venv\Scripts\python.exe -m ml.src.train_xgb
.\.venv\Scripts\python.exe -m ml.src.freeze_model
# freeze_model refuses to run without held-out metrics.
```

These produce `models/edgeppg_rf_v1.*` and `models/edgeppg_xgb_v1.*`
with `status: UNTRAINED_NO_REAL_DATA`. They are **not** a substitute
for real validation data; the manifests say so.

---

## How to build the APK and run on the iQOO

The full Stage 15 build is the operator's next step on the verified
Windows host per `docs/ANDROID_ENVIRONMENT.md`:

```powershell
cd E:\EdgePPG\android
.\gradlew.bat clean assembleDebug
# If `compileDebugKotlin` fails with `Unresolved reference: addSessionCaptureCallback`
# (Camera2 interop classpath under AGP 9.4.1's built-in Kotlin), the fix
# is a 5-10 line `androidComponents { onVariants { ... } }` block in
# `app/build.gradle.kts`. Documented in docs/implementation_plan.md
# Stage 13 Task 8 / Stage 15 Task 7.

adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
adb logcat -s EdgePPG/*:V
```

The complete operator procedure — pre-flight, the three demo
scenarios (genuine, printed photo, replay), failure modes, and
the claim-discipline enforcement — is in `docs/demo_run.md`. That
doc has an **Observed Results** template the operator fills in after
the actual device run.

---

## Implementation status (high level)

| Stage | Description | Source state | Verified? |
| --- | --- | --- | --- |
| 1 | Android foundation | DONE | operator |
| 2 | Camera + face mesh + ROI | DONE | operator |
| 3 | Quality gate | DONE | operator |
| 4 | rPPG DSP (pure-Kotlin baseline) | DONE | JVM test (math) |
| 5 | Behavioural challenge engine | DONE | JVM test |
| 6 | Gaze / head / hand estimators | DONE | JVM test |
| 7 | Session state machine | DONE | JVM test |
| 8 | Multi-person tracker | DONE | JVM test |
| 9 | Feature schema + validator | DONE | source + JVM test |
| 10 | ML fusion (PC: RF+XGB+freeze; Android: NaN fallback) | DONE | source + JVM test |
| 11 | Decision gates | DONE | source test (truth table) |
| 12 | Keystore + canonical JSON | DONE | source test (round-trip) |
| 13 | Android transport (Wi-Fi + QR) | DONE | source test (contract) |
| 14 | PC verifier | DONE | source test (round-trip) |
| 15 | On-device UI / end-to-end | source DONE | **PENDING iQOO run** |
| 16 | Delivery prep (Office Kit, docs, demo_run) | source DONE | operator |

JVM unit tests: 3 test classes (`ChallengeEngineTest`, `NonceGeneratorTest`,
`SessionStateTest`) in `app/src/test/kotlin/`. The test target is
registered; `testImplementation("junit:junit:4.13.2")` is in
`app/build.gradle.kts`. The actual `:app:testDebugUnitTest` execution
is blocked on the same P1 Camera2 interop classpath issue that
blocks `assembleDebug`.

---

## What's NOT yet implemented (open work)

- **Trained ML model.** `NaNFallbackMlClient` is the runtime. The
  decision engine correctly routes to `UNCERTAIN` when `P(LIVE)` is
  NaN; the demo will therefore show `UNCERTAIN` for both genuine
  and attacked sessions until a real model is trained.
- **Real validation data** (`Requirements §PR-DAT-1`). The training
  pipeline runs on the synthetic fixture (8 subjects, 6 sessions
  each). A real dataset is required for `freeze_model.freeze_for_runtime`
  to produce `edgeppg_frozen.*` and for the `evaluate.py` attack
  metrics (`FAR`, `FRR`, attack-specific) to mean anything.
- **Optical-flash correlation on the verifier side** (`Requirements
  §FR-OPT-2` / `§FR-OPT-3`, marked `[Requires Device Test]`). The
  device projects the flash; the camera records the reflection. The
  end-to-end correlation between expected and observed reflectance
  is `[Requires Device Test]` and is not implemented in the
  current build.
- **Multi-person desync detection** (`Requirements §FR-MP-3`).
  `MultiFaceTracker` keeps stable IDs; the per-participant
  cross-correlation is the row assembler's `cross_person_*` fields,
  which are NaN at runtime today (single-participant scope).
- **iQOO physical-device verification** of the above. The current
  source builds and the Python test suite passes; the actual
  install / launch / logcat capture is the operator's next step on
  the Windows host per `docs/ANDROID_ENVIRONMENT.md`.

The full stage-by-stage plan lives in `docs/implementation_plan.md`;
the discovered repo state lives in `docs/current_state.md`.

---

## Claim discipline

This codebase does **not** claim to:

- prevent spoofing,
- guarantee liveness,
- be deepfake-proof,
- be medical-grade,
- guarantee physical presence,
- be unspoofable,
- train a model that exists (no real validation set).

It is a research / engineering scaffold implementing a documented
protocol composition whose effectiveness must be validated empirically
against specified attack datasets. See
`EDGEPPG_MASTER_INSTRUCTIONS.md` §4 for the full invariant list.
