# EDGEPPG_MASTER_INSTRUCTIONS.md

The highest-level operational instruction layer for any AI coding agent working on EdgePPG.
This file governs and references the documents below — it does not replace them and does not invent architecture.

## 1. What EdgePPG Is

EdgePPG is a session-adaptive, multi-person active liveness and anti-spoofing system for Video KYC (VKYC), running on iQOO hardware with a PC-side verifier. Instead of passively asking whether a face matches a claimed identity, it issues a fresh, unpredictable multi-modal challenge per session and checks that physiological (rPPG), behavioral, optical, temporal, identity, and multi-person evidence respond consistently within one cryptographically bound session. Individual components are established technologies; the contribution is their protocol-level composition and temporal binding. This is a research/security hypothesis requiring experimental validation — never describe it as unspoofable, deepfake-proof, medical-grade, or guaranteeing physical presence.

## 2. Document Hierarchy

- **Level 1 — Master Source Material.** `Research_docs/EdgePPG_Master_Engineering_Instructions_Muse_Spark_1.3 (1).pdf` and `Research_docs/EdgePPG_FINAL_Architecture_v2-1.pdf`. Ultimate architectural source of truth.
- **Level 2 — This file (`EDGEPPG_MASTER_INSTRUCTIONS.md`).** Translates Level 1 into persistent instructions for AI agents. Preserves the intended architecture; invents none.
- **Level 3 — Core Engineering Documents.** `docs/Requirements.md` (what) · `docs/TechStack.md` (which technology) · `docs/Architecture.md` (how components operate/interact) · `docs/workflow.md` (how to discover, build, integrate, test, deliver). Must remain mutually consistent.
- **Level 4 — Android Environment.** `docs/ANDROID_ENVIRONMENT.md` plus `docs/EdgePPG_Muse_Spark_Android_Environment_Instructions.pdf`. An implementation constraint, NOT an architectural source.
- **Level 5 — Repository Implementation.** Actual source code. Must be brought into alignment with Levels 1–3, never used to silently redefine them.

On any conflict, higher level wins; report the conflict before changing anything (see §8).

## 3. Canonical Runtime Architecture

Canonical conceptual pipeline (order is normative):

```
1. Session Start
2. Nonce / Challenge
3. Camera
4. Face / Identity
5. Gaze / Head / Hand Behavioral Features
6. rPPG
7. Optical Challenge
8. Multi-Person Synchronization
9. Feature Vector
10. Schema Validation / Preprocessing
11. Frozen ML Model
12. P(LIVE)
13. Security Gates
14. LIVE / SPOOF / UNCERTAIN
15. Signed Transcript
16. PC Verifier
```

Components may execute concurrently or pipelined where `docs/Architecture.md` permits it. Such concurrency is an implementation property and must NOT be interpreted as architectural reordering, nor used to justify dropping, merging, or reordering stages.

## 4. Core Security Model

The following are invariants. An agent must not casually alter them:

- Secure, unpredictable per-session challenge generation (fresh session ID, nonce, timestamp, challenge seed; protocol/model versions bound to the session).
- Randomized optical challenge (color/brightness/duration/timing), with expected-vs-observed facial-reflection correlation.
- Front-camera capture with face/ROI quality gating (exposure/illumination, ROI visibility, eye/blink state, head motion, signal quality); invalid segments rejected or retried, never silently scored.
- Multi-ROI rPPG (forehead, left/right cheeks): RGB/chrominance normalization, POS and/or CHROM processing, bandpass filtering, FFT/SNR and temporal features. rPPG is supporting evidence, never the sole root of trust.
- Challenge-response correlation with temporal separation between optical stimulus and physiological measurement, plus normalization, multi-ROI checks, and quality gating.
- Optional motion verification as a second active challenge where the architecture permits it.
- Behavioral evidence (gaze/head/hand against the fresh challenge), multi-person synchronization (independent per-person challenges, presence/identity/spatial/temporal/ordering checks), and evidence fusion into one session decision.
- Frozen ML model producing `P(LIVE)` only; security gates kept distinct from ML fusion; final state one of `LIVE` / `SPOOF` / `UNCERTAIN`.
- Poor sensing conditions (low light, motion, weak signal, incomplete challenge) must NOT automatically be treated as spoofing — they route to `UNCERTAIN` or a controlled retry per the documented policy.
- Android Keystore-backed signing of the session transcript; signed transcript transported over local Wi-Fi (primary) or QR (fallback); PC-side verification including signature check and replay protection via nonce/timestamp/session information.

Overclaiming is forbidden: never use "deepfake-proof," "guaranteed physical presence," "medical-grade," "impossible to spoof," or equivalent absolutes.

## 5. ML Boundary

Invariant boundary:

```
Features → Frozen ML Model → P(LIVE) → Security Gates → Final Decision
```

- **PC-side:** dataset preparation, feature extraction/processing, training, model comparison, evaluation, calibration, model selection, model freeze/export.
- **Android/iQOO runtime:** camera capture, face/ROI processing, behavioral feature extraction, rPPG, optical challenge, multi-person synchronization, feature-vector construction, schema validation, frozen-model inference, security gates, transcript signing.

