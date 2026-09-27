# EdgePPG Tech Stack

This document lists technologies and their responsibilities for the EdgePPG system. It does **not** describe runtime interaction (see `Architecture.md`) and contains no demo or presentation content.

**Claim discipline:** Entries describe functional contributions (what a component computes/detects), not security guarantees. No technology is described as making the system "secure," "unspoofable," or guaranteeing detection.

**Classification legend:**
- **Core** — required for the end-to-end EdgePPG system/runtime defined by the Master Instructions.
- **Optional** — improves the system but is not required for that end-to-end runtime.
- **Research/Future** — explicitly named as an advanced/future direction.
- **Requires Verification** — plausible but unconfirmed/unbenchmarked.

**Hardware Status legend (device-dependent items):**
- **Verified** — confirmed available/behaves as expected on the actual device.
- **Requires Device Test** — plausible, unconfirmed on iQOO 15.
- **Optional-TBD** — nice-to-have, not required for baseline.
- **Research/Future** — advanced/future direction.

No iQOO 15 hardware capability is marked Verified because no device test has been run and the source docs do not confirm specific hardware behaviors.

---

## A. PC-Side ML Development Stack

*Dataset handling → feature engineering → training → evaluation → calibration → model selection → freeze/export. No on-device inference occurs here.*

### 1. Dataset Handling & Storage Format
- **Classification:** Core
- **Chosen or candidate(s):** Python + CSV; directory convention `data/{raw,processed,splits}/` with one row per session; `requirements.txt` for dependency capture.
- **Contribution:** Provides reproducible raw/processed/split storage for subject-session data and attack samples.
- **Why:** Master Instructions §§24,27 specify CSV per-session rows and explicit split directories.
- **Alternatives considered:** Parquet, HDF5 — CSV chosen for simplicity and auditability.
- **Feasibility risk / verification needed:** None (PC-side only).

### 2. Feature Engineering / Schema Tooling
- **Classification:** Core
- **Chosen or candidate(s):** `ml/src/feature_schema.py` defining a versioned ~25–30 feature schema with explicit scales, units, and missing-value flags.
- **Contribution:** Enforces a fixed, versioned feature contract between PC training and on-device inference.
- **Why:** Master §21 requires a stable schema; §§43–44 require explicit scales and missing-value handling.
- **Alternatives considered:** Schema-less dicts, pandas-only — rejected for contract enforcement.
- **Feasibility risk / verification needed:** None (PC-side only).

### 3. Training Framework (Random Forest, XGBoost, Optional MLP)
- **Classification:** Core (Random Forest baseline + XGBoost challenger); Optional (small MLP as third baseline)
- **Chosen or candidate(s):** scikit-learn-type RandomForestClassifier (baseline); XGBoost library (challenger); scikit-learn MLPClassifier or equivalent small MLP (optional third baseline only).
- **Contribution:** Trains engineered-feature-vector classifiers on the fixed ~25–30 schema. Random Forest is the baseline; XGBoost is evaluated against it; a small MLP may be evaluated as a third baseline. No end-to-end neural network on raw video/sensor data is in scope.
- **Why:** Master §§22,50 explicitly require RF baseline, XGBoost evaluation, and optional small MLP; end-to-end video NN is out of scope.
- **Alternatives considered:** LightGBM, CatBoost — XGBoost preferred per Master §22.
- **Feasibility risk / verification needed:** None (PC-side only). Model selection feeds #7.

### 4. Evaluation & Subject-Independent Split Tooling
- **Classification:** Core
- **Chosen or candidate(s):** scikit-learn `GroupShuffleSplit` / grouped cross-validation on `subject_id`; attack-specific FAR/FRR computation; ROC-AUC reporting.
- **Contribution:** Produces subject-independent performance estimates and per-attack-type metrics required for calibration.
- **Why:** Master §§26,28 mandate subject-independent splits and attack-specific FAR/FRR.
- **Alternatives considered:** Random splits — rejected due to subject leakage risk.
- **Feasibility risk / verification needed:** None (PC-side only).

