# EdgePPG UI Changes & Challenge Pacing Documentation

**Date:** 2026-09-27  
**Scope:** Android Applicant UI, PC Verifier Dashboard, and Challenge Transition Timing  
**Related Specs:** `docs/vkyc-call-dashboard-spec.md`, `docs/Requirements.md`, `docs/Architecture.md`, `docs/final_integration_status.md`

---

## 1. Overview

This document specifies the user interface changes, visual design enhancements, and execution flow fixes implemented for both the **PC Verifier Dashboard** and the **Android Mobile App**, including:
1. Complete visual aesthetic overhaul on both sides (Fintech/Cyber-assurance dark design system).
2. Resolution of the challenge timing error where challenges transitioned prematurely or too rapidly.
3. Network security and ECDSA hardware key provisioning.

---

## 2. PC Verifier Dashboard Visual Overhaul

The PC Verifier runs as a Python HTTP service (`verifier/server.py`) accessible on `http://127.0.0.1:8080/`.

### 2.1 Professional VKYC Banking & Assurance Console Upgrade
- **Design Philosophy:** Upgraded from an administrative developer dashboard into an executive-grade, tier-1 fintech/banking verification console (Stripe Identity / Socure / Jumio class) prioritizing instantaneous 2-to-3-second scanning, strong visual hierarchy, zero visual clutter, and strict fidelity to underlying cryptographic data.
- **Color Palette & Typography:**
  - **Background:** Deep space slate (`#080C14`) with ambient radial mesh of indigo (`#6366F1`) and cyan (`#06B6D4`).
  - **Header:** Sticky elevated console bar (`#0B111E`) with subtle border (`#1A2438`) and gradient brand emblem (`EP`).
  - **Surfaces & Cards:** Dark slate (`#111B2E`) with subtle borders (`#1E2D4A`) and hover depth transitions.
  - **Typography:** Google `Outfit` for headings and primary metrics; `JetBrains Mono` for cryptographic hashes, nonces, and session keys.
  - **Status Colors:** Emerald (`#10B981` / `#34D399`), Amber (`#F59E0B` / `#FBBF24`), Coral Red (`#EF4444` / `#F87171`), and Indigo (`#818CF8`).
- **Structured Visual Hierarchy:**
  1. **Applicant & Active Session Profile Card:**
     - Dynamic initials avatar badge, Applicant Name, Reference ID, Session ID, Scheduled Time, and `✓ Android Keystore Authenticated` security pill.
  2. **Hero Verification Attestation & Confidence Component:**
     - **Radial Confidence Progress Ring:** Native SVG circular progress ring (r=45, circumference 282.74) with smooth animated stroke offset reflecting the actual $P(\text{LIVE})$ evidence confidence (e.g. 92%, 87%, or 50% from verified receipt telemetry).
     - Sub-labels: Evidence Confidence, $P(\text{LIVE})$ badge, and Bank Verification Policy indicator (`Threshold ≥ 0.70`).
     - **Unmistakable Final Verdict Hero:** Large status pill (`LIVE APPLICANT`, `UNCERTAIN`, `SPOOF`, or `STANDBY`), prominent headline, descriptive rationale, timestamp, and receipt filename.
  3. **Operational Telemetry Matrix:**
     - 4 discrete node health indicators: Call State (`CONNECTED` / `COMPLETED`), Transport (`Direct HTTP / Wi-Fi`), Verification (`COMPLETED`), and Root Key (`secp256r1 Valid ✓`).
  4. **Evidence Modalities (4-Card Grid):**
     - **Face Spatial ROI:** Spatial correlation score (`roi_corr`), sync progress bar, and cheek/forehead perfusion agreement.
     - **rPPG Pulse Dynamics:** Real Heart Rate (`hr_bpm`), Signal-to-Noise Ratio (`snr`), Pulse Quality Index (`signal_quality`), and visual signal quality meter bar.
     - **Behavioral & Temporal:** Inference model version (`v2.1-edge`), anti-replay nonce validity check (`< 5m`).
     - **Interactive Challenge:** Active Challenge ID and prompt sequence execution status (`expected_seq`).
  5. **Security & Cryptographic Integrity Checklist:**
     - Visually quieter horizontal bar: `✓ Hardware Enclave Attested`, `✓ ECDSA P-256 Signature Valid`, `✓ Zero-Knowledge rPPG Stream`, `✓ Tamper-Evident Offline Receipt`.
  6. **Operations & Audit Console (Lower 2-Column Grid):**
     - **Left:** Session Scheduling (interactive form with "+ Schedule Session" & "⚡ Autofill Sample") + Live Verification Queue table with real-time status badges and operator actions.
     - **Right:** Decision & Audit Log table showing real-time timestamps, verdicts, session IDs, and receipts + Direct Intake (QR / Manual Fallback) textarea.

---

## 3. Android Mobile Dashboard Visual Overhaul

The Android application (`MainActivity.kt`) runs a single-activity architecture, cleanly separating the pre-session Call Dashboard and the Camera Verification Session.

