# EdgePPG Workflow — Construction Order

**Purpose:** This file defines HOW the repository is inspected, implemented, integrated, tested, and delivered. It is a **construction order** for a coding agent to execute stage-by-stage with checkboxes.

**Authoritative execution order** is defined in `docs/Architecture.md` (session start → … → PC verifier). This file's staged build order may legitimately differ (e.g., rPPG before challenge engine integration) — that is intentional.

**Claim-discipline rule:** No documentation deliverable produced via this workflow (README, etc.) may claim guaranteed security or spoof-proofing. Use defensible wording only.

**Cross-references** are generic by document/layer name only (e.g., "`docs/TechStack.md` — rPPG DSP", "`docs/Architecture.md` — decision flow"). No section numbers are assumed. No duplication of Architecture or TechStack content.

**Attack work** is worded only as **attack/validation evidence** (engineering validation). Excluded from this workflow: LM Studio, attack-controller implementation, attack staging/selection for presentation, live demo sequencing, presentation choreography, demo scripts. Those belong in a separate demo/red-team document.

---

## 0. Timeline (inline GREEN/ORANGE/RED labels)

- Repository Discovery — **ORANGE**
- Pre-Build Gates (G1–G7) — **RED**
- Staged Build Plan (Stages 1–14) — **RED**
- Priority Order — informational
- PC-Side ML Track — **RED**
- iQOO Runtime Track — **RED**
- Verifier Track — **RED**
- Testing Checkpoints — **RED**
- Documentation Deliverables — **RED** (produced-by-this-workflow)
- Agent Behavior Rules — informational

---

## 1. Repository Discovery (first, gates everything)

**Ownership:** split PC / iQOO items individually  
**Status:** ORANGE

- [ ] Inspect repository: language, Android structure, CV modules, rPPG, challenge, ML code, dependencies
- [ ] Determine current implementation state per component
- [ ] Produce `docs/current_state.md` (existing component, status, location, dependencies, missing functionality)
- [ ] Produce `docs/implementation_plan.md` (phase, task, dependencies, test, status)
- [ ] **Gate:** Do NOT modify architecture or start large refactors until discovery is complete

---

## 2. Pre-Build Gates (must pass before feature work)

Each gate tagged: Ownership · Status · Hardware Status (where iQOO device/API-dependent)

- [ ] G1 rPPG stable — iQOO · RED · Hardware Status: Requires Device Test
- [ ] G2 multi-ROI temporal consistency — iQOO · RED · Hardware Status: Requires Device Test
- [ ] G3 active-challenge detectable under bright ambient light — iQOO · RED · Hardware Status: Requires Device Test
- [ ] G4 blink/motion contamination → configurable retry policy (not SPOOF) — iQOO · RED · Hardware Status: Requires Device Test
- [ ] G5 attack/validation set collected — PC · RED
- [ ] G6 transport tested (Wi-Fi primary, QR fallback) — Verifier · RED
- [ ] G7 Core PC Verifier tested independent of any Office Kit — Verifier · RED

---

## 3. Staged Build Plan (14 stages)

Every stage carries all 9 fields: Ownership, Status, Hardware Status (where applicable), Goal, Inputs, Built, Outputs, Handoff, Definition of Done, Test/validation. All Status: RED initially.

### Stage 1: Camera + Face + Tracking
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Acquire camera frames, detect/track faces, output ROIs
- **Inputs:** `docs/TechStack.md` — Camera API; `docs/Architecture.md` — session start
- **Built:** Camera acquisition module, face detector, tracker, ROI emitter
- **Outputs:** Per-frame ROI rectangles + landmarks
- **Handoff:** → Stage 2 (challenge engine), Stage 4 (rPPG)
- **Definition of Done:** Stable 30 fps ROI output on target device; no dropped frames under normal light
- **Test:** Unit test: synthetic frames → expected ROI coordinates

### Stage 2: Challenge Engine
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Generate fresh nonce/seed per session, emit per-session challenge sequences
- **Inputs:** `docs/Architecture.md` — challenge flow; `docs/TechStack.md` — RNG, secure storage
- **Built:** Nonce generator, challenge sequencer, session binder
- **Outputs:** Signed challenge payload per session
- **Handoff:** → Stage 3 (behavioral), Stage 5 (optical), Stage 13 (crypto)
- **Definition of Done:** Cryptographically fresh nonce per session; challenge sequences vary and are unpredictable
- **Test:** 1000 sessions → all nonces unique; statistical randomness check

