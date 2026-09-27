# Requirements Specification for EdgePPG

## 1. Project Summary
EdgePPG is a session-adaptive, multi-modal active liveness and anti-spoofing system for Video KYC (VKYC) designed to run locally on iQOO 15 hardware with a PC-side verifier as the standard result-verification endpoint. It addresses the vulnerabilities of passive face-matching pipelines to replay and presentation attacks, as well as the privacy and connectivity limitations associated with cloud-based biometric verification. In strict compliance with the claim-discipline rule, EdgePPG is designed as a risk-reduction system; it does not prevent spoofing, guarantee liveness, or make spoofing impossible, and all claims of its liveness detection capabilities must be tied directly to empirical validation against specified attack datasets.

The novel contribution of this system is defined as follows:
> EdgePPG introduces a session-adaptive multi-person active VKYC protocol that combines unpredictable behavioral challenges, optical challenge-response, remote photoplethysmography, identity verification, trusted co-presence, cross-person temporal interaction, and device/session integrity into a single verification transaction. Individual components are established technologies; the proposed contribution is their protocol-level composition and temporal binding for active VKYC.

---

## 2. Functional Requirements

### Session & Challenge Engine
*   **FR-SESS-1:** The system SHALL initialize a fresh, unique VKYC session upon start by generating a secure session payload containing a session ID, a cryptographically secure pseudo-random nonce, a high-precision timestamp, a challenge seed, a protocol version, and a model version.
*   **FR-SESS-2:** The challenge sequence SHALL be generated dynamically *after* the session has started using the secure session challenge seed to prevent replay of fixed sequence patterns.
*   **FR-SESS-3:** The challenge engine SHALL support a set of unpredictable, randomized instructions to be presented to the applicant, including looking left, right, up, or down, turning the head, nodding, remaining still, raising a specific hand, or performing simple gestures.
*   **FR-SESS-4:** In two-person mode, the challenge engine SHALL generate different, independent challenge instructions for the primary applicant and the trusted participant.
*   **FR-SESS-5:** The capture engine SHALL implement a robust session state machine transition path: Capture $\rightarrow$ Quality Check $\rightarrow$ Baseline $\rightarrow$ Randomized Challenge $\rightarrow$ Motion/Blink Check $\rightarrow$ Processing.
*   **FR-SESS-6:** If a quality event (such as a blink or sudden head motion) contaminates a capture segment during the challenge window, the system SHALL invalidate the affected frames and allow a single controlled retry of that challenge segment.
*   **FR-SESS-7:** A full session transcript file SHALL be generated upon session completion, containing the session ID, cryptographic nonce, dynamic challenge sequence, raw observed sensor response features, model/protocol versions, final gate decision, and timestamp.

### Face/Identity
*   **FR-FACE-1:** The system SHALL perform real-time face detection on the device, returning a face bounding box, facial landmark coordinates, a face tracking ID, and detection confidence. Technology selection is deferred to TechStack.md.
*   **FR-FACE-2:** In two-person mode, the system SHALL maintain independent, simultaneous tracking for both detected individuals.
*   **FR-FACE-3:** The system SHALL support face identity verification by computing face embeddings and comparing them against a pre-enrolled embedding to produce a similarity and identity score. Technology selection is deferred to TechStack.md.
*   **FR-FACE-4:** The system SHALL independently enroll and verify the second co-present individual, designated as the Trusted Co-Presence Participant.

### Behavioral Liveness (Gaze/Head/Hand)
*   **FR-BEH-1:** The system SHALL perform geometric gaze analysis by tracking pupil/iris coordinates relative to eye corners to verify whether the applicant is looking Left, Right, Up, Down, or Center. **[Requires Device Test]**
*   **FR-BEH-2:** For each gaze challenge, the system SHALL record the requested action, the actual detected action, response latency, and success status, and compute aggregate metrics for gaze accuracy, latency, and consistency.
*   **FR-BEH-3:** The system SHALL estimate head pose (yaw, pitch, roll) from facial landmarks to verify head-turning and nodding challenges.
*   **FR-BEH-4:** For each head challenge, the system SHALL record the requested action, actual detected action, and yaw/pitch/roll trajectories, and compute aggregate metrics for head accuracy, response latency, and head-motion consistency.
*   **FR-BEH-5:** The system SHALL support verifying simple hand gestures using hand landmark coordinates. Technology selection is deferred to TechStack.md.
*   **FR-BEH-6:** For each hand gesture challenge, the system SHALL record the requested gesture, the actual detected gesture, latency, and success status to compute hand accuracy.

