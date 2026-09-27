# Changelog

All notable changes to the **EdgePPG** project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-27

### Added
- **Physiological rPPG Engine**: Pure Kotlin POS DSP, radix-2 FFT spectral analysis, biquad Butterworth filtering, and multi-ROI Pearson correlation.
- **Decision Engine & Quality Gates**: 28-feature schema compliance, exposure/AWB stability gates, and physiological spoof detection fallback.
- **Hardware Cryptographic Attestation**: `AndroidKeyStore` SECP256R1 ECDSA transcript signing and canonical payload serialization.
- **PC Verifier Gateway**: Local HTTP server with real-time verification dashboard, live queue management, and offline tamper-evident receipt generation.
- **Attack Scenario Test Harness**: Built-in test suite evaluating genuine subjects, printed photos, video replays, and signature tampering.
- **Simplified Session Orchestration**: Short call identifiers (`001`, `User 1`), sample autofill, and automatic scheduled call matching.
- **Comprehensive Documentation**: Complete `README.md`, `WALKTHROUGH.md`, `CONTRIBUTING.md`, `SECURITY.md`, and CI workflow.
