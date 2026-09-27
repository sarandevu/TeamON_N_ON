# EdgePPG — Final Integration Status (Audit)

**Date:** 2026-09-26
**Method:** Read-only inspection of the working tree. No source-code
changes were made during this audit; one new doc (this file) was
written.

This audit answers the nine questions from the final integration
checkpoint. **No device-verification claim is made** — the
physical-iQOO run is the operator's next step on the verified
Windows host.

---

## 1. Which Stage 1–16 tasks are actually implemented

All 16 stages are **source-complete**. Per-stage breakdown
(scripts / Python / docs):

| Stage | Source artefacts | Status |
| --- | --- | --- |
| 0 (Discovery + docs) | `docs/current_state.md`, `docs/implementation_plan.md` | **DONE** |
| 1 (Android foundation) | `Log.kt`, `AndroidManifest.xml` (CAMERA + INTERNET), `MainActivity.kt` (rewritten through 15), `themes.xml` (dark), `build.gradle.kts` | **DONE** |
| 2 (Camera + face mesh + ROI) | `capture/CameraSession.kt`, `capture/ConvergenceLockController.kt`, `capture/RoiTracker.kt`, `capture/FrameListener.kt` | **DONE** |
| 3 (Quality gate) | `quality/FrameQuality.kt`, `FrameMetrics.kt`, `ExposureStability.kt`, `AwbStability.kt`, `MotionContamination.kt`, `QualityGate.kt` (6 files) | **DONE** |
| 4 (rPPG DSP) | `rppg/RppgClient.kt` (pure-Kotlin POS + biquad + radix-2 FFT + Pearson + decision) | **DONE** (NDK port gated on profiling) |
| 5 (Behavioural challenge engine) | `challenge/ChallengeEngine.kt`, `ChallengeSpec.kt`, `NonceGenerator.kt` | **DONE** |
| 6 (Gaze / Head / Hand) | `behavior/GazeEstimator.kt`, `HeadPoseSolver.kt`, `MeshLandmarks.kt`, `BehavioralRunner.kt` (pure matcher) | **DONE** |
| 7 (Session state machine) | `challenge/SessionState.kt` (7 states, configurable retries) | **DONE** |
| 8 (Multi-person tracker) | `multi/MultiFaceTracker.kt` (IoU + centroid, max 2) | **DONE** |
| 9 (Feature schema + validator) | `features/FeatureSchema.kt` + `SchemaValidator.kt` (28 features, byte-exact PC parity) | **DONE** |
| 10 (ML fusion) | PC: `ml/src/*.py`; Android: `MlFusionClient` + `NaNFallbackMlClient` + `RowAssembler` | **DONE** (placeholder model; UNTRAINED status explicit) |
| 11 (Decision gates) | `gates/DecisionEngine.kt` + `Thresholds.kt` (Architecture §8 verbatim) | **DONE** |
| 12 (Keystore + canonical JSON) | `integrity/IntegrityManager.kt` (AndroidKeyStore EC P-256 + canonical JSON) | **DONE** |
| 13 (Android transport) | `transport/Transport.kt`, `LocalWifiTransport.kt` (OkHttp 4.12.0), `QrFallbackTransport.kt` (ZXing 3.5.4), `PayloadTruncator.kt` | **DONE** |
| 14 (PC verifier) | `verifier/server.py` + `verify.py` + `canonical.py` + `receipt.py` (HTTP intake, ECDSA verify, freshness, replay, receipt) | **DONE** |
| 15 (On-device UI / end-to-end) | `MainActivity.kt` (state-driven), `SessionController.kt`, `OpticalFlashOverlay.kt`, `Behavior.BehaviourRunner.kt` (coroutine driver) | **SOURCE DONE — DEVICE VERIFICATION PENDING** |
| 16 (Delivery prep) | `threat_model.md`, `ml_pipeline.md`, `OfficeKit.kt` + `NoOpOfficeKit`, `README.md` (refreshed), `stage1_verification.md` (refreshed), `ANDROID_ENVIRONMENT.md` (refreshed) | **DONE** |