### rPPG & Physiological Evidence
*   **FR-RPPG-1:** The system SHALL extract contactless physiological signals (rPPG) from multiple facial Regions of Interest (ROIs), specifically the forehead, left cheek, and right cheek.
*   **FR-RPPG-2:** The rPPG extraction pipeline SHALL utilize motion-aware tracking to dynamically adjust facial ROIs during head movement or facial expression changes.
*   **FR-RPPG-3:** The rPPG analyzer SHALL calculate independent ROI physiological metrics, including rPPG signal-to-noise ratio (SNR), heart-rate estimate, peak strength, heart-rate stability, and cross-ROI signal agreement.
*   **FR-RPPG-4:** The system SHALL estimate signal quality metrics, including exposure stability, auto-white-balance (AWB) stability, camera frame rate consistency, and frame drop rates.
*   **FR-RPPG-5:** The system SHALL implement a face/ROI quality gate that assesses ambient illumination, face visibility, blink states, and motion contamination, discarding segments that fail to meet quality criteria.
*   **FR-RPPG-6:** Physiological evidence SHALL be treated strictly as a supporting biometric signal; it SHALL NOT be the sole root of trust for liveness.

### Optical Challenge
*   **FR-OPT-1:** The system SHALL project a fresh, unpredictable, randomized optical sequence on the screen, varying color, brightness, duration, and transition timing (e.g., color transitions such as blue $\rightarrow$ red, green $\rightarrow$ white, white $\rightarrow$ blue, red $\rightarrow$ green).
*   **FR-OPT-2:** The system SHALL measure the change in light reflected from the user's face to verify correlation with the screen's randomized stimulus sequence, producing an optical response score, optical timing error, and optical sequence score.
*   **FR-OPT-3:** The optical challenge response and the physiological rPPG signals SHALL be analyzed with strict temporal separation, normalization, multi-ROI checks, and quality gating to ensure screen-induced display variations are not falsely attributed to endogenous cardiac pulses. **[Requires Device Test]**
*   **FR-OPT-4:** The system SHALL require that a measurable facial reflection response above ambient-light and camera noise levels is experimentally confirmed prior to session progression. **[Requires Device Test]**

### Multi-Person Mode & Cross-Person Synchronization
*   **FR-MP-1:** The system SHALL support a simultaneous Multi-Person Mode, requiring the presence and coordination of an Applicant and a Trusted Co-Presence Participant.
*   **FR-MP-2:** The system SHALL verify cross-person interactions, requiring specific coordinated actions (e.g., Applicant looking at the Trusted Co-Presence Participant, or the Trusted Co-Presence Participant looking at the camera) in a validated sequence and temporal order.
*   **FR-MP-3:** The system SHALL compute multi-person features including trusted participant face confidence, trusted participant face quality, trusted gaze/head/hand accuracy, trusted challenge timing error, cross-person timing, cross-person interaction, relative motion consistency, participant presence consistency, and challenge sequence consistency.

### ML Fusion
*   **FR-FUS-1:** The ML Fusion component SHALL operate strictly on a fixed engineered numerical feature vector of approximately 25–30 features representing aggregated session metrics (e.g., face confidence, face quality, rPPG SNR, rPPG peak strength, HR stability, ROI agreement, gaze/head/hand accuracies, optical scores, and multi-person interaction features). An end-to-end neural network operating on raw video or sensor feeds is explicitly out of scope.
*   **FR-FUS-2:** The ML Fusion component SHALL output a single liveness probability value $P(\text{LIVE})$ between 0.0 and 1.0.
*   **FR-FUS-3:** The ML probability $P(\text{LIVE})$ SHALL NOT itself constitute the final verification decision. Decision-making is strictly deferred to the independent Security Decision Gates.