### 3.1 Visual Design Enhancements
- **Native Programmatic Design System:** Built using custom `GradientDrawable` shape and gradient utilities without external heavy UI dependencies, preserving backward compatibility and zero bloat.
- **System Bar Integration:** Dark status bar and navigation bar styling (`#080C14`), with safe-inset top padding (`dp(68)`) clearing camera punch-holes and dynamic island cutouts.
- **Header Badges & Typography:**
  - Glowing security badge: `● HARDWARE SECURE ENCLAVE` (emerald green text and translucent pill border).
  - Title: `EdgePPG Identity` in bold 26sp white typography.
  - Subtitle: `Hardware-Signed Zero-Knowledge VKYC` in muted slate (`#94A3B8`).
- **Input Card Container:**
  - Deep slate card container (`#131B2E`) with rounded corners (20dp) and subtle border (`#23304E`).
  - **Call Identifier Input:** Monospace font with focus-activated glowing stroke (`#6366F1`), dark interior (`#0B101D`), and clear placeholder hints.
  - **Applicant Reference Input:** Matching styled input with clean label and glow transitions.
  - **Dynamic Call Status Banner:** Rounded status pill with state-dependent colors and icons:
    - `IDLE`: Blue banner (`ℹ️ Enter call credentials, then tap Join Call.`)
    - `SCHEDULED`: Amber banner (`⏳ Call <id> scheduled. Ready to join.`)
    - `JOINING`: Indigo banner (`🔄 Handshaking with verifier...`)
    - `CONNECTED`: Emerald banner (`✅ Session authorized! Starting verification...`)
    - `FAILED`: Red banner (`⚠️ Join failed: ...`)
  - **Gradient Join Button:** Gradient CTA (`#4F46E5` to `#7C3AED`) with bold white text `JOIN SECURE SESSION ➔` and disabled state styling.
- **Session HUD & Challenge Feedback:**
  - Frosted translucent glass HUD (`#EE0A0F1D`) with rounded corners (16dp) overlaid on the live CameraX preview.
  - Challenge cards formatted with large intuitive icons (`👁️ GAZE`, `👤 HEAD ROTATION`, `✋ GESTURE`, `⏱️ STILLNESS`, `⚡ OPTICAL PROBE`).
  - Post-session verdict cards:
    - `LIVE`: Emerald green badge card with `🛡️ VERIFIED LIVE APPLICANT`, hardware root of trust confirmation, and round-trip transport latency.
    - `SPOOF`: Crimson warning card with synthetic detection alerts.
    - `UNCERTAIN`: Amber cautionary card for insufficient lighting or motion.

---

## 4. Challenge Pacing & Rapid Transition Fix

### 4.1 Root Cause of the "Too Quick to Change Between Challenges" Error
1. **Premature Runner Execution:** Previously, `behaviourRunner?.start(challenges)` was invoked inside `startSession()` at the same time as `QUALITY_CHECK`. Because camera AE/AWB convergence can take up to 10 seconds, the challenge runner had already executed and timed out several challenges in the background before the applicant even saw the challenge screen.
2. **Zero Delay Between Challenges:** In `BehaviourRunner.kt`, the loop moved from one challenge to the next with 0ms delay as soon as an observation was emitted, leaving the user no time to comprehend the prompt or observe the feedback.
3. **Double Advance on Events:** Both `PromptShown` and `Observation` events triggered advance handlers, causing rapid skipping.

### 4.2 Fix Applied
1. **Deferred Challenge Runner Start:** In `MainActivity.kt`, `behaviourRunner?.start(challenges)` is now triggered **only** upon entering `SessionState.RANDOMIZED_CHALLENGE` (after quality gate and baseline capture complete).
2. **Inter-Challenge Transition Delay:** In `BehaviourRunner.kt`, a `delay(1200L)` is added between consecutive challenges.
3. **Visual Feedback on Observation:** During the 1.2-second transition window, the UI displays immediate feedback:
   ```
   Challenge N of Total
   Result: [✓ / —] OUTCOME
   Next challenge starting in 1 second…
   ```
   When the next challenge starts, `PromptShown` updates the prompt smoothly.

---

## 5. Network Security & Public Key Provisioning

1. **Cleartext Traffic Enabled:** Added `android:usesCleartextTraffic="true"` in `AndroidManifest.xml` to allow the local Wi-Fi / ADB reverse HTTP communication on port 8080 without Android 9+ security policy rejection.
2. **Multi-Target Transport Fallbacks:** Updated `LocalWifiTransport.kt` to check candidate loopback URLs (`127.0.0.1:8080` for ADB reverse, `172.20.10.3:8080` for local LAN, and `10.0.2.2:8080` for emulator) so testing works on physical devices and emulators seamlessly.
3. **Device Public Key Provisioning:** `IntegrityManager` now exports the hardware-backed ECDSA P-256 public key on app launch to `verifier/pubkey.b64`, enabling valid cryptographic verification and offline receipt generation.

---

## 6. Verification Status

- **PC Unit Tests:** 316 / 316 passing (`python -m tests.run_all_tests`).
- **Android JVM Unit Tests:** Passing (`.\gradlew.bat :app:testDebugUnitTest`).
- **Android APK Build:** Successful (`.\gradlew.bat assembleDebug`).
- **Device Verification:** Verified end-to-end on connected physical iQOO device (Model I2501). Call scheduling, waiting state, joining, camera session, challenge execution, cryptographic signing, verifier intake, and offline receipt writing all verified working.
