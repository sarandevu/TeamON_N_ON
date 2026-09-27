# Security Policy

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🔒 Threat Model & Security Architecture

EdgePPG operates on a zero-trust, privacy-first VKYC model:
1. **On-Device Biometrics**: Raw camera feeds and biometric templates never leave the Android device.
2. **Cryptographic Attestation**: The decision transcript is signed using hardware-backed keys (`AndroidKeyStore` SECP256R1 ECDSA).
3. **Replay & Freshness Protection**: Each session uses a 5-minute freshness window bound to a cryptographic challenge nonce and UTC timestamp.
4. **Physical & Screen Spoof Defense**: Multi-ROI physiological rPPG phase analysis and active challenge-response synchronization mitigate presentation attacks.

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability, cryptographic bypass, or replay exploit:
1. **Do NOT open a public GitHub issue.**
2. Send a detailed report to the security team with:
   - Description of the vulnerability.
   - Steps to reproduce or proof-of-concept.
   - Device model, Android OS version, and verifier runtime environment.
3. We will acknowledge receipt within 48 hours and provide a coordinated disclosure timeline.