Training never moves into the runtime. The ML model must never silently become the entire security decision system: `P(LIVE)` plus independent quality/integrity/challenge signals feed the gates; the gates decide.

## 6. PC / Android Responsibility Split

- **Android/iQOO:** runtime sensing, processing, inference, challenge execution, security gating, signed evidence generation.
- **PC:** model development/training, evaluation tooling, verifier (public-key/signature verification, nonce/session/timestamp validation, replay checks, QR/local-Wi-Fi reception, logging/audit).

Implementation details may evolve, but this boundary must not be casually changed without explicit justification recorded in documentation.

## 7. Verified Android Environment

Implementation infrastructure (Level 4), not architecture:

- OS: Windows 11
- Project root: `E:\EdgePPG`
- Android project: `E:\EdgePPG\android`
- Android Studio installed; Android SDK configured
- Android platform/API 37
- Build Tools 36.0.0
- JDK 25.0.3
- Gradle 9.6.0
- Android Gradle Plugin 9.4.1
- Kotlin Gradle Plugin 2.2.10
- Project-local Gradle wrapper: `E:\EdgePPG\android\gradlew.bat`
- Verified build command:
  ```powershell
  .\gradlew.bat assembleDebug
  ```
- Debug APK output: `E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk`
- Device check: `adb devices`
- Install: `adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"`
- Physical iQOO device connection, APK build/install/launch: already verified. Current app is a placeholder — the starting implementation state, not the final application.

Agents must NOT recreate the Android project, reinstall Android Studio/SDK, unnecessarily change the JDK, replace the Gradle wrapper, or migrate build systems, without a demonstrated, documented compatibility requirement. Full detail lives in `docs/ANDROID_ENVIRONMENT.md`.

## 8. Agent Behavior Rules

Any future AI coding agent must:

- Treat Levels 1–3 documentation as source of truth; never redesign architecture or silently swap major components.
- Treat the Android environment (Level 4) as a constraint to respect, not an architecture to modify.
- Inspect the full repository (Level 5) before making changes — never assume state, verify it.
- Implement incrementally; never attempt an uncontrolled full-system implementation in one pass.
- Build/verify after each meaningful stage with the verified build command; a feature counts as done only when it builds and, where applicable, runs on the physical device — not merely when code is written.
- Never fabricate ML results or claim a model "works" before testing; keep `UNCERTAIN` as a legitimate outcome.
- Never make absolute security/medical claims (see §4).
- When implementation forces a technical or architectural decision, update the relevant document and record the reason — never change architecture silently.
- Report contradictions between documents, or between documentation and the verified environment/repository, before any major architectural change; distinguish genuine contradictions from mere implementation detail; never silently resolve them.

## 9. Documentation Synchronization Rule

Whenever an implementation choice changes an architectural or technical decision, the appropriate document (`docs/Requirements.md`, `docs/TechStack.md`, `docs/Architecture.md`, `docs/workflow.md`, or this file) must be updated in the same change, with the reason recorded. Documentation and implementation must never be allowed to drift apart.

## 10. Validation Requirement

Validate by compiling/building after meaningful changes with `.\gradlew.bat assembleDebug`, running on the physical iQOO device where applicable, and executing the tests and gates defined in `docs/workflow.md`. Never report a feature as complete based on source code alone.

## Verification Status

- **Confirmed:** §1–§6 invariants from the two Level 1 PDFs (full text extracted); §7 toolchain/paths/build/APK/ADB/package facts from the Android Environment PDF; hierarchy and rules as instructed by the task prompt.
- **UNVERIFIED / NEEDS CONFIRMATION:** device serial and live ADB authorization state (not stated in any source); Windows-side paths as observed from this Linux checkout (trusted from PDF, not directly confirmable here).

## Known Conflicts / Needs Resolution

1. **Gaze/hand core vs head-motion-only:** Master Instructions treat gaze, head, and hand challenges as core; Final Architecture v2-1 lists only an optional head-motion instruction. (`docs/Requirements.md` §8 already discloses this.)
2. **Multi-person core vs absent:** Master Instructions treat multi-person co-presence as core; Final Architecture v2-1 omits it from the architecture layer. (Also disclosed in `docs/Requirements.md` §8.)
3. **Retry policy:** Final Architecture says allow one controlled retry; `docs/Requirements.md` FR-SESS-6 hard-codes a single retry while `docs/Architecture.md` §11 and `docs/workflow.md` G4 require a configurable policy with no hard-coded count.
4. **Office Kit role:** Final Architecture Gate 7 wording can read as Office Kit being the verifier; the MDs resolve it as baseline standalone verifier plus optional additive Office Kit enhancement.
5. **Signed-payload wording:** `docs/Architecture.md` §9 says the signature covers "exactly" seven fields while `docs/Requirements.md` FR-CRY-3 and Master §33 include additional fields (confidence, signal quality, observed responses).

None of the above were silently resolved in this file; human decision required.
