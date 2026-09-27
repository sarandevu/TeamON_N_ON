# EdgePPG Architecture (Runtime)

**Scope:** This document describes how EdgePPG components operate and interact at runtime on the iQOO 15 device. It does not cover training, build order, or technology selection — those belong to `Workflow.md` and `TechStack.md` respectively.

**Frozen-model statement:** The ML classifier consumed at runtime is a frozen artifact produced by an offline, PC-side training process (detailed in `Workflow.md`). This document describes only its runtime execution.

**Security-claim discipline:** Every security property described below is a design intent whose actual effectiveness must be validated experimentally per the Final Architecture validation matrix. No claim here should be read as a guarantee that spoofing is impossible, that all attacks are prevented, or that liveness is assured.

**Device-capability tags:** Every iQOO 15–specific mechanism is tagged inline:
- `[Requires Device Test]` — plausible, needs confirmation on actual hardware (default)
- `[Optional/TBD]` — nice-to-have, not required for baseline
- `[Research/Future]` — explicitly deferred
- `[Verified]` — stated as available in source docs (none confirmed for iQOO 15)

---

## 1. System Overview Diagram

The canonical runtime flow (components may execute concurrently/pipelined in implementation but are documented in this order and all synchronized before Feature Vector Assembly):

```
Session Start
  → Nonce / Challenge Generation
       (session_id, nonce, timestamp, challenge seed, protocol version, model version)
  → Camera Acquisition
  → Face / Identity
  → Behavioral Features (gaze, head movement, hand gesture)
  → rPPG
  → Optical Challenge
  → Multi-Person Synchronization
       (cross-person timing, spatial relationship, challenge-sequence verification)
  → Feature Vector Assembly
  → Schema Validation / Preprocessing
  → ML Fusion → P(LIVE)
  → Security Gates
  → LIVE / SPOOF / UNCERTAIN
  → Signed Transcript (Keystore)
  → PC Verifier (via local Wi-Fi, QR fallback)
```

Functional layer names only (Camera, Face/ROI, Inference, Signing/Transport); framework choices deferred to `TechStack.md`.

---

## 2. Session Protocol

Per session, fresh values are generated:
- `session_id` — unique session identifier
- `nonce` — secure RNG output `[Requires Device Test]`
- `timestamp` — session start time
- `challenge seed` — entropy for challenge generation
- `protocol version` — wire format version
- `model version` — frozen classifier version

**Why fresh every session:** A fixed sequence (e.g., `LEFT → RIGHT → SMILE → BLINK`) would permit pre-recorded replay. Unpredictability is the root of challenge-response — design intent, requires validation.

**Signed transcript payload:** session ID, nonce, challenge sequence (+ hash), observed responses, feature/model versions, final result, timestamp.

---

## 3. Challenge Engine

Applicant and trusted-participant challenges are generated independently and differently each session. Two illustrative randomized examples (shape only, not scripts):

**Applicant:** `LOOK LEFT → TURN HEAD DOWN → LOOK AT PARTICIPANT`
**Trusted participant:** `RAISE RIGHT HAND → LOOK AT CAMERA → REMAIN STILL`

---

## 4. Per-Modality Pipelines

### 4.1 Face Detection & Identity
Input: camera frames → Output: bounding box, landmarks, tracking ID, confidence → embedding → similarity → `identity_score`.

### 4.2 Gaze Analysis
Input: eye-region landmarks → iris-vs-corner geometry → requested vs actual (LEFT/RIGHT/UP/DOWN/CENTER) + latency/success → gaze features.

### 4.3 Head Movement
Input: face landmarks → yaw/pitch/roll vs requested → head features.

### 4.4 Hand Gestures
Input: hand landmarks → simple gesture classification (raise, point, etc.) → hand features.

### 4.5 rPPG
Input: forehead + left/right cheek ROIs → temporal RGB → chrominance normalization via **POS and/or CHROM as alternatives** → bandpass → FFT → SNR, peak strength, HR stability, ROI agreement.
Supporting signal, not sole root of trust. PTT is `[Research/Future]`, not core. Optional randomized head-motion challenge is `[Optional/TBD]`.

### 4.6 Optical Challenge Analysis
Input: randomized screen brightness/color/timing → expected vs observed correlation + delay → `optical_response_score`, `optical_timing_error`, `optical_sequence_score`.

**Explicit warning:** Screen-induced RGB variation must not be confused with physiological rPPG. Mitigations: multi-ROI, temporal separation, normalization, quality gating. Experimental confirmation of this separation is `[Requires Device Test]`.