### Security Decision Gates
*   **FR-GATE-1:** The final session decision (LIVE, SPOOF, or UNCERTAIN) SHALL be evaluated by an independent set of hard-coded security gates that integrate the $P(\text{LIVE})$ output with quality, integrity, and challenge completion signals.
*   **FR-GATE-2:** If a critical device, session, or capture integrity failure is detected, the decision gates SHALL immediately return a SPOOF result.
*   **FR-GATE-3:** If the quality gate determines that there is insufficient sensing quality, incomplete behavioral challenge response, or low rPPG signal quality, the decision gates SHALL return an UNCERTAIN result.
*   **FR-GATE-4:** Insufficient sensing quality, incomplete challenges, or low signal quality SHALL NOT be automatically treated as a SPOOF result.
*   **FR-GATE-5:** The decision gates SHALL return a LIVE result if and only if:
    1. No integrity failures are present.
    2. Quality and challenge completion requirements are met.
    3. $P(\text{LIVE})$ meets or exceeds a configurable and calibrated `LIVE_THRESHOLD`.
*   **FR-GATE-6:** The decision gates SHALL return a SPOOF result if and only if:
    1. A critical integrity failure is detected, OR
    2. $P(\text{LIVE})$ falls below a configurable and calibrated `SPOOF_THRESHOLD`.
*   **FR-GATE-7:** If quality and challenge requirements are met but $P(\text{LIVE})$ falls strictly between `SPOOF_THRESHOLD` and `LIVE_THRESHOLD`, the decision gates SHALL return an UNCERTAIN result.
*   **FR-GATE-8:** The security decision gate thresholds (`LIVE_THRESHOLD` and `SPOOF_THRESHOLD`) SHALL be configurable and calibrated from empirical validation datasets, with `0.80` and `0.20` established as baseline starting values only.

### Cryptographic Session Binding (Keystore)
*   **FR-CRY-1:** The system SHALL perform secure, on-device cryptographic signing of the final VKYC session transcript.
*   **FR-CRY-2:** Cryptographic signing keys SHALL be stored inside and operated within the hardware-backed secure key manager of the device where hardware support permits. **[Requires Device Test]**
*   **FR-CRY-3:** The signed transcript payload SHALL contain the session ID, secure nonce, challenge seed hash, final decision, confidence score, rPPG signal quality metrics, model version, protocol version, and timestamp.
*   **FR-CRY-4:** The system SHALL NOT use custom-designed cryptographic algorithms or store private keys in unprotected, ordinary application storage.

### Transport
*   **FR-TR-1:** The system SHALL support local, peer-to-peer Wi-Fi as the primary transmission medium to transfer the cryptographically signed session transcript to the verifier.
*   **FR-TR-2:** The system SHALL support generating a QR-code representation of the signed transcript payload on the device screen as a fallback transmission channel.
*   **FR-TR-3:** The data transport pipeline SHALL operate completely offline without dependencies on external internet connection, cellular networks, or centralized cloud servers.
*   **FR-TR-4:** The system SHALL NOT depend on the device clipboard for secure session transcript transfer.

### Core Result Verification
*   **FR-VER-1:** The standard PC-side verifier SHALL verify the cryptographic signature of the session transcript and display verified session details, audit features, and generate an offline verification receipt.
*   **FR-VER-2:** The core result verification path SHALL run as a standalone PC application and SHALL NOT depend on vendor-specific screen sharing, PC-mobile integration suites, or proprietary connectivity kits being present.
*   **FR-VER-3:** **[Optional/TBD]** If a vendor-specific mobile-to-PC integration suite (e.g., Office Kit) is present, the verifier may support it as an optional, additive transport layer, but it SHALL NOT replace or compromise the baseline standalone verifier path.

### UI Transparency
*   **FR-UI-1:** The on-device user interface SHALL display real-time, user-readable progress states, including session status, challenge completion status, and signal quality warnings.
*   **FR-UI-2:** If a session results in a SPOOF or UNCERTAIN decision, the UI SHALL display a clear, concise visual explanation indicating which security gate failed (e.g., optical reflection mismatch, behavioral response timeout, or low rPPG signal quality).
*   **FR-UI-3:** The user interface SHALL NOT expose sensitive cryptographic material, private keys, or raw intermediate biometric templates.

