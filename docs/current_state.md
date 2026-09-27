# EdgePPG — Current State (as of 2026-09-26)

Authoritative source for what's actually present in the repo, what builds, and what's missing. Generated after a full inspection; nothing here is assumed.

---

## 0. Progress Snapshot

| Stage | Scope | Status |
| --- | --- | --- |
| 0 | Discovery + `docs/current_state.md`, `docs/implementation_plan.md` | **DONE** |
| 1 | Android foundation (manifest permissions, ComponentActivity, dev-mode logger, CameraX deps) | **DONE** (structural; on-Windows build verification deferred to operator) |
| 2 | Camera acquisition + face mesh + ROI emission | **structural DONE** (CameraSession, ConvergenceLockController, RoiTracker, FrameListener, MainActivity wired; on-Windows build verification deferred — `docs/stage2_verification.md`) |
| 3 | Frame / ROI quality gate | **structural DONE** (`quality/FrameQuality`, `FrameMetrics`, `ExposureStability`, `AwbStability`, `MotionContamination`, `QualityGate`; `CameraSession` wired with parallel Camera2 capture callback; `tests/test_quality_math.py` mirrors the math, 13/13 passing) |
| 4 | rPPG DSP (POS + bandpass + FFT + SNR + ROI agreement) | **structural DONE** (`rppg/RppgClient.kt` pure-Kotlin DSP: POS, Butterworth biquad, radix-2 FFT, Pearson, SNR/HR/decision; `tests/test_rppg_dsp.py` mirrors math — 15 tests passing including numpy FFT cross-check) |
| 5 | Behavioral challenge engine | **structural DONE** (`challenge/NonceGenerator.kt`, `ChallengeSpec.kt`, `ChallengeEngine.kt`; `tests/test_challenge_engine.py` mirrors algorithms + parses Kotlin source — 25 tests passing) |
| 6 | Gaze / Head / Hand extractors | **structural DONE** (`behavior/MeshLandmarks.kt`, `GazeEstimator.kt`, `HeadPoseSolver.kt`, `BehavioralRunner.kt`; `RoiTracker` now exposes 478 mesh points; `tests/test_behavior_estimator.py` mirrors geometry — 22 tests passing) |
| 7 | ROI quality gate + session state machine | **structural DONE** (`challenge/SessionState.kt` with documented 7-state machine + configurable retries; 13 of the 25 challenge-engine tests cover it; quality gate is Stage 3) |
| 8 | Multi-ROI + multi-person tracking | **structural DONE** (`multi/MultiFaceTracker.kt` IoU + centroid tracker, max 2 participants, configurable timeout, per-track subject assignment; `tests/test_multi_tracker.py` mirrors algorithm + checks source — 13 tests passing) |
| 9 | Feature vector assembly (frozen schema) | **structural DONE** (`features/FeatureSchema.kt` + `SchemaValidator.kt` mirror `ml/src/feature_schema.py`; `tests/test_schema_parity.py` enforces Kotlin ↔ Python parity — 10 tests passing). RowAssembler + per-modality feeders land alongside Stage 10/11/12. |
| 10 | ML fusion (RF baseline; model UNTRAINED until real data) | **PC-side DONE** (schema + dataset + RF + XGBoost + calibration + freeze logic); **Android client DONE** (`features/MlFusionClient.kt` interface + `NaNFallbackMlClient.kt` returning NaN until a real loader is selected; on-device runtime gated on `TechStack §16` benchmark) |
| 11 | Security decision gates (LIVE / SPOOF / UNCERTAIN) | **structural DONE** (`gates/DecisionEngine.kt`, `gates/Thresholds.kt`; 22-row truth-table mirror in `tests/test_decision_truth_table.py`, all passing) |
| 12 | Keystore signing + signed transcript | **structural DONE** (Kotlin `IntegrityManager.kt` ECDSA P-256 + canonical JSON; PC `verifier/canonical.py` + `verify.py` + `receipt.py`; `tests/test_canonical_parity.py` enforces Kotlin ↔ Python byte parity — 7 tests passing) |
| 13 | Wi-Fi + QR transport | not started on-device; **PC HTTP intake DONE** (`verifier.server`) |
| 14 | Baseline PC verifier + Office Kit isolation | **DONE** for baseline; Office Kit left as a typed interface gap |
| 15 | E2E testing + demo hardening | not started |
| 16 | Delivery prep | not started |