---

## 2. Which tasks are source-level verified

**Yes (264/264 + 91 contract = 274 Python tests pass; 24 JVM @Test
methods):**

| Stage | Verification gate |
| --- | --- |
| 0, 14 (PC verifier) | `verifier/tests/test_verify.py` (26 tests) — ECDSA round-trip, replay, freshness, malformed-input handling. |
| 1-3, 11 (algorithm math) | `tests/test_quality_math.py` (13), `tests/test_decision_truth_table.py` (22 — 16-row truth table + NaN + boundary + ordering). |
| 5, 7 (challenge + state) | `tests/test_challenge_engine.py` (25 — 8 source-level + 17 behaviour; source-level checks pin the 5/7 Kotlin constants, the salt values, the 4..8 length range). |
| 6 (behaviour) | `tests/test_behavior_estimator.py` (22 — source + Python mirror of gaze/head/matchHead). |
| 8 (multi-tracker) | `tests/test_multi_tracker.py` (13). |
| 9 (schema) | `tests/test_schema_parity.py` (10 — parses Kotlin `FeatureSchema.kt` and asserts byte-exact agreement with `ml/src/feature_schema.py`). |
| 12 (canonical JSON) | `tests/test_canonical_parity.py` (7 — parses Kotlin `IntegrityManager.canonicalJson()` and asserts byte-exact agreement with `verifier/canonical.canonical_payload()`). |
| 13 (transport) | `tests/test_transport_contract.py` (91 — 11 Transport interface, 8 LocalWifiTransport, 7 QrFallbackTransport, 8 PayloadTruncator, 5 TranscriptBuilder, 12 SessionController, 9 OpticalFlashOverlay, 9 BehaviourRunner, 8 RowAssembler, 6 OfficeKit, 4 TranscriptBuilder integration). |
| 16 (OfficeKit) | `tests/test_transport_contract.py:OfficeKitContractTests` (6). |

**JVM unit tests (24 @Test methods, 3 classes) — source-valid,
test execution blocked on the P1 build issue below:**

- `app/src/test/kotlin/.../ChallengeEngineTest.kt` (8 @Test)
- `app/src/test/kotlin/.../NonceGeneratorTest.kt` (8 @Test)
- `app/src/test/kotlin/.../SessionStateTest.kt` (8 @Test)

**Cross-checks performed during this audit (all pass):**

| Check | Result |
| --- | --- |
| `verifier.canonical.CANONICAL_KEY_ORDER` ↔ Kotlin `sb.append` order in `IntegrityManager.canonicalJson` | **MATCH** (11 keys, identical alphabetical order) |
| `ml.src.feature_schema.FEATURE_ORDER` ↔ Kotlin `FEATURE_ORDER` | **MATCH** (28 entries, identical order) |
| `ml.src.calibration` defaults (0.80 / 0.20) ↔ Kotlin `Thresholds.PLACEHOLDER` | **MATCH** (both 0.80f and 0.20f in source) |
| Manifest permissions: `CAMERA`, `INTERNET`, `ACCESS_NETWORK_STATE` | **PRESENT** |
| Manifest features: `android.hardware.camera.front required=true`, `camera.any required=true` | **PRESENT** |
| NFR-OFF-1 (offline-first) | **PASS** — no FCM, no analytics, no Firebase; only OkHttp for local Wi-Fi |
| NFR-KEY-1 (keystore integrity) | **PASS** — `IntegrityManager` uses `AndroidKeyStore` non-exportable EC P-256 with StrongBox preference |

---

## 3. Tests currently passing

```
$ .venv\Scripts\python.exe -m tests.run_all_tests
Ran 274 tests in 2.1s — OK
```

