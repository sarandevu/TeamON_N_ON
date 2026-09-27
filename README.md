# EdgePPG — VKYC Assurance & Verification Gateway

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Android](https://img.shields.io/badge/Android-10%2B%20(API%2029%2B)-green.svg)](android/)
[![Kotlin](https://img.shields.io/badge/Kotlin-1.9%2B-purple.svg)](android/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-yellow.svg)](verifier/)

**EdgePPG** is an on-device Video KYC (VKYC) liveness assurance and cryptographic attestation engine. It combines real-time remote photoplethysmography (rPPG), active optical/behavioral challenges, camera sensor quality gating, and hardware-backed cryptographic signing (`AndroidKeyStore` SECP256R1) to provide tamper-evident verification receipts without transmitting raw biometric video to the cloud.

---

## 🏗️ System Architecture

```
                                  EDGEPPG PIPELINE
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                                                                             │
   │  ┌────────────────┐     ┌────────────────┐     ┌─────────────────────────┐  │
   │  │ Camera Capture │ ──> │ Face ROI &     │ ──> │ rPPG POS DSP            │  │
   │  │ (30 FPS Lock)  │     │ Mesh Tracking  │     │ (Biquad + FFT + Corr)   │  │
   │  └────────────────┘     └────────────────┘     └─────────────────────────┘  │
   │                                                             │               │
   │  ┌────────────────┐     ┌────────────────┐                  ▼               │
   │  │ Sensor Quality │     │ Active Gaze &  │     ┌─────────────────────────┐  │
   │  │ Gate (AE/AWB)  │     │ Head Challenge │ ──> │ Multi-Modal Decision     │  │
   │  └────────────────┘     └────────────────┘     │ Engine (LIVE/SPOOF/UNC) │  │
   │                                                └─────────────────────────┘  │
   │                                                             │               │
   │  ┌────────────────────────────────────────────────────────┐ │               │
   │  │ AndroidKeyStore (SECP256R1 Hardware-Signed Envelope)   │ ◄               │
   │  └────────────────────────────────────────────────────────┘                 │
   │                               │                                             │
   └───────────────────────────────┼─────────────────────────────────────────────┘
                                   │ HTTP POST /api/result
                                   ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                          PC VERIFIER & GATEWAY NODE                         │
   │  - Cryptographic Signature & Nonce Verification                             │
   │  - Real-Time Live Queue & Operator Console (Session / Call ID Routing)      │
   │  - 28-Feature Schema Compliance & Audit Ledger                              │
   │  - Offline Tamper-Evident Verification Receipts                             │
   └─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Capabilities

### 1. Physiological rPPG Pulse Extraction
- **Plane-Orthogonal-to-Skin (POS) Algorithm**: Extracts microvascular blood volume pulse (BVP) signals from facial skin ROIs (forehead, left/right cheeks).
- **Dual-Band Spectral Analysis**: Radix-2 FFT and biquad Butterworth filtering isolate pulse harmonics between $0.75\,\text{Hz} - 3.5\,\text{Hz}$ ($45 - 210\,\text{BPM}$).
- **Cross-ROI Phase Correlation**: Validates cross-region Pearson correlation ($r > 0.35$). Synthetic screens and printed photos exhibit zero microvascular phase sync, reliably triggering `SPOOF` detection.

### 2. Active Behavioral & Optical Challenges
- **Deterministic Challenge Generation**: Seed-derived pseudo-random sequences (Gaze shifts, Head tilts, Hand gestures, Stillness intervals).
- **Temporal Reflection Analysis**: Measures facial reflectance modulation under controlled screen flash stimuli to detect digital projection surfaces.

### 3. Hardware-Enclave Integrity
- **On-Device Cryptographic Attestation**: Verification transcripts are canonicalized and signed inside the `AndroidKeyStore` using NIST P-256 (`SHA256withECDSA`).
- **Replay Protection**: Nonce-bound 5-minute freshness window prevents recording replays and man-in-the-middle tampering.

### 4. Zero-Cloud Privacy Model
- Raw video frames never leave the device. Only canonicalized telemetry and cryptographic signatures are transmitted over local Wi-Fi or QR fallback.

---

## 🚀 Quick Start Guide

### Prerequisites
- **Android Device**: Android 10+ (API 29+) with front camera.
- **Development Workstation**: Windows, macOS, or Linux with Python 3.10+ and JDK 17+.

---

### Step 1: Start the PC Verifier Gateway

```powershell
# In the repository root:
.\.venv\Scripts\python.exe -m verifier.server --port 8080
```
Open **`http://localhost:8080/`** in your web browser to view the Verification Dashboard.

---

### Step 2: Build & Install the Android Application

```powershell
cd android
.\gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

---

### Step 3: Run Live Verification

1. **On the PC Dashboard**:
   - Tap **⚡ Autofill Sample** (populates Session `001`, Applicant `User 1`, Reference `User1`).
   - Click **+ Schedule Session**.
2. **On the Mobile App**:
   - Verify defaults are set to Applicant `User1` and Session `001`.
   - Tap **`START / JOIN VERIFICATION ➔`**.
   - Align face in preview. Complete active prompts (gaze/head movement).
   - Once completed, the phone displays **VERIFIED LIVE APPLICANT** (or **SYNTHETIC SPOOF DETECTED** if presenting a screen/photo).
   - The PC Dashboard updates in real time with the verified cryptographic receipt.

---

## 🧪 Automated Attack Test Harness

The PC Verifier includes an integrated Security Test Harness simulating physical and digital presentation attacks:

```powershell
# Run the test suite:
.\.venv\Scripts\python.exe -m unittest discover verifier/tests
```

Available Scenarios in Dashboard Test Lab:
- **Genuine Live Subject**: Valid rPPG pulse ($SNR \ge 0.42$, $ROI \ge 0.52$), passes all gates $\rightarrow$ `LIVE`.
- **Printed Photo Attack**: Static reflection ($SNR = 0.04$, $ROI = 0.02$), no pulse $\rightarrow$ `SPOOF`.
- **Screen Video Replay**: Display flicker ($SNR = 0.08$, $ROI = 0.06$) $\rightarrow$ `SPOOF`.
- **Signature Tampering**: Corrupted envelope signature $\rightarrow$ `INVALID`.
- **Nonce Replay**: Replayed session nonce past freshness window $\rightarrow$ `REPLAY REJECTED`.

---

## 📁 Repository Structure

```
EdgePPG/
├── android/                   # Android native application (Kotlin)
│   └── app/src/main/kotlin/com/edgeppg/app/
│       ├── behavior/          # Gaze, head pose, and hand gesture estimators
│       ├── capture/           # CameraX session, AE/AWB lock, face ROI tracker
│       ├── challenge/         # Deterministic challenge engine & state machine
│       ├── features/          # 28-feature schema & row assembler
│       ├── gates/             # DecisionEngine & threshold evaluator
│       ├── integrity/         # AndroidKeyStore ECDSA signer & transcript builder
│       ├── optical/           # Screen flash challenge overlay
│       ├── quality/           # Exposure, AWB, motion contamination gates
│       ├── rppg/              # POS DSP, biquad bandpass filter, FFT
│       ├── session/           # SessionController & CallController
│       └── transport/         # Local Wi-Fi & QR code fallback transport
├── verifier/                  # Python PC verifier gateway node
│   ├── calls.py               # Session scheduling & join handling
│   ├── canonical.py           # Canonical JSON serialization
│   ├── receipt.py             # Tamper-evident receipt generator
│   ├── server.py              # HTTP dashboard & verification gateway
│   ├── test_harness.py        # Automated attack scenario engine
│   └── verify.py              # ECDSA signature & freshness validator
├── models/                    # ML model manifests and calibration metadata
├── docs/                      # Technical specifications & architecture blueprints
└── requirements.txt           # Python dependencies
```

---

## 📜 Compliance & Security Notice

EdgePPG enforces strict claim discipline:
- Cryptographic signatures guarantee authenticity and freshness of the decision transcript.
- Spoof detection relies on physiological pulse dynamics and multi-cue consistency.
- No raw biometric identifiers or video recordings are stored or transmitted.