---

## 3. Non-Functional Requirements

*   **NFR-OFF-1 (Offline-First):** The entire mobile capture, feature extraction, ML inference, and cryptographic signing pipeline SHALL run completely offline. No network requests to external servers or cloud services are permitted during execution.
*   **NFR-LAT-1 (On-Device Inference Latency):** The local ML fusion inference execution time SHALL be measured directly on the iQOO 15 hardware target. Target latency performance constraints must be established from empirical measurements rather than assumed. **[Requires Device Test]**
*   **NFR-MEM-1 (On-Device Memory & Power):** The system's memory footprint, CPU utilization, battery consumption, and thermal behavior during a standard VKYC session SHALL be profiled and logged on the target device. Performance limits must be calibrated on-device. **[Requires Device Test]**
*   **NFR-EVAL-1 (Subject-Independent Evaluation):** All machine learning components evaluated during system development SHALL use strict subject-independent data splits (e.g., GroupShuffleSplit on subject identifier), ensuring no session data from the same subject is present in both training and test sets.
*   **NFR-MET-1 (Metrics Integrity):** The system SHALL report actual, measured performance metrics (such as FAR, FRR, ROC-AUC, and latency). The fabrication of biometric performance metrics, feature importance values, or training data is strictly prohibited.
*   **NFR-PRV-1 (Privacy Minimization):** The system SHALL prioritize privacy by retaining only the derived numerical features, face embeddings, and cryptographic session transcripts. Storing or caching raw, unencrypted video or audio recordings on local device storage after session completion is prohibited, except for consent-gated development dataset collection.
*   **NFR-KEY-1 (Keystore Integrity):** The cryptographic private key used for session signing SHALL never be stored in plain text, hardcoded in source code, or written to unprotected flash storage.
*   **NFR-ENG-1 (Robustness & Error Handling):** The system SHALL gracefully handle exceptional conditions—including missing hardware sensors, missing face landmarks, multi-face contamination in single-user challenges, camera stream interruptions, and frame drops—without crashing or silently swallowing exceptions.

---

## 4. Prerequisites & Dependencies

### Hardware Prerequisites
*   **PR-HW-1:** One iQOO 15 smartphone target device, utilized for primary capture, challenge display, local DSP feature extraction, ML fusion, and cryptographic signing.
*   **PR-HW-2:** One secondary target device (mobile phone, tablet, or monitor) to act as the second subject or trusted participant interface during multi-person co-presence validation testing.
*   **PR-HW-3:** A standard PC to execute the standalone baseline verifier.

### Pre-Implementation Validation
*   **PR-VAL-1 (Recommended / Requires Verification):** Before finalizing the challenge engine parameters, pre-hackathon trials must confirm that the optical challenge stimulus (evaluating multiple screen brightness increments $+10\%$, $+25\%$, and $+50\%$, and duration intervals 100ms, 250ms, and 500ms) produces a measurable, statistically significant facial reflection change above ambient noise and camera sensor gain fluctuations. **[Requires Device Test]**

### Security Validation Dataset Needs
*   **PR-DAT-1:** A security-validation dataset is required to calibrate decision thresholds and measure liveness performance. This validation set SHALL contain data collected from 10–20 unique subjects, with multiple genuine sessions per subject.
*   **PR-DAT-2:** The validation dataset SHALL include structured representation of the following attack categories to verify and report attack-specific False Acceptance Rates (FAR):
    1.  **Printed Photo Attack:** High-resolution printed portrait photographs of subjects.
    2.  **Phone Replay Attack:** Video playbacks of genuine subjects captured and replayed on a secondary smartphone screen.
    3.  **Laptop Replay Attack:** Video playbacks of genuine subjects captured and replayed on a laptop display.
    4.  **OLED Replay Attack:** Video playbacks of genuine subjects replayed on an OLED display.
    5.  **Two-Person Replay Attack:** Co-presence attacks utilizing pre-recorded synchronized video segments of two subjects.