---

## 5. Multi-Person Synchronization

Applicant + Trusted Co-Presence Participant (never a "family-member requirement"). Each is tracked independently with separate fresh challenges. Verification covers: presence, identity, spatial relationship, temporal relationship, challenge ordering. Streams are time-aligned.

---

## 6. Feature Schema (Normative)

Frozen 28-feature schema from Master Engineering Instructions §21 (verbatim):

```
face_confidence, face_quality,
rppg_snr, rppg_peak_strength, rppg_hr_stability, rppg_roi_agreement,
gaze_accuracy, head_accuracy, hand_accuracy,
challenge_timing_error,
optical_response_score,
trusted_face_confidence, trusted_face_quality,
trusted_gaze_accuracy, trusted_head_accuracy, trusted_hand_accuracy,
trusted_challenge_timing_error,
cross_person_timing, cross_person_interaction,
relative_motion_consistency, participant_presence_consistency,
challenge_sequence_consistency,
camera_quality, frame_drop_rate, exposure_stability, awb_stability,
capture_duration, device_integrity
```

**Schema rules:**
- Frozen once data collection starts.
- Version bump + migration document required on any change.
- Pipeline-derived measurements (e.g., `rppg_hr`, latencies, `optical_timing_error`) remain intermediate unless a versioned schema change adopts them.

**Schema Validation / Preprocessing** is a distinct stage between Feature Vector Assembly and ML Fusion:
- Missing-value handling (never silently zero-fill unavailable rPPG)
- Scaling/normalization
- Never folded into Assembly or Fusion.

---

## 7. ML Fusion (Probability Only)

Schema-validated feature vector → frozen classifier → `P(LIVE)` (+ per-feature confidence/quality signals surfaced by the model).

**Explicit:** This stage does NOT decide LIVE/SPOOF/UNCERTAIN.

Model alternatives (decided in `TechStack.md`): Random Forest baseline, XGBoost evaluation, optional MLP — all preserved as alternatives, not mandates.

---

## 8. Security Decision Gates (Downstream, Application Logic)

Reproduces Master §31 pseudocode verbatim:

```
if critical_integrity_failure:          → SPOOF
elif insufficient_quality:              → UNCERTAIN
elif challenge_incomplete:              → UNCERTAIN
elif live_probability ≥ LIVE_THRESHOLD: → LIVE
elif live_probability ≤ SPOOF_THRESHOLD:→ SPOOF
else:                                   → UNCERTAIN
```

- Thresholds are configurable/calibrated, not hardcoded (0.80/0.20 are starting points only).
- Poor sensing SHALL produce UNCERTAIN and SHALL NOT be automatically treated as SPOOF.
- UNCERTAIN is a first-class result.
- This stage combines `P(LIVE)` with independent quality/integrity signals — application logic, not the model.

---

## 9. Cryptographic Binding & Signed Transcript

- Android Keystore-backed signing `[Requires Device Test]`
- No custom cryptography
- No keys in app storage or source code
- Signature covers exactly: `session_id, nonce, challenge_hash, result, model_version, protocol_version, timestamp`
- Nonce/challenge/timestamp binding provides replay validation

---

## 10. PC Verifier (Core Baseline Path)

- Transport: local Wi-Fi (primary), QR fallback — no cloud dependency, clipboard removed
- Verifies signature, checks nonce/timestamp for replay, displays result
- Works independently of any vendor Office Kit

**Office Kit** (signature verify + audit display + offline receipt, per Final Architecture §1) is a separate, optional, additive enhancement layered on top of this baseline — never a dependency.

---

## 11. Quality Gating & Failure Handling

- Blink/motion contamination → mark invalid, exclude from rPPG/challenge; configurable capture/retry policy (no hard-coded count)
- Missing values never silently zero-filled (unavailable rPPG ≠ 0)
- Capture state machine: `CAPTURE → QUALITY CHECK → BASELINE → RANDOMIZED CHALLENGE → MOTION/BLINK CHECK → PROCESS`

---

## 12. Security Layers Summary

1. Identity
2. Behavioral liveness
3. Physiological evidence
4. Optical challenge
5. Multi-person co-presence
6. Temporal consistency
7. Capture/device integrity
8. Cryptographic session binding

Each layer contributes at runtime; all require experimental validation.

---

## 13. Known Limitations

- Live relay / virtual-camera attacks and a fully compromised capture path are out of scope as a design boundary.
- No guarantee language applies — all security properties require experimental validation per the Final Architecture validation matrix.