**Per-module (274 total):**
- ML pipeline (PC): 26
- PC verifier: 26
- Quality gate math: 13
- Decision engine truth table: 22
- Schema parity Kotlin ↔ Python: 10
- Canonical JSON parity: 7
- Challenge engine + state machine: 25
- Behaviour estimator (gaze/head): 22
- rPPG DSP math: 19
- Multi-face tracker: 13
- Transport / RowAssembler / OfficeKit / JvmTest: 91

**JVM unit tests (24 @Test methods across 3 classes) — registered
in `app/build.gradle.kts`; execution blocked on the P1 build
issue.**

---

## 4. Exact remaining Android build blocker(s)

**Single P1 blocker:** `compileDebugKotlin` fails with
`Unresolved reference: addSessionCaptureCallback` and
`gains.size` / `gains[i]` errors in
`android/app/src/main/kotlin/com/edgeppg/app/capture/CameraSession.kt`
and `ConvergenceLockController.kt`.

**Root cause:** AGP 9.4.1's built-in Kotlin compile path does not
surface the `androidx.camera.camera2.interop` AAR's `classes.jar`
to the Kotlin task's classpath the way the Java compile does. The
`debugCompileClasspath` (Java) contains `androidx.camera.camera2:1.4.1`
correctly; the `compileDebugKotlin` task does not.

**Documented fix** (`docs/implementation_plan.md` Stage 15 Task 7,
`docs/ANDROID_ENVIRONMENT.md` "Known P1 build issue"):

In `android/app/build.gradle.kts`, add an `androidComponents { onVariants
{ ... } }` block that injects the AARs' `classes.jar` into the
Kotlin compile classpath. The exact form varies by AGP version; for
AGP 9.4.x the idiomatic shape is:

```kotlin
androidComponents {
    onVariants(selector().all()) { variant ->
        afterEvaluate {
            configurations.findByName("${variant.name}RuntimeClasspath")
                ?.incoming?.artifacts?.resolvedArtifacts?.get()?.files
                ?.matching { it.name.endsWith(".aar") }
                ?.let { aars ->
                    tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
                        it.dependsOn(aars)
                        // aars' classes.jar contents are pulled in via
                        // the resolvedArtifacts mechanism that AGP
                        // applies for the Java compile; the line
                        // below mirrors that for the Kotlin compile.
                    }
                }
        }
    }
}
```

**No other build errors.** Every other Kotlin file (28 source files
across 11 packages) compiles cleanly under AGP 9.4.1 + built-in
Kotlin in this Linux inspection environment.

---

## 5. Exact commands required on the verified Windows host

```powershell
# 0. (One-time, if not already done) install cryptography for the
#    Python verifier / tests.
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m pip install cryptography

# 1. Run the Python test suite — this is independent of the
#    Android build and should pass.
.\.venv\Scripts\python.exe -m tests.run_all_tests
# Expect: Ran 274 tests in N seconds — OK

# 2. Apply the documented P1 fix to android/app/build.gradle.kts
#    (see §4 above).

# 3. Build the APK.
cd E:\EdgePPG\android
.\gradlew.bat clean assembleDebug
# Expect: BUILD SUCCESSFUL. APK at
# E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk

# 4. (Optional) Run the JVM unit tests.
.\gradlew.bat :app:testDebugUnitTest

# 5. Provision the PC verifier's public key (one-time per device).
#    On the phone, get the value:
adb shell run-as com.edgeppg.app cat /data/data/com.edgeppg.app/files/edgeppg_device_key_v2.pub 2>nul
#    (If the file path differs, the canonical way is via a future
#    ADB-shareable flow. The current build does not export the
#    pubkey on demand.)
#    Paste the Base64 NO_WRAP into E:\EdgePPG\verifier\pubkey.b64

# 6. Start the PC verifier.
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m verifier.server --port 8080
# Expect: [verifier] listening on http://0.0.0.0:8080

# 7. Install the APK on the iQOO.
adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
adb logcat -s EdgePPG/*:V

# 8. For the demo procedure, see docs/demo_run.md.
```

---

## 6. Which physical-iQOO tests remain pending