### 5. Experiment Tracking Convention
- **Classification:** Core
- **Chosen or candidate(s):** Filesystem convention `ml/experiments/exp_NNN/{config.yaml,metrics.json,confusion_matrix.png,feature_importance.csv,model/}`; no vendor tracker assumed.
- **Contribution:** Guarantees reproducible experiment artifacts (config, metrics, visualizations, feature importance, serialized model) without external dependencies.
- **Why:** Master §§40–41 specify this exact folder structure for auditability.
- **Alternatives considered:** MLflow, Weights & Biases — rejected to avoid vendor lock-in for baseline.
- **Feasibility risk / verification needed:** None (PC-side only).

### 6. Calibration Tooling for Decision Thresholds
- **Classification:** Core
- **Chosen or candidate(s):** `calibration.py` computing configurable LIVE/SPOOF probability thresholds from validation data; 0.80/0.20 as starting points only.
- **Contribution:** Derives operating thresholds from validation performance; thresholds are configurable at runtime, not hardcoded.
- **Why:** Master §31 requires configurable thresholds with stated starting values.
- **Alternatives considered:** Hardcoded thresholds — rejected per Master §31.
- **Feasibility risk / verification needed:** None (PC-side only).

### 7. Model Freeze & Export Step
- **Classification:** Requires Verification
- **Chosen or candidate(s):** Candidates: `joblib`/`pickle` (scikit-learn native), ONNX export via `sklearn-onnx`/`xgboost-onnx`, runtime-specific export (tied to #16). None selected.
- **Contribution:** Serializes the selected frozen model for on-device loading. Final format depends on on-device inference runtime benchmark (#16).
- **Why:** Export format cannot be decided until the on-device runtime is benchmarked on iQOO 15.
- **Alternatives considered:** TensorFlow SavedModel, TorchScript — not applicable to RF/XGB/MLP baselines.
- **Feasibility risk / verification needed:** Blocked on #16 runtime benchmark on iQOO 15. Must confirm chosen format loads and executes within latency/memory budget.

---

## B. iQOO On-Device Runtime Stack

*Camera → feature extraction → frozen-model inference → P(LIVE) → security gates → signing → transport. Training never appears here.*

### 8. Platform & Language
- **Classification:** Core
- **Hardware Status:** Requires Device Test (exposure/AWB convergence, hardware timestamps per Arch p.1)
- **Chosen or candidate(s):** Android target; Kotlin **or** Java (both valid, neither mandated); CameraX **vs** Camera2 (undecided candidates).
- **Contribution:** Provides the application runtime, camera control, and frame acquisition pipeline.
- **Why:** Master Instructions specify Android; language and camera API are implementation choices requiring device validation.
- **Alternatives considered:** Native C++ camera HAL — rejected per NDK rule (#20).
- **Feasibility risk / verification needed:** CameraX vs Camera2 must be tested on iQOO 15 for exposure/AWB lock latency, frame timestamp availability, and YUV_420_888 access reliability.

### 9. Face Detection & Landmarks
- **Classification:** Core (capability); Requires Verification (exact model)
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Established mobile detector candidates only (MediaPipe-type Face Detection, ML Kit-type Face Detection). **Explicit: no custom detector training** (Master §11).
- **Contribution:** Detects faces and extracts facial landmarks for ROI definition, gaze/head-pose, and identity embedding.
- **Why:** Master §11 forbids training a custom detector; must use pretrained mobile-friendly model.
- **Alternatives considered:** BlazeFace, RetinaFace-Mobile — kept as unverified candidates.
- **Feasibility risk / verification needed:** Latency, memory, and landmark stability on iQOO 15 under varying illumination must be measured.

### 10. Face Identity / Embedding
- **Classification:** Core (capability); Requires Verification (exact model)
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Pretrained embedding model candidates (MobileFaceNet-type, FaceNet-type, ML Kit-type); cosine similarity → `identity_score`. **Explicit: no new recognition network training** (Master §12).
- **Contribution:** Computes a face identity embedding for multi-person tracking continuity and challenge personalization.
- **Why:** Master §12 forbids training a new recognition network; pretrained embedding + similarity is the specified approach.
- **Alternatives considered:** ArcFace, CosFace — kept as unverified candidates.
- **Feasibility risk / verification needed:** Embedding dimensionality, inference latency, and cross-session stability on iQOO 15 must be confirmed.

### 11. Gaze & Head Pose Estimation
- **Classification:** Core
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Landmark-based geometric computation (yaw/pitch/roll from 3D landmark projection; iris-vs-eye-corner for gaze).
- **Contribution:** Estimates head pose angles and gaze direction from detected landmarks for liveness features.
- **Why:** Master §§13–14 specify "prefer landmark-based geometry initially."
- **Alternatives considered:** Dedicated head-pose CNN (e.g., Hopenet) — deferred per Master preference for geometry-first.
- **Feasibility risk / verification needed:** Geometric stability under partial occlusion and extreme angles on iQOO 15 camera must be validated.

### 12. Hand Gesture Detection
- **Classification:** Core
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Lightweight hand-landmark model candidates (MediaPipe Hands-type); simple gesture set only (Master §15).
- **Contribution:** Detects hand landmarks and classifies simple gestures for challenge interaction features.
- **Why:** Master §15 specifies lightweight hand landmarks and simple gestures only.
- **Alternatives considered:** Full hand-pose estimation — rejected as over-specified for simple gestures.
- **Feasibility risk / verification needed:** Latency and false-positive rate on iQOO 15 must be measured; may share detector with face pipeline.

### 13. rPPG / DSP Stack
- **Classification:** Core (POS); Optional (CHROM alternative)
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** ROI extraction (forehead + cheeks) → adaptive normalization → **POS (primary, Core)** + **CHROM (preserved alternative, Optional)** → bandpass filter (0.7–4.0 Hz) → FFT/spectral analysis → SNR + quality-weighted multi-ROI consistency.
- **Contribution:** Extracts pulse signal from facial video via chrominance methods; computes SNR, peak frequency, and multi-ROI consistency features for liveness.
- **Why:** Arch p.1 names POS; Master §§16–17,47 preserve CHROM as alternative. Both must remain explicit — neither silently dropped.
- **Alternatives considered:** ICA, PCA-based methods — not in source docs.
- **Feasibility risk / verification needed:** POS vs CHROM robustness to motion/illumination on iQOO 15; optical challenge contamination (Arch p.2 light-matrix experiment); real-time FFT latency on device.

### 14. Optical Challenge Rendering & Correlation
- **Classification:** Core
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** `SecureRandom` per-session randomized sequence (color/brightness/duration/timing) rendered on screen; expected-vs-observed correlation computation with temporal separation from rPPG window.
- **Contribution:** Generates unpredictable visual challenge and computes correlation between expected and observed skin reflectance response.
- **Why:** Master §§8,19,47 specify randomized sequence, correlation metric, and temporal separation from rPPG; Arch p.2 describes the light-matrix experiment.
- **Alternatives considered:** Fixed challenge patterns — rejected per Master §8 (spoofability).
- **Feasibility risk / verification needed:** Screen-Δ detectability in bright/venue light on iQOO 15 display; correlation SNR under real-world conditions; temporal separation implementation correctness.

### 15. Multi-Person Tracking & Synchronization
- **Classification:** Core
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Two independent face tracks maintained via identity embeddings (#10) + temporal alignment of challenge/interaction features across tracks.
- **Contribution:** Sustains two simultaneous subject tracks and time-aligns their challenge responses for multi-person liveness evaluation.
- **Why:** Master §§9–11,20 require independent tracks and synchronized multi-person features.
- **Alternatives considered:** Single-track with ID switching — rejected per multi-person requirement.
- **Feasibility risk / verification needed:** Track continuity under crossing/occlusion; time-alignment accuracy on iQOO 15 (mandated by task rule).

### 16. ML Fusion Model (Runtime Only)
- **Classification:** Core (function); Requires Verification (inference runtime)
- **Hardware Status:** Requires Device Test (acceleration/NNAPI unconfirmed)
- **Chosen or candidate(s):** Loads frozen model from #3/#7; input = engineered feature vector; output = **P(LIVE) only — does not decide LIVE/SPOOF/UNCERTAIN**. Inference runtime candidates: TFLite / ONNX Runtime Mobile / NNAPI / vendor runtime (list only, no mandate).
- **Contribution:** Executes the frozen feature-vector classifier to produce a live probability; decision logic is separate (#17).
- **Why:** Master §§22–23 specify P(LIVE) output only; inference runtime must be benchmarked after model exists (RUNTIME RULE).
- **Alternatives considered:** None mandated — all candidates require verification.
- **Feasibility risk / verification needed:** Benchmark all candidates on iQOO 15 with candidate model; measure latency, memory, thermal, and numerical parity with PC inference. Final selection in Workflow.md.

### 17. Security Decision Gates
- **Classification:** Core
- **Chosen or candidate(s):** Pure application rule logic: consumes P(LIVE) + quality/integrity signals → emits LIVE / SPOOF / UNCERTAIN. **Insufficient quality or incomplete challenge routes to UNCERTAIN, never automatically SPOOF.**
- **Contribution:** Applies deterministic thresholds and quality gates to produce the final three-way liveness decision.
- **Why:** Master §§31–32 and Arch p.1 Gate 7 explicitly require UNCERTAIN for poor quality/incomplete challenge, not auto-SPOOF.
- **Alternatives considered:** ML-based decision head — rejected; decision must be rule-based and auditable.
- **Feasibility risk / verification needed:** Threshold calibration must align with #6; gate logic must be unit-tested exhaustively (#23).

### 18. Cryptography / Device Integrity
- **Classification:** Core
- **Hardware Status:** Requires Device Test (Keystore hardware-backing unconfirmed)
- **Chosen or candidate(s):** Android Keystore signing of transcript (`session_id, nonce, challenge_hash, result, model_version, protocol_version, timestamp`). **No custom cryptography; no keys in code or storage** (Master §§33–34).
- **Contribution:** Produces a device-bound, verifiable signature over the session transcript for PC verifier validation.
- **Why:** Master §§33–34 mandate Keystore usage and forbid custom crypto or key exposure.
- **Alternatives considered:** Software-only signing, TEE-direct — rejected per Master Keystore requirement.
- **Feasibility risk / verification needed:** Keystore hardware-backing behavior on iQOO 15 (StrongBox/TEE); signature verification compatibility with PC verifier; attestation availability.

### 19. Transport
- **Classification:** Core (Office-Kit-independent)
- **Hardware Status:** Requires Device Test
- **Chosen or candidate(s):** Local Wi-Fi primary (mechanism TBD: socket / HTTP / mDNS — do not assume) + QR-code fallback. Clipboard transport excluded (Arch p.1).
- **Contribution:** Delivers signed session transcript from device to PC verifier over local network or visual fallback.
- **Why:** Arch p.1 specifies local Wi-Fi + QR fallback; clipboard removed. Mechanism is implementation-defined.
- **Alternatives considered:** Bluetooth, NFC, cloud relay — excluded by local-only requirement.
- **Feasibility risk / verification needed:** Wi-Fi discovery/connection reliability on iQOO 15; QR payload capacity for full transcript; round-trip latency; offline receipt generation.

### 20. NDK/C++ Performance Path
- **Classification:** Optional
- **Hardware Status:** Optional-TBD
- **Chosen or candidate(s):** C++ via NDK for specific hot paths (DSP, inference) only if profiling demonstrates a real need.
- **Contribution:** Provides an optimization path for compute-intensive kernels; baseline system buildable without native code.
- **Why:** RUNTIME RULE: NDK is Optional and profiling-gated only.
- **Alternatives considered:** Full native implementation — rejected per rule.
- **Feasibility risk / verification needed:** Profile Java/Kotlin implementation first; only introduce NDK if measurable bottleneck exists.

---

## C. PC Verifier (Core, Standard)

### 21. PC Verifier Baseline
- **Classification:** Core
- **Chosen or candidate(s):** Python (candidate); signature verification, transcript parsing, nonce/timestamp/replay validation, result display, offline receipt generation. Operates over local Wi-Fi / QR transport only — no Office Kit dependency.
- **Contribution:** Verifies device-signed transcript integrity, freshness, and replay protection; displays human-readable result; produces offline receipt.
- **Why:** Master §§33–34 and Arch §7 Gate 7 define the baseline verifier; must function without vendor Office Kit.
- **Alternatives considered:** Web-based verifier, mobile app verifier — PC Python script specified as baseline for auditability.
- **Feasibility risk / verification needed:** Signature verification compatibility with #18 Keystore output; nonce/timestamp replay window tuning; QR decode robustness.

---

## D. Office Kit Integration (Optional, Vendor-Dependent)

### 22. Office Kit Enhanced Verifier
- **Classification:** Optional
- **Hardware Status:** Optional-TBD
- **Chosen or candidate(s):** Unknown/unspecified vendor API. No assumptions made.
- **Contribution:** Potential enhanced audit UI, fleet management, or enterprise integration layered additively on top of #21.
- **Why:** Master Instructions acknowledge Office Kit as a possible enhancement; its concrete API is unknown and integration is additive, never a prerequisite for #21.
- **Alternatives considered:** None — vendor-dependent.
- **Feasibility risk / verification needed:** Vendor product identification and API documentation required before any integration work.

---

## E. Testing & Experiment Tracking

### 23. Testing Infrastructure & Attack Validation Logging
- **Classification:** Core (capability); Requires Verification (exact frameworks)
- **Chosen or candidate(s):** Android: JUnit/Espresso-type unit and instrumented tests; PC: pytest-type for ML code; trial logger for attack-sample results (printed photo, phone replay, laptop/display replay, OLED replay, two-person replay) with attack-specific FAR/FRR logging. **Validation infrastructure only — no demo scripts, no LM Studio, no attack-controller, no presentation orchestration, no live attack staging procedures.**
- **Contribution:** Validates correctness of all pipeline components and records security-validation trial outcomes for engineering analysis.
- **Why:** Master §§28,42,66 require unit tests and attack-specific FAR/FRR; Arch p.3 lists attack types for validation.
- **Alternatives considered:** Robotium, Detox, custom harness — framework choice Requires Verification.
- **Feasibility risk / verification needed:** Select and validate test frameworks on CI; ensure attack trial logger captures all required metadata without becoming a demo tool.

---

## Stack Summary Table

| Group | Layer | Technology / Candidates | Classification | Hardware Status |
|-------|-------|------------------------|----------------|-----------------|
| A | 1. Dataset Handling & Storage | Python + CSV, `data/{raw,processed,splits}/` | Core | — |
| A | 2. Feature Schema Tooling | `feature_schema.py`, versioned ~25–30 schema | Core | — |
| A | 3. Training Framework | scikit-learn RF (baseline), XGBoost (challenger), small MLP (optional) | Core / Optional | — |
| A | 4. Evaluation & Split Tooling | `GroupShuffleSplit`, attack-specific FAR/FRR, ROC-AUC | Core | — |
| A | 5. Experiment Tracking | Filesystem `ml/experiments/exp_NNN/{config.yaml,metrics.json,...}` | Core | — |
| A | 6. Calibration Tooling | `calibration.py`, configurable thresholds | Core | — |
| A | 7. Model Freeze & Export | joblib / ONNX / runtime-specific (undecided) | Requires Verification | — |
| B | 8. Platform & Language | Android; Kotlin or Java; CameraX vs Camera2 | Core | Requires Device Test |
| B | 9. Face Detection & Landmarks | MediaPipe-type / ML Kit-type (no custom training) | Core (cap) / Requires Verification (model) | Requires Device Test |
| B | 10. Face Identity / Embedding | MobileFaceNet-type / FaceNet-type / ML Kit-type (no new training) | Core (cap) / Requires Verification (model) | Requires Device Test |
| B | 11. Gaze & Head Pose | Landmark-based geometry | Core | Requires Device Test |
| B | 12. Hand Gesture Detection | MediaPipe Hands-type, simple gestures | Core | Requires Device Test |
| B | 13. rPPG / DSP Stack | POS (Core), CHROM (Optional alternative), bandpass, FFT, multi-ROI | Core / Optional | Requires Device Test |
| B | 14. Optical Challenge & Correlation | SecureRandom sequence, expected-vs-observed correlation | Core | Requires Device Test |
| B | 15. Multi-Person Track & Sync | Two independent tracks + time alignment | Core | Requires Device Test |
| B | 16. ML Fusion (Runtime) | Frozen model load → P(LIVE); runtime: TFLite/ONNX-RT/NNAPI/vendor | Core (fn) / Requires Verification (rt) | Requires Device Test |
| B | 17. Security Decision Gates | Rule logic: P(LIVE)+quality → LIVE/SPOOF/UNCERTAIN (UNCERTAIN on poor quality) | Core | — |
| B | 18. Crypto / Integrity | Android Keystore signing; no custom crypto | Core | Requires Device Test |
| B | 19. Transport | Local Wi-Fi (mechanism TBD) + QR fallback | Core | Requires Device Test |
| B | 20. NDK/C++ | Profiling-gated hot paths only | Optional | Optional-TBD |
| C | 21. PC Verifier Baseline | Python, sig verify, nonce/timestamp/replay, display, receipt | Core | — |
| D | 22. Office Kit Integration | Unknown vendor API (additive only) | Optional | Optional-TBD |
| E | 23. Testing & Attack Validation | JUnit/Espresso-type, pytest-type, trial logger for 5 attack types | Core (cap) / Requires Verification (fw) | — |

---

## Feasibility Flags

*Every item below is **Requires Verification** or **Requires Device Test** and must be scheduled early in `Workflow.md`.*

1. **#7 Model Freeze & Export** — export format depends on #16 runtime benchmark.
2. **#8 Platform & Language** — CameraX vs Camera2; exposure/AWB/timestamp behavior on iQOO 15.
3. **#9 Face Detection & Landmarks** — exact model selection; latency/memory/landmark stability on device.
4. **#10 Face Identity / Embedding** — exact model; embedding dim/latency/stability on device.
5. **#11 Gaze & Head Pose** — geometric stability under occlusion/extreme angles on device.
6. **#12 Hand Gesture Detection** — latency, false-positive rate, detector sharing with face pipeline.
7. **#13 rPPG / DSP Stack** — POS vs CHROM robustness; optical challenge contamination (Arch p.2); real-time FFT latency.
8. **#14 Optical Challenge & Correlation** — screen-Δ detectability in bright light; correlation SNR; temporal separation correctness.
9. **#15 Multi-Person Track & Sync** — track continuity under crossing/occlusion; time-alignment accuracy.
10. **#16 ML Fusion Runtime** — benchmark TFLite/ONNX-RT/NNAPI/vendor on iQOO 15 with candidate model; latency/memory/thermal/numerical parity.
11. **#18 Crypto / Integrity** — Keystore hardware-backing (StrongBox/TEE) on iQOO 15; attestation availability.
12. **#19 Transport** — Wi-Fi mechanism selection/validation; QR payload/round-trip; offline receipt.
13. **#21 PC Verifier Baseline** — signature compatibility with #18; replay window; QR decode robustness.
14. **#22 Office Kit Integration** — vendor product/API identification (unknown until vendor engaged).
15. **#23 Testing Frameworks** — exact framework selection and CI integration; attack trial logger scope enforcement (no demo drift).

---

*End of TechStack.md. This document answers WHICH technology/candidate performs each responsibility. Runtime interaction → Architecture.md. Construction order → Workflow.md. No demo content included.*