### Stage 3: Gaze / Head / Hand Behavioral Features
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Extract gaze direction, head pose, hand landmarks per challenge frame
- **Inputs:** `docs/TechStack.md` — MediaPipe/ML Kit; `docs/Architecture.md` — behavioral capture
- **Built:** Gaze estimator, head-pose solver, hand landmark detector, feature packager
- **Outputs:** Per-frame behavioral feature vector (frozen schema subset)
- **Handoff:** → Stage 7 (feature collector)
- **Definition of Done:** Features extracted at challenge frame rate; latency < 50 ms/frame
- **Test:** Replay validation clips → feature vectors match frozen schema

### Stage 4: rPPG DSP
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Multi-ROI POS + bandpass + FFT → waveform + SNR per session
- **Inputs:** `docs/TechStack.md` — DSP libs; `docs/Architecture.md` — multi-ROI pipeline
- **Built:** ROI signal extractor, POS filter, bandpass (0.7–4 Hz), FFT, SNR calculator
- **Outputs:** Clean waveform, heart-rate estimate, SNR, quality flags
- **Handoff:** → Stage 7 (feature collector)
- **Definition of Done:** SNR > 10 dB on live subjects; motion artifact rejection via retry policy
- **Test:** Synthetic PPG + motion → SNR and HR within tolerance

### Stage 5: Optical Challenge Render + Response Correlation
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Render screen-flash challenge, correlate camera response with temporal separation from rPPG
- **Inputs:** `docs/Architecture.md` — optical challenge flow; `docs/TechStack.md` — display sync, camera exposure
- **Built:** Challenge renderer, exposure sync, response correlator
- **Outputs:** Optical response score, liveness indicator
- **Handoff:** → Stage 7 (feature collector)
- **Definition of Done:** Correlation peak detectable under bright ambient; spoof replays produce no correlation
- **Test:** Live + printed photo + phone replay → live scores high, replays low

### Stage 6: Two-Person Mode & Synchronization
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Detect second face, synchronize dual ROI pipelines, emit combined feature set
- **Inputs:** `docs/Architecture.md` — two-person flow; Stage 1, Stage 4 outputs
- **Built:** Second-face detector, dual-track synchronizer, combined feature packager
- **Outputs:** Synchronized dual-subject feature vectors
- **Handoff:** → Stage 7 (feature collector)
- **Definition of Done:** Two faces tracked simultaneously; feature vectors time-aligned within 33 ms
- **Test:** Two-subject recording → dual features aligned, no identity swap

### Stage 7: Feature Collector (Frozen Schema)
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Aggregate all per-session features into single frozen-schema row
- **Inputs:** `docs/Architecture.md` — feature schema; Stages 3–6 outputs
- **Built:** Schema validator, NaN/missing handler, row assembler, CSV/Parquet writer
- **Outputs:** One-row-per-session dataset files (frozen schema)
- **Handoff:** → Stage 8 (dataset), Stage 9 (model training), Stage 6 runtime
- **Definition of Done:** Every session produces exactly one row; schema matches frozen spec; missing values handled per policy
- **Test:** Schema validation on 1000 sessions → zero mismatches

### Stage 8: Dataset (One Row = One Session)
- **Ownership:** PC
- **Status:** RED
- **Hardware Status:** N/A
- **Goal:** Curate, split, and version-control the training/validation dataset
- **Inputs:** Stage 7 outputs; `docs/Architecture.md` — subject-independent split
- **Built:** Dataset repo, GroupShuffleSplit by `subject_id`, versioned splits (train/val/test), attack/validation subset
- **Outputs:** Versioned dataset artifacts, split manifests, attack sample catalog
- **Handoff:** → Stage 9 (training)
- **Definition of Done:** No subject appears in more than one split; attack samples cataloged with ground truth
- **Test:** Split integrity check → zero subject leakage; attack catalog complete

### Stage 9: Baseline Fusion Model (Engineered Feature Vector Only)
- **Ownership:** PC
- **Status:** RED
- **Hardware Status:** N/A
- **Goal:** Train RF → XGBoost → optional MLP on engineered feature vector; no end-to-end raw-video NN
- **Inputs:** `docs/Architecture.md` — fusion; Stage 8 dataset; `docs/TechStack.md` — ML libs
- **Built:** RandomForest baseline, XGBoost evaluator, optional MLP, calibration (Platt/Isotonic), model exporter (ONNX/TFLite)
- **Outputs:** Frozen model artifact + calibration params + evaluation report
- **Handoff:** → Stage 10 (attack eval), Stage 11 (security gates), Stage 13 runtime
- **Definition of Done:** ROC-AUC ≥ 0.95 on held-out test; calibration ECE < 0.02; model size < 5 MB
- **Test:** Ablation study Model 1 (face-only) → Model 7 (full stack) logged; attack-specific FAR/FRR recorded