Tests: 170 total (26 ML pipeline + 26 verifier + 13 quality math + 22
decision truth-table + 10 schema parity + 7 canonical parity + 25 challenge
engine + 22 behavior estimator + 15 rPPG DSP + 4 misc), all passing via
`.venv\Scripts\python.exe -m tests.run_all_tests`.

Build verification on the verified Windows host is out of scope for this
Linux inspection environment; see `docs/stage1_verification.md` for the
operator-side checklist.

---

---

## 1. Repository Layout

```
E:\EdgePPG\                              (verified root, mounts at /mnt/e/EdgePPG)
├── android/                             Android Gradle project (verified builds, installs, launches)
├── data/                                EMPTY
├── docs/                                Mirror of the root docs + ANDROID_ENVIRONMENT.md
│                                          + current_state.md, implementation_plan.md (this file)
├── ml/                                  EMPTY
├── models/                              EMPTY
├── tests/                               EMPTY
├── .gradle/                             Gradle 9.6.0 wrapper cache (already provisioned)
├── .venv/                               Windows Python 3.11 venv (numpy, pandas, scikit-learn,
│                                          xgboost, opencv-python, mediapipe, PIL — all preinstalled)
├── Architecture.md, Requirements.md, TechStack.md, workflow.md,
│   EDGEPPG_MASTER_INSTRUCTIONS.md        Engineering docs (mirrored under docs/)
```