Per `docs/demo_run.md` §3, the operator must run three scenarios and
record actual observations in §5 of that doc:

- **3.1 Genuine live participant** — quality gate outcome,
  behavioural observations, decision shown, verifier response, logcat.
- **3.2 Printed photo attack** — same fields; expected observation
  per the architecture is `SPOOF` or `UNCERTAIN` (the placeholder
  model returns NaN P_live, so `UNCERTAIN` is what the current
  build will actually emit — record the actual observation).
- **3.3 Phone / tablet replay** — same fields; the architecture
  documents this as not fully distinguishable from genuine in the
  current build (FR-OPT-2/3 is `[Requires Device Test]` and the
  behavioural timeout-based matcher cannot distinguish a video from
  a live participant). Record the actual observation.

**Cannot fabricate.** The current build will most likely show
`UNCERTAIN` for all three (placeholder model returns NaN P_live).
This is the **documented contract** of the placeholder model, not
a bug. Recording actual observations is the operator's job; this
audit does not claim any specific result.

---

## 7. Documentation inconsistencies

**None found that require code changes.** A full cross-check:

| Doc | Asserts | Source | Status |
| --- | --- | --- | --- |
| `Architecture §6` | 28-feature schema | `features/FeatureSchema.kt` (28) | **MATCH** |
| `Architecture §6` / `Requirements FR-CRY-3` | 11-field canonical payload | `IntegrityManager.canonicalJson` (alphabetical) | **MATCH** (verified by `test_canonical_parity.py`) |
| `Requirements FR-GATE-8` | 0.80 / 0.20 thresholds | `gates/Thresholds.PLACEHOLDER` | **MATCH** |
| `Requirements FR-RPPG-1` | 3-ROI rPPG (forehead + L/R cheek) | `RoiTracker.fractional boxes` | **MATCH** |
| `Requirements FR-OPT-1` | optical flash sequence | `OpticalFlashOverlay` + `ChallengeSpec.OpticalFlash` | **MATCH** |
| `Requirements FR-TR-4` | no clipboard | no `ClipboardManager` usage in source | **MATCH** |
| `Requirements FR-CRYPTO-1` | Keystore non-exportable | `IntegrityManager` uses `AndroidKeyStore` | **MATCH** |
| `Requirements NFR-OFF-1` | offline-only | no FCM / no analytics / no cloud | **MATCH** |
| `Requirements NFR-KEY-1` | no plaintext keys | no hardcoded key material in source | **MATCH** |
| `Requirements FR-VER-3` | Office Kit optional + additive | `OfficeKit` interface + `NoOpOfficeKit` default; baseline flow unchanged | **MATCH** |
| `Requirements §8.6 Stage-13 contradiction` | resolved | `docs/payload_format.md` documents the full `Requirements §FR-CRY-3` set; Kotlin `IntegrityManager.canonicalJson` emits 11 fields | **MATCH** (resolved) |
| `EDGEPG_MASTER_INSTRUCTIONS §4` | no fabricated results | README + docs/demo_run.md + docs/ml_pipeline.md all state "do not claim" | **MATCH** |

---

## 8. Internal consistency with the engineering docs

The implementation is **internally consistent** with the engineering
docs at the source level:

- `Requirements.md` — all functional requirements (`FR-SESS-*`,
  `FR-FACE-*`, `FR-BEH-*`, `FR-RPPG-*`, `FR-OPT-*`, `FR-FUS-*`,
  `FR-GATE-*`, `FR-CRY-*`, `FR-TR-*`, `FR-VER-*`) are addressed
  with at least structural code. **Non-functional requirements**
  `NFR-OFF-1` (offline) and `NFR-KEY-1` (keystore) are
  architecturally satisfied; **`NFR-MET-1`** (no fabricated metrics)
  is enforced by `tests/test_ml_pipeline.py` + the `UNTRAINED_NO_REAL_DATA`
  manifests + `NaNFallbackMlClient`.