### Stage 10: Attack/Validation Evaluation
- **Ownership:** PC
- **Status:** RED
- **Hardware Status:** N/A
- **Goal:** Run frozen model on attack/validation set; record attack-specific FAR/FRR as evidence
- **Inputs:** Stage 8 attack subset; Stage 9 frozen model
- **Built:** Evaluation harness, per-attack-type FAR/FRR calculator, evidence report
- **Outputs:** Attack-specific FAR/FRR table, validation evidence bundle
- **Handoff:** → Stage 11 (threshold calibration), delivery prep
- **Definition of Done:** All five attack types evaluated (printed photo, phone replay, laptop/display replay, OLED replay, two-person replay); FAR/FRR per type documented
- **Test:** Evidence bundle reproducible from frozen model + fixed dataset version

### Stage 11: Security Decision Gates
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** ML → P(LIVE) → independent gates → LIVE/SPOOF/UNCERTAIN; poor quality/incomplete evidence → UNCERTAIN (never auto-SPOOF)
- **Inputs:** `docs/Architecture.md` — decision flow; Stage 9 model + calibration; Stage 7 features
- **Built:** Gate evaluator (quality checks, temporal consistency, challenge pass/fail), decision engine, UNCERTAIN router
- **Outputs:** Final decision (LIVE/SPOOF/UNCERTAIN) + audit trail
- **Handoff:** → Stage 13 (Keystore signing)
- **Definition of Done:** Truth table covers all combos; UNCERTAIN triggered on low SNR / missing challenge / motion contamination; no path to SPOOF without positive evidence
- **Test:** Decision truth table unit test (16+ rows) → all PASS

### Stage 12: UI (DEV_MODE vs Clean Mode)
- **Ownership:** iQOO
- **Status:** RED
- **Hardware Status:** Requires Device Test
- **Goal:** Minimal on-device UI; DEV_MODE exposes diagnostics; clean mode exposes only result; no crypto material exposed
- **Inputs:** `docs/Architecture.md` — UI requirements; Stage 11 decision output
- **Built:** Camera preview overlay, challenge prompt renderer, result screen, DEV_MODE toggle
- **Outputs:** APK with UI; DEV_MODE flag gated by build config
- **Handoff:** → Stage 13 (integration), Stage 14 (delivery)
- **Definition of Done:** Clean mode shows only LIVE/SPOOF/UNCERTAIN; DEV_MODE shows waveforms, scores, timing; no key material in logs
- **Test:** Manual smoke: DEV_MODE on → diagnostics visible; clean mode → only result

### Stage 13: Crypto/Session Layer + Core PC Verifier
- **Ownership:** split — Keystore signing iQOO / Verifier path Verifier
- **Status:** RED
- **Hardware Status:** Keystore signing: Requires Device Test; Verifier: N/A
- **Goal:** Keystore-sign result transcript on device; Core Verifier verifies sig + transcript + nonce/timestamp/replay over Wi-Fi/QR
- **Inputs:** `docs/Architecture.md` — crypto flow; `docs/TechStack.md` — Android Keystore, TLS/QR libs; Stage 2 nonce, Stage 11 decision
- **Built:** 
  - iQOO: Keystore wrapper, transcript builder, QR encoder, Wi-Fi transport
  - Verifier: Signature verifier, transcript parser, nonce/timestamp/replay checker, audit logger, offline receipt generator
- **Outputs:** Signed transcript (device), verification result + audit log (PC)
- **Handoff:** → Stage 14 (delivery)
- **Definition of Done:** 
  - Device: transcript signed with non-extractable key; QR + Wi-Fi both work
  - Verifier: accepts valid, rejects replayed/expired/tampered; logs audit; works without Office Kit
- **Test:** 
  - Device: 100 sessions → all transcripts verify
  - Verifier: replay attack → rejected; clock-skew ±5 min → accepted; expired nonce → rejected

### Stage 14: Delivery Prep
- **Ownership:** split per item
- **Status:** RED
- **Hardware Status:** Per item
- **Goal:** Reproducibility bundle, on-device benchmark, docs package
- **Inputs:** All prior stage outputs
- **Built:** 
  - Reproducibility: pinned deps, build scripts, dataset version, model hash
  - Benchmark: latency (ms), memory (MB), battery (mAh/session) on target
  - Docs: `README.md`, `docs/Architecture.md`, `docs/Requirements.md`, `docs/TechStack.md`, `docs/threat_model.md`, `docs/ml_pipeline.md`, `docs/current_state.md`, `docs/implementation_plan.md`