*   **PR-DAT-3:** The validation dataset is strictly designated as offline performance-evaluation and threshold-calibration material; live presentation orchestration scripts or red-team demonstration procedures are out of scope for this document.

---

## 5. Out of Scope

The following components and capabilities are explicitly excluded from the EdgePPG system scope:
1.  **Custom Biometric Primitive Models:** Developing or training custom deep learning models for face detection, face recognition/embedding, gaze estimation, or hand landmark detection is out of scope. The system must rely on pretrained capabilites.
2.  **Custom Deep rPPG Networks:** Training deep neural networks for end-to-end photoplethysmography extraction is prohibited. The rPPG pipeline must utilize classical signal processing (POS/chrominance) on engineered ROIs.
3.  **End-to-End Deep Liveness Networks:** Any end-to-end deep neural network that bypasses the engineered feature pipeline to predict liveness directly from raw video feeds is strictly out of scope.
4.  **Custom Deepfake Detectors:** Developing or training custom deep learning classifiers specifically targeting generative deepfakes or face-swaps.
5.  **Distributed Ledger & Web3 Tech:** Integration of blockchains, non-fungible tokens (NFTs), or decentralized identity models.
6.  **Unnecessary Network Architecture:** External web microservices, cloud-based AI endpoints, remote databases, or external communication backends.
7.  **Absolute Attack Prevention:** Full, guaranteed defense against advanced hardware-level attacks, physical camera pipeline injection, live-video relay attacks, or fully compromised operating system roots. EdgePPG is designed as a software-level risk-reduction protocol and does not claim to solve low-level capture-path tampering.
8.  **Demo & Red-Team Choreography:** Live demonstration schedules, presentation timing, red-team attack staging guidelines, and slide decks are out of scope for this specification and belong in separate demonstration documents.

---

## 6. Threat Model Summary

*The following summarizes the target threat vectors. Full details, mitigation mappings, and vulnerability metrics are deferred to `docs/threat_model.md`.*

| Threat / Attack Class | Primary System Treatment (WHAT) | Residual Risk & Known Limitations |
| :--- | :--- | :--- |
| **Printed Photo / Static Image** | Detection of absent physiological signals (rPPG) and lack of behavioral response (gaze/head movements). | High-quality 3D masks or facial movement simulation during presentation may reduce signal contrast; effectiveness must be verified via validation trials. |
| **Basic Video Replay** | Dynamic, randomized optical screen challenge correlation and gaze tracking verification. | High-fidelity screen replays with correct temporal synchronization; mitigated strictly by randomized sequence unpredictability. |
| **Pre-recorded Genuine-Face Replay** | Verification of real-time correlation between randomized optical screen stimulus and face reflections. | If the adversary pre-records the subject under identical randomized screen challenges; mitigated by fresh per-session cryptographic seeds. |
| **OLED / High-Quality Display Replay** | Combined evaluation of optical reflection response, multi-ROI rPPG consistency, and gaze alignment. | High-luminance displays matching physical reflection properties; must be evaluated experimentally during validation. |
| **Multi-Person Co-Presence Replay** | Verification of independent participant challenges and cross-person temporal and spatial interaction sequences. | Extremely coordinated multi-screen playbacks or physical co-conspirators; mitigated by ordering verification. |
| **Poor Lighting / Heavy Motion** | Quality gate detection leading to controlled segment retry or UNCERTAIN gate decision. | Extreme environment noise may increase False Rejection Rates (FRR) by forcing sessions to UNCERTAIN status. |
| **Tampered Result Payload / Receipt** | Cryptographically signed session transcript using secure on-device hardware keystore. | Host device root compromise allowing modification of intermediate features before signing; out of scope. |
| **Live Relay / Virtual Camera Injection** | Out of Scope. System assumes secure operating system capture path. | A compromised capture path can inject arbitrary synthetic frames; requires hardware-attested capture paths. |

*Note: The effectiveness of each target mitigation MUST be empirically verified via the validation matrix and performance trials; it cannot be assumed on design intent alone.*

---

## 7. Success Criteria