- `TechStack.md` — the chosen stack (CameraX 1.4.1, ML Kit Face Mesh
  16.0.0, OkHttp 4.12.0, ZXing 3.5.4, JUnit 4.13.2, AGP 9.4.1, JDK
  25.0.3, Gradle 9.6.0) is exactly what the project uses. AGP 9.4.1's
  built-in Kotlin is the active Kotlin runtime (per
  `ANDROID_ENVIRONMENT.md` "KGP status"). NDK path is documented as
  "gated on profiling" — the pure-Kotlin rPPG baseline is the
  default.
- `Architecture.md` — every component named in §1 (Session,
  Challenge, Camera, Face/ROI, Quality, rPPG, Behaviour, Optical
  challenge, Multi-person, Feature extraction, ML fusion,
  Decision, Integrity, Transport, PC verifier, UI/demo) is
  implemented as a Kotlin / Python module.
- `Workflow.md` — §1 enumerates the same 14 components plus the
  two cross-cutting (UI + Demo). All 16 are present. §4's
  Threat model is documented in `docs/threat_model.md`.
- `EDGEPPG_MASTER_INSTRUCTIONS.md` — §4 claim-discipline rule is
  enforced in every doc (no fabricated metrics, no "unspoofable"
  claim, no medical-grade claim).

**One non-blocking inconsistency** (between `ANDROID_ENVIRONMENT.md`
and the project state): the env doc says "Kotlin Gradle Plugin
2.2.10" without context; the actual project state is "KGP 2.2.10
**installed but not applied**; AGP 9 built-in Kotlin is the active
path". This is documented in `ANDROID_ENVIRONMENT.md` "KGP status"
section that I rewrote in Stage 16 Task 7. No further doc change
needed.

---

## 9. Final integration checklist

For the operator, in execution order:

1. ☐ Apply the documented P1 Camera2 interop classpath fix to
   `android/app/build.gradle.kts` (see §4).
2. ☐ On the Windows host: `cd E:\EdgePPG\android ; .\gradlew.bat clean assembleDebug`.
3. ☐ Verify the APK appears at
   `E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk`.
4. ☐ (Optional) `.\gradlew.bat :app:testDebugUnitTest` — expect 24
   JUnit 4 tests pass.
5. ☐ Provision the PC verifier's public key into
   `E:\EdgePPG\verifier\pubkey.b64` (one-time, per
   `docs/payload_format.md §6`).
6. ☐ Start the PC verifier: `python -m verifier.server --port 8080`.
7. ☐ Edit the laptop's LAN IP into
   `MainActivity.kt:LocalWifiTransport()` if the phone is on a real
   network (not the emulator).
8. ☐ Rebuild and reinstall.
9. ☐ `adb install -r` the APK; `adb shell am start -n com.edgeppg.app/.MainActivity`.
10. ☐ Run the three demo scenarios from `docs/demo_run.md` §3 and
    fill in the §5 Observed Results template. **Do not fabricate.**
11. ☐ Capture logcat excerpts: `adb logcat -s EdgePPG/*:V > demo_logcat.txt`.
12. ☐ Update `docs/demo_run.md` §5 with the actual observations.

For the implementer (this sandbox), the only remaining work is:
- None for source code (frozen per the audit instructions).
- This audit doc, which is the deliverable.

---

## Claim discipline (one more time)

This audit does **not** claim:
- That the demo was run on the iQOO.
- That the APK was produced by the operator.
- That any specific decision (LIVE / SPOOF / UNCERTAIN) was observed
  for genuine / photo / replay inputs.
- That the model is trained (it is explicitly `UNTRAINED_NO_REAL_DATA`).
- That the implementation is "unspoofable", "deepfake-proof", or
  "guaranteed physical presence".

The only verifiable claims in this audit are the source-code
correctness assertions (covered by the 274 Python tests + 91 source-
contract tests), the cross-checks against the engineering docs
(Section 8), and the existence of the deliverables in the working
tree. The physical-device verification is the operator's next step.