- **Outputs:** Release bundle, benchmark report, docs package
- **Handoff:** — (end)
- **Definition of Done:** Clean build from scratch passes; benchmark within targets; all docs present and claim-discipline compliant
- **Test:** CI: fresh checkout → build → test → benchmark → doc lint → all GREEN

---

## 4. Priority Order If Time Runs Out

1. End-to-end functionality
2. Security protocol
3. Attack/validation evidence
4. Robust feature extraction
5. ML fusion
6. UI polish
7. Advanced optimization

**Never** sacrifice the end-to-end pipeline for a more sophisticated model.

---

## 5. PC-Side ML Track (Detail)

**Ownership:** PC  
**Status:** RED per item

- [ ] Dataset collection and storage
- [ ] Subject-independent split (GroupShuffleSplit by `subject_id`)
- [ ] Feature analysis against frozen schema
- [ ] Training: RandomForest baseline
- [ ] Training: XGBoost evaluation
- [ ] Training: Optional MLP (engineered feature vector only — no end-to-end raw-video NN)
- [ ] Evaluation: accuracy / precision / recall / F1 / ROC-AUC / attack-specific FAR/FRR
- [ ] Threshold calibration (Platt/Isotonic)
- [ ] Model freeze and export (ONNX/TFLite)
- **Rule:** One row = one session
- **Ablation sequence:** Model 1 (face-only) → Model 2 (+rPPG) → Model 3 (+behavioral) → Model 4 (+optical) → Model 5 (+two-person) → Model 6 (+quality gates) → Model 7 (full stack)

---

## 6. iQOO Runtime Track (Detail)

Each item: **Ownership: iQOO · Status: RED · Hardware Status: Requires Device Test** (depth/IR, PTT = Research-Future if mentioned)

- [ ] Camera acquisition
- [ ] Face/ROI detection & tracking
- [ ] Behavioral features (gaze, head, hand)
- [ ] rPPG DSP (POS, bandpass, FFT, SNR)
- [ ] Optical challenge render & correlation
- [ ] Multi-person synchronization
- [ ] Feature extraction against frozen schema
- [ ] Frozen-model inference → P(LIVE) only
- [ ] Security decision gates (LIVE/SPOOF/UNCERTAIN; poor quality → UNCERTAIN)
- [ ] Keystore signing of result transcript

---

## 7. Verifier Track (Detail)

### 7a. Core PC Verifier (required, tracked independently)
- **Ownership:** Verifier
- **Status:** RED
- **Flow:** Wi-Fi/QR → signature verification → transcript validation → nonce/timestamp/replay validation → result display/logging → offline receipt
- Must work without any Office Kit integration.

### 7b. Optional Office Kit Integration
- **Ownership:** Verifier (Optional: Office Kit)
- **Status:** RED
- Enhancement only; concrete implementation depends on unconfirmed environment.
- Core Verifier (7a) must pass without it.

---

## 8. Testing Checkpoints (Mapped to Stages, Ownership-Tagged)

- Challenge generation (fresh nonce / varying / independent) — iQOO
- Feature extraction (missing/NaN handling) — iQOO / PC split
- rPPG edge cases (short / noisy / missing-ROI / motion / few-frames) — iQOO
- Decision-engine truth table (incl. UNCERTAIN-for-poor-quality) — iQOO
- Attack/validation-sample testing — PC

All RED initially.

---

## 9. Documentation Deliverables Checklist

| File | Existing | Produced by This Workflow |
|------|----------|---------------------------|
| README.md | No | Yes |
| docs/Architecture.md | No | Yes |
| docs/Requirements.md | No | Yes |
| docs/TechStack.md | No | Yes |
| docs/threat_model.md | No | Yes |
| docs/ml_pipeline.md | No | Yes |
| docs/current_state.md | No | Yes |
| docs/implementation_plan.md | No | Yes |

**Note:** Claim-discipline rule applies to all. Demo/red-team document is out of scope for this workflow.

---

## 10. Agent Behavior Rules

- Inspect before modifying
- Plan before large changes
- Incremental implementation
- Run tests after major components
- Never fabricate functionality, metrics, or validation
- Document limitations when blocked instead of faking a fallback silently