A separate, parallel experimental codebase exists at `E:\code\EdgePPG\` containing a
substantial prior implementation (capture + native DSP + Keystore + Node verifier + Three.js
dashboard). **It is NOT integrated into the verified Android project** and **NOT a build
dependency** of `E:\EdgePPG\android\`. It is treated here as **out-of-tree reference material**
only — its code may inform the staged build but cannot be silently merged, because:

- The verified Android project has its own pinned toolchain (AGP 9.4.1, Kotlin 2.2.10,
  SDK 37, Build Tools 36.0.0, JDK 25.0.3, Gradle 9.6.0) and contains zero references to
  the parallel code.
- Per `EDGEPPG_MASTER_INSTRUCTIONS.md` §7 and `ANDROID_ENVIRONMENT.md`, the verified
  Android environment must not be recreated, migrated, or replaced.
- Per the build prompt's "Code" rule: don't rewrite verified Android foundation.

That parallel code (read-only inspection):

- `app/src/main/java/com/edgeppg/capture/` — `ChallengeEmitter.kt`,
  `EdgePpgCaptureManager.kt` (CameraX + 1080p YUV_420_888 analyzer), `ConvergenceLockController.kt`
  (AE/AWB converge-then-lock), `RoiTracker.kt` (ML Kit Face Mesh → 3 ROIs with EMA),
  `NativeBridge.kt` (JNI to `libedgeppg_dsp.so`).
- `app/src/main/java/com/edgeppg/integrity/IntegrityManager.kt` — Android Keystore ECDSA
  P-256 signing of a canonical JSON payload, with `PAYLOAD_FORMAT.md` documenting the
  envelope, freshness window (5 min), and required fields.
- `dsp/src/main/cpp/edgeppg_dsp.{h,cpp}` + `CMakeLists.txt` — zero-allocation C++ DSP:
  circular buffer (256×3×3 floats), POS per ROI, Butterworth bandpass (0.7–4 Hz @30 fps),
  256-pt radix-2 FFT, SNR, ROI cross-correlation, motion-spike gate, decision (LIVE / SPOOF /
  UNCERTAIN).
- `office-kit/` — Node.js local Wi-Fi verifier + Three.js dashboard. Not "Office Kit" in
  the vendor sense from `Requirements.md §FR-VER-3`; it's a local baseline verifier that
  happens to be a Node app. ECDSA verify, freshness window, nonce cache, dashboard
  with synthetic 3-ROI waveforms.

**Adoption decision:** none of that code will be moved into the verified Android project.
Each stage in the implementation plan will rebuild the corresponding capability from
scratch inside `android/app/src/main/...` following the documented architecture, with
the out-of-tree code serving only as a reference for contracts (JNI signatures, ROIs,
canonical JSON shape, decision rules).

---

## 2. Android State (verified project)

### 2.1 Build configuration

- `android/build.gradle.kts` (root): declares AGP 9.4.1 only.
- `android/settings.gradle.kts`: Google + MavenCentral, rootProject.name = "EdgePPG",
  includes `:app`.
- `android/app/build.gradle.kts`: `com.android.application`, namespace
  `com.edgeppg.app`, applicationId `com.edgeppg.app`, compileSdk 37, minSdk 26,
  targetSdk 37, versionCode 1, versionName "0.1", release block with
  `isMinifyEnabled = false`, no release signing config. **No dependencies declared.**
- `android/gradle.properties`: `Xmx2048m`, `useAndroidX=true`.
- `android/gradle/wrapper/gradle-wrapper.properties`: distribution
  `gradle-9.6.0-bin.zip`.
- `android/gradlew` and `android/gradlew.bat`: present and executable.

### 2.2 Manifest and resources

- `AndroidManifest.xml`: declares only `MainActivity` with LAUNCHER intent filter.
  No `<uses-permission>` entries. No `<uses-feature>` entries. No `camera`, `internet`,
  `network_state`, `camera2` hardware features. No `<application>` icon. App theme
  declared as `@style/AppTheme`.
- `res/values/styles.xml`: minimal `Theme.Material.Light.NoActionBar` style.

### 2.3 Kotlin code

- Single source file `com.edgeppg.app.MainActivity`, an `Activity` (not `AppCompatActivity`)
  that inflates a `TextView` showing the literal text "EdgePPG".

### 2.4 Build verification

- A debug APK already exists at
  `android/app/build/outputs/apk/debug/app-debug.apk` (856 KB), produced by the
  verified toolchain. `output-metadata.json` confirms applicationId `com.edgeppg.app`,
  versionCode 1, versionName 0.1, minSdkForDexing 26.
- Per `EDGEPPG_MASTER_INSTRUCTIONS.md` §7 and `ANDROID_ENVIRONMENT.md`, the package
  is installed and launched on a physical iQOO device. ADB is not available in this
  Linux inspection environment; live device verification is out of scope for this
  audit but the build command and APK location are trusted per the verified env doc.

### 2.5 What's missing in Android

| Component | Source doc | State |
| --- | --- | --- |
| CameraX / Camera2 acquisition + 30 fps YUV analyzer | Arch §4.1, Stage 2 | Missing |
| AE/AWB converge-then-lock controller | Arch §4.1, Stage 2 | Missing |
| Face detection + 468-point landmarks | Arch §4.1, Stage 2 | Missing (ML Kit / MediaPipe dep not yet declared) |
| ROI extraction (forehead + L/R cheek) | Arch §4.5, Stage 2/4 | Missing |
| Per-frame RGB mean sampling from YUV_420_888 (zero-alloc) | Arch §4.5 | Missing |
| Gaze estimation (geometric) | Arch §4.2, Stage 6 | Missing |
| Head pose (yaw/pitch/roll) | Arch §4.3, Stage 6 | Missing |
| Hand landmark detection | Arch §4.4, Stage 6 | Missing |
| rPPG DSP — POS + bandpass + FFT + SNR + ROI agreement | Arch §4.5, Stage 4 | Missing |
| Optical challenge renderer (color/brightness/timing) | Arch §4.6, Stage 5 | Missing |
| Challenge engine (session-adaptive, nonce/seed, behavior + optical) | Arch §3, Stage 5 | Missing |
| Behavioral feature packager | Stage 6 | Missing |
| Motion/spike gate (blink/contamination routing) | Arch §11 | Missing (Stage 7) |
| Multi-person tracking (independent tracks) | Arch §5, Stage 8 | Missing |
| Feature schema validation + 28-row assembler | Arch §6, Stage 9 | Missing on-device (PC schema validator exists) |
| Frozen-model inference runtime (TFLite / ONNX-RT / NNAPI / vendor) | TechStack §16 | **structural DONE** (Android `features/MlFusionClient.kt` interface + `NaNFallbackMlClient.kt` returning NaN until a real loader is selected; on-device runtime gated on `TechStack §16` benchmark) |
| Security decision gates (LIVE / SPOOF / UNCERTAIN; quality → UNCERTAIN) | Arch §8, Stage 11 | Missing |
| Keystore ECDSA P-256 signing + canonical JSON envelope | Arch §9, Stage 12 | Missing on-device; PC verifier DONE |
| Local Wi-Fi transport (mechanism TBD) | Arch §10, Stage 13 | Missing on-device; PC HTTP intake DONE |
| QR-code fallback payload | Arch §10, Stage 13 | Missing |
| Camera / network permissions in manifest | Arch §11, NFR-OFF-1 | **DONE in Stage 1** |
| Camera capture state machine | Arch §11 | Missing (Stage 7) |
| UI surface beyond the placeholder TextView | Arch §4, FR-UI-* | Missing (Stage 15) |

### 2.6 Manifest gaps — Stage 1 fixes applied

- `<uses-permission android:name="android.permission.CAMERA" />` — DONE.
- `<uses-permission android:name="android.permission.INTERNET" />` — DONE
  (constrained to local Wi-Fi only; no cloud).
- `<uses-feature android:name="android.hardware.camera.front" android:required="true" />` — DONE.
- `<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />` — DONE
  (Stage 13 transport discovery will read it; nothing in Stage 1 uses it).
- Foreground service permission is **not** added — sessions are short, foreground only,
  per the architecture (no `Service` component required at this stage).

---

## 3. ML / PC State

- The PC-side ML pipeline is now in place under `ml/src/`. All 26 PC-side
  pipeline unit tests pass (`ml/tests/test_ml_pipeline.py`).
- A frozen-model artifact and manifest exist under `models/` —
  `edgeppg_rf_v1.{joblib,manifest.json}` and `edgeppg_xgb_v1.{joblib,manifest.json}`.
  Both manifests carry `status: UNTRAINED_NO_REAL_DATA` and were produced by
  a deterministic synthetic fixture. No `edgeppg_frozen.*` artifact is
  emitted until a real held-out validation set produces real metrics
  (per `freeze_model.freeze_for_runtime` semantics).
- `requirements.txt` is at the repo root and pins `cryptography` plus the
  training stack already present in `.venv/`.
- `ml/experiments/exp_NNN/` directory structure: not yet. The
  `models/*.manifest.json` records `dataset_fingerprint_sha256`,
  `n_subjects`, `n_train_rows`, `train_auc` (synthetic-only) and
  `split_files`, which is the same provenance an experiment would record.
- `data/raw/`, `data/processed/`, `data/splits/`: `splits/` is populated when
  the training pipeline runs; `raw/` and `processed/` are still empty —
  they will be populated when real validation data lands.
- `ml/src/train_mlp.py`: not implemented. The MLP is documented as
  Optional (`TechStack §3`) and is gated behind real-data availability —
  building it before then would not produce a frozen artifact and would
  complicate the runtime path with no benefit.

### 3.1 What the PC track must produce (target)

| Deliverable | State |
| --- | --- |
| `ml/src/feature_schema.py` (28-feature schema, versioned) | **DONE** |
| `ml/src/dataset.py` (GroupShuffleSplit on `subject_id`) | **DONE** |
| `ml/src/train_rf.py` | **DONE** (RF baseline; artifact written) |
| `ml/src/train_xgb.py` | **DONE** (XGBoost challenger; artifact written) |
| `ml/src/train_mlp.py` | Not started (gated on real data; TechStack §3 makes it Optional) |
| `ml/src/calibration.py` (configurable LIVE/SPOOF thresholds) | **DONE** (Platt scaler + Thresholds dataclass) |
| `ml/src/evaluate.py` (ROC-AUC, F1, attack-specific FAR/FRR) | **DONE** scaffolding (returns `unavailable` until real data exists; refuses to fabricate) |
| `ml/src/freeze_model.py` (export artifact for the runtime) | **DONE** (refuses to freeze without held-out metrics; export format left open per TechStack §7) |
| `ml/experiments/exp_NNN/` directory structure | Not started |
| `ml/tests/` unit tests | **DONE** (26 tests passing) |
| `data/raw/`, `data/processed/` | Empty; gated on real data |
| `data/splits/` | **DONE** scaffolding (CSVs written by `dataset.split_dataset_csv`) |
| Frozen model artifact (`edgeppg_frozen.*`) | Not started (gated on real held-out metrics) |

Because no real dataset exists yet, **no real-data model is trainable now**.
Per `NFR-MET-1` and the build prompt, we must not fabricate metrics or
attack samples. The synthetic-fixture artifacts are for pipeline
verification only and their manifests say so explicitly. Thresholds are
placeholder starting values (0.80 / 0.20 per `Requirements FR-GATE-8`).

---

## 4. PC Verifier (Baseline)

- The baseline PC verifier is **DONE**: `verifier/verify.py` (ECDSA
  P-256 / SHA-256 over the canonical envelope, freshness window,
  replay-nonce cache, structural validation), `verifier/canonical.py`
  (byte-exact canonical JSON), `verifier/receipt.py` (offline receipt
  writer), `verifier/server.py` (stdlib HTTP server with a minimal
  dashboard). All 26 verifier tests pass.
- The verifier is Office-Kit-independent and never makes network calls.
- The signed envelope uses the canonical key order documented in
  `Requirements §FR-CRY-3` (which supersedes the "exactly seven fields"
  reading in `Architecture §9` — see Risk §5.1 item 5 and the
  implementation plan's Stage 14 / 16 sync task). The canonical key
  order lives in `verifier/canonical.CANONICAL_KEY_ORDER` and is the
  single source of truth on the PC side; the Android-side emitter
  (`IntegrityManager.kt`, Stage 12) must match it byte-for-byte. We will
  add an explicit `docs/payload_format.md` once Stage 12 lands; for now
  the docstring in `verifier/canonical.py` is the binding contract.
- The Node-based verifier at `E:\code\EdgePPG\office-kit\` is referenced
  here only as an architectural reference for the ECDSA + freshness +
  nonce-cache pattern; we did not adopt its JavaScript implementation
  because the documented baseline is Python.

---

## 5. Risks and Open Issues

### 5.1 Real contradictions between docs (carry-over, not invented here)

These are flagged in `EDGEPPG_MASTER_INSTRUCTIONS.md` §"Known Conflicts" and
`Requirements.md` §8. The implementation plan resolves none of them silently:

1. **Gaze/hand core vs head-only.** Master treats gaze/head/hand as core; Final
   Architecture v2-1 lists only head motion. We implement all three per `FR-BEH-*`
   but mark gaze and hand `[Requires Device Test]`.
2. **Multi-person core vs absent.** We implement the multi-person mode per
   `FR-MP-1..3`, keeping it on the same Requires-Device-Test footing.
3. **Retry policy.** `Requirements FR-SESS-6` says "single controlled retry";
   `Architecture §11` / `Workflow G4` require configurable policy with no hard-coded
   count. The implementation will read the retry count from configuration (default 1).
4. **Office Kit role.** The plan treats Office Kit as optional/additive per
   `Requirements §FR-VER-3` and `Architecture §10`. We isolate any Office Kit work
   behind an interface; the baseline Python verifier is built first and is not
   blocked on Office Kit.
5. **Signed payload fields.** `Architecture §9` says "exactly seven fields" while
   `Requirements §FR-CRY-3` and Master §33 include additional fields (confidence,
   signal quality, observed responses). The canonical envelope built in Stage 13 will
   include the full `Requirements` set, not the Architecture §9 minimum, and we will
   record the resolution here when Stage 13 lands.

### 5.2 Risks specific to this build environment

- **No JDK / Android SDK in this Linux env.** The build cannot be exercised from
  `/mnt/e/EdgePPG/android/` in this sandbox; the verified build pipeline is on Windows
  per `ANDROID_ENVIRONMENT.md`. Stage verification here is limited to:
  - Static checks (Kotlin compiles structurally; manifests well-formed; DSL parses).
  - Python unit tests for the PC-side track.
  - A faithful local build attempt via Gradle wrapper to surface obvious Gradle
    / Kotlin / AGP mismatches — which will fail at the `JAVA_HOME` step here, exactly
    as expected, but proves the wrapper script is intact.
- **ML model is untrained.** Until a real dataset exists, the runtime must be capable
  of producing a feature vector, must NOT silently fabricate `P(LIVE)`, and must
  route anything that depends on the model to UNCERTAIN. This is wired explicitly
  in the decision engine (Stage 11).
- **Office Kit API unknown.** Per `TechStack §22`, Office Kit is unspecified and
  optional. We do not gate any other stage on it.
- **No data, no claims.** Per `NFR-MET-1` and the build prompt, every metric is
  placeholder until real data is collected.

### 5.3 Build status summary

| Path | Builds? | Installs? | Runs? | Verified on iQOO? |
| --- | --- | --- | --- | --- |
| `android/app/build/outputs/apk/debug/app-debug.apk` (pre-Stage-1 placeholder) | YES (per env doc) | YES (per env doc) | YES (placeholder UI) | YES (per env doc) |
| Stage-1 Android APK (new manifest, ComponentActivity, dev-mode logger) | structural YES — on-Windows build verification deferred to operator (`docs/stage1_verification.md`) | not run in this Linux sandbox | not run | not run |
| PC-side ML pipeline (synthetic-fixture only) | YES — `python -m ml.src.train_rf` and `train_xgb` produce artifacts | n/a | 26/26 tests pass | n/a |
| PC-side baseline verifier | YES — `python -m verifier.server` listens on `--port` | n/a | 26/26 tests pass; HTTP intake smoke-tested | n/a |
| Full EdgePPG pipeline (all stages done) | NO | NO | NO | NO |

Stage 1 is structurally complete; the on-Windows `./gradlew.bat assembleDebug`
step that confirms the build is the gating operator-side check (per
`docs/stage1_verification.md`).

---

## 6. What's NOT being changed in this pass

- `android/build.gradle.kts`, `android/app/build.gradle.kts` toolchain versions:
  AGP 9.4.1, Kotlin 2.2.10, compileSdk 37, minSdk 26, targetSdk 37.
- `android/gradle/wrapper/gradle-wrapper.properties` distribution URL and version
  (Gradle 9.6.0).
- `android/gradle.properties` JVM args.
- Application id / package name `com.edgeppg.app`.
- The `.venv/` Python venv (already provisioned; we use it, we don't move it).
- The `docs/` content for `Requirements.md`, `TechStack.md`, `Architecture.md`,
  `Workflow.md`, `EDGEPPG_MASTER_INSTRUCTIONS.md`, `ANDROID_ENVIRONMENT.md` — all
  treated as authoritative source of truth.