*Performance evaluation and acceptance testing SHALL be measured using the following criteria. Biometric values must be reported directly from real-world trials on the validation dataset.*

### Functional Success Criteria
*   **SC-FUNC-1:** On-device camera capture, real-time face detection, and multi-ROI tracking execute concurrently without pipeline crashes.
*   **SC-FUNC-2:** Gaze estimation, head movement estimation, and gesture detection successfully classify user movements against 100% of generated active challenge instructions.
*   **SC-FUNC-3:** The challenge engine generates a cryptographically unpredictable sequence for every session, with zero duplicate sequences recorded across 100 consecutive trials.
*   **SC-FUNC-4:** The on-device UI correctly displays real-time quality warnings and, in the event of failure, provides the correct visual indicator explaining the failing gate.

### Security Success Criteria
*   **SC-SEC-1:** The security decision gates successfully output UNCERTAIN when evaluated against genuine subjects under poor lighting (less than 10 lux) or high motion (exceeding 30 degrees per second head rotation), rather than outputting SPOOF.
*   **SC-SEC-2:** The PC-side verifier successfully parses, verifies the signature of, and displays the details of authentic session transcripts, and rejects 100% of manually modified or unsigned transcripts.
*   **SC-SEC-3:** Cryptographic key generation and session transcript signing are executed using the device's hardware-backed key manager. **[Requires Device Test]**

### ML & Performance Success Criteria
*   **SC-ML-1:** Machine learning models evaluated during system development report actual, un-fabricated metrics including ROC-AUC, F1-Score, aggregate False Acceptance Rate (FAR), and False Rejection Rate (FRR) on the validation dataset.
*   **SC-ML-2:** The system reports attack-specific False Acceptance Rates (FAR) specifically calculated and documented against the following validation trials:
    *   Printed Photo Attack FAR
    *   Phone Replay Attack FAR
    *   Laptop Replay Attack FAR
    *   OLED Replay Attack FAR
    *   Two-Person Replay Attack FAR

---

## 8. Open Questions & Contradictions Flagged

### Identified Contradictions in Source Documentation
1.  **Mandatory vs. Optional Behavioral Challenges:** The *Master Engineering Instructions* establish eye gaze tracking, head movement, and hand gesture challenges as core primary objectives. However, the *Final Architecture & Security/Validation Plan v2* lists only head-motion tracking as an active challenge, omitting gaze and hand gestures from the core architecture. This specification includes all three as functional requirements (`FR-BEH-1`, `FR-BEH-3`, `FR-BEH-5`) but tags their implementation viability on target hardware as **[Requires Device Test]**.
2.  **Multi-Person Requirement:** The *Master Engineering Instructions* describe a multi-person co-presence and cross-person interaction protocol as a core feature. The *Final Architecture & Security/Validation Plan v2* omits multi-person features entirely from its system architecture layer and validation matrix. This specification retains the multi-person capabilities in the functional requirements (`FR-MP-1` to `FR-MP-3`) but marks them as subject to device and capture-setup validation.

### Open Decisions & Device Uncertainties
1.  **iQOO 15 Device Capabilities:** Precise support for hardware-backed keystore integration, high-precision sensor timestamps, and direct, fine-grained exposure/white-balance controls on the target iQOO 15 camera interface remains unverified and **[Requires Device Test]**.
2.  **Optical Challenge Measurability:** The precise luminance, color contrast levels, and duration limits required to trigger a measurable skin reflection above ambient venue lighting noise on the iQOO 15 are unresolved and **[Requires Device Test]**.
3.  **ML Model Selection:** The specific lightweight classifier architecture to execute on the numerical session feature vector (e.g., Random Forest vs. XGBoost vs. MLP) is unresolved and will be determined based on measured performance and model size.
4.  **Office Kit Availability:** The availability, OS version compatibility, and API footprint of a vendor-provided PC-mobile integration suite (Office Kit) are TBD, making the feature strictly optional and additive (`FR-VER-3`).
5.  **Calibration Thresholds:** The exact numerical values for `LIVE_THRESHOLD` and `SPOOF_THRESHOLD` are unresolved and can only be set after empirical testing on the validation dataset.
