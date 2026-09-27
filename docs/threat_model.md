# EdgePPG — Threat Model

This document catalogues the threats the system is designed to
address, the actual mitigations in the source code (Stage 1–15),
and the residual risks. It is grounded in `Requirements.md §6`,
`Architecture.md §11`, and the implemented behaviour observed in
the source tree. **It is not** a security certification; it is a
record of what the design and implementation actually cover.

**Claim discipline:** Per `EDGEPPG_MASTER_INSTRUCTIONS.md §4`, the
system is **not** "impossible to spoof", **not** "deepfake-proof",
**not** "guaranteed physical presence". Where a mitigation is
partial or pending device verification, this document says so.

---

## 1. Threat inventory

The threats below are the ones called out in `Requirements.md §6`
plus the implementation gaps surfaced by the source audit.

### T1 — Printed photo (static image) replay

**Description:** The attacker holds a high-resolution printed photo
of an authorised subject in front of the front camera. The camera
sees a face mesh; the face mesh passes quality gates; the
behavioural challenges may be matched if the attacker can reproduce
a frozen pose that satisfies the geometric matcher.

**Mitigations in the source:**
- **rPPG pulse check (Architecture §4.5, FR-RPPG-*).** A printed
  photo has no pulse. `rppg/RppgClient.kt` extracts the pulse via
  POS → bandpass → FFT → SNR; on a static image the SNR is below
  the `SNR_SPOOF = 0.12f` threshold documented in the file
  (RppgClient companion object).
- **Cross-ROI Pearson correlation (Architecture §4.5, FR-RPPG-3).**
  `RppgClient.computeWindow()` returns `roiCorr`. A flat photo
  yields near-zero cross-correlation; the documented
  `ROI_CORR_SPOOF = 0.05f` threshold catches it.
- **Optical flash correlation (Architecture §4.6, FR-OPT-2/3).**
  The renderer (`optical/OpticalFlashOverlay.kt`) projects a
  randomised colour flash; the verifier-side correlation between
  expected and observed face-reflectance is `[Requires Device Test]`
  per `Requirements §PR-VAL-1` and is **not** end-to-end implemented
  in the hackathon build.
- **Motion / blink challenge (Architecture §3, FR-BEH-*).**
  Printed photos don't blink on cue. The behavioural runner
  (`behavior/BehaviourRunner.kt`) emits `BehavioralOutcome.TIMEOUT`
  or `WRONG` when no motion is detected.

**Residual risk:** with no trained ML model (the runtime's
`NaNFallbackMlClient` returns NaN for `P(LIVE)`), the decision engine
routes to `UNCERTAIN` rather than `SPOOF` for any case where
integrity_ok but P_live is NaN — see the truth table in
`tests/test_decision_truth_table.py`. This is the **documented
contract** of the placeholder model, not a bug.

**Status:** Source-mitigated. Device-verified effectiveness is
**pending** (`docs/demo_run.md` §3.2).

### T2 — Phone / tablet replay

**Description:** A second device plays a video of a genuine VKYC
session. The video includes face mesh-detectable motion and the
camera re-detects the face.

**Mitigations in the source:**
- **Optical flash correlation (FR-OPT-2/3).** A replay device
  produces a phase-locked but offset reflectance signal; the
  optical response score should be low. Implementation deferred
  per the hackathon scope.
- **Fresh per-session cryptographic seed (FR-SESS-1, FR-CRYPTO-1).**
  The challenge list and optical-flash sequence are seeded by
  `NonceGenerator.seedHex()` per session, so a captured video
  cannot be replayed against a fresh challenge. `ChallengeEngine.kt`
  derives the applicant + trusted streams from the seed with
  distinct salts. This is **enforced** in `tests/test_challenge_engine.py`.
- **Behavioural timeout (FR-BEH-*).** With the hackathon's
  timeout-based matcher, a video CAN match (it shows the same
  motion pattern). The architecture's full correlation is `[Requires
  Device Test]`.

**Residual risk:** without the trained ML model and the
optical-flash correlation stage, the demo **cannot** distinguish
"video playing the same motion" from "real person responding on
cue". Recorded as a known limitation in `docs/demo_run.md` §3.3.

**Status:** Partially source-mitigated. **Pending** device
verification.

### T3 — Replay with synchronized timing (advanced)

**Description:** A more capable adversary captures a video of a
genuine session and synchronizes their replay device's clock with
the original session.

**Mitigations in the source:**
- **Fresh per-session nonce + 5-minute freshness window.** The
  envelope's `timestamp_ms` is wall-clock; the verifier rejects
  anything older than 5 minutes (`IntegrityManager.FRESH_MS`,
  `verifier/verify.py`). A replay attempt after the freshness
  window expires is rejected at the verifier. Within the window,
  this mitigation does not apply.

**Residual risk:** Within the freshness window, a synchronized
replay is not distinguishable from a live session by the current
build. Out-of-window replays are blocked.

**Status:** Partial. **Pending** trained model + cross-session
correlation analysis.

### T4 — Multi-person / multi-track confusion

**Description:** The applicant holds a printed photo while a
trusted-participant (or a video of one) appears separately.

**Mitigations in the source:**
- **Multi-face tracker (Stage 8).** `multi/MultiFaceTracker.kt`
  detects up to 2 simultaneous face tracks and keeps stable IDs
  via IoU + centroid hysteresis. Each track is independent.
- **Independent challenge streams.** `ChallengeEngine.generateApplicant`
  and `generateTrusted` produce different lists with different
  salts; the architectural `cross_person_*` features catch
  spatial / temporal desync.

**Residual risk:** with the hackathon single-participant scope, the
multi-person features are NaN in `RowAssembler.Inputs` — the row
assembler passes them through as the documented "missing" sentinel.

**Status:** Partially source-mitigated. The multi-person
desync-detection is `[Requires Device Test]` per `Requirements §8`.

### T5 — Hostile OS / kernel-level capture-path tampering

**Description:** A rooted phone or compromised OS re-routes the
camera through a different pipeline, replacing frames with
arbitrary data.

**Mitigations:**
- **None in the source.** This is documented in `Requirements §6`
  as out-of-scope: "Live relay / virtual camera injection —
  Out of Scope. System assumes secure operating system capture
  path."
- The hackathon build does not detect or defend against this.

**Status:** **Not mitigated.** Documented as a known limitation.

### T6 — Keystore exfiltration

**Description:** An attacker extracts the `edgeppg_device_key_v2`
private key from the phone.

**Mitigations:**
- **AndroidKeyStore non-exportable key (NFR-KEY-1).** The key is
  generated in the AndroidKeyStore and cannot be exported in
  plaintext. `IntegrityManager.ensureKey()` and `exportPublicKeyB64()`
  return the public half only; the private half stays inside the
  TEE/StrongBox.
- **StrongBox preference (Architecture §12).** `IntegrityManager`
  requests StrongBox when available (`setIsStrongBoxBacked(true)`)
  and silently falls back to TEE if the device doesn't expose it.

**Residual risk:** A rooted attacker with kernel-level access can
defeat the hardware-backed store on most devices. Per `Requirements
§6`: "Host device root compromise allowing modification of
intermediate features before signing; out of scope."

**Status:** Hardware-backed where available. **Not** defended
against a fully compromised OS.

### T7 — Replay / nonce-reuse

**Description:** An attacker captures a signed envelope and
re-submits it.

**Mitigations:**
- **Per-session nonce LRU.** `verifier/verify.py` keeps a
  per-process LRU of seen nonces within the 5-minute freshness
  window and rejects duplicates with `replay-nonce`.
- **Per-session fresh nonce + 5-minute freshness window.** The
  envelope's `timestamp_ms` + `nonce` together ensure any
  resubmission of the same envelope is rejected.

**Status:** Source-mitigated (`verifier/verify.py` lines
`seenNonces` + `FRESH_MS`).

### T8 — Receipt tampering / receipt forgery

**Description:** An attacker modifies a verifier receipt.

**Mitigations:**
- **Receipts are not authoritative.** Per `Requirements §FR-VER-1`
  the verifier produces a display + audit log; the PC's signature
  is on the envelope, not on the receipt. The hackathon build
  doesn't include a signed receipt — that's `Requirements §FR-VER-3`
  ("Operator-side, Office Kit, optional").

**Status:** Receipts are unsigned audit artefacts. Not a security
boundary.

### T9 — Verifier-side key compromise

**Description:** An attacker steals the PC-side pubkey.b64
(`verifier/pubkey.b64`) and replaces it with their own.

**Mitigations:**
- **Out-of-band provisioning.** `docs/payload_format.md §6`
  documents the one-time provisioning step: the operator pastes
  `IntegrityManager.exportPublicKeyB64()` into the laptop's
  `verifier/pubkey.b64`. There is no network sync; an attacker
  who can write to `verifier/pubkey.b64` has already compromised
  the operator's laptop.
- **Verdict display.** The verifier's dashboard shows the
  decision; if an attacker substitutes their own key, every
  genuine session would be rejected as a bad-signature, and
  every attacker-crafted envelope would verify as LIVE. The
  attack is detectable by the operator (the genuine subjects would
  not pass).

**Status:** Detection only; no prevention. Standard PKI assumption.

---

## 2. Mitigations NOT in the current implementation

The following `Requirements §6` rows are partially or not
implemented in the current build:

| Row | Status | Why |
| --- | --- | --- |
| **Poor Lighting / Heavy Motion** | Source-mitigated via `quality/QualityGate.kt` (`GateDecision.FAIL` on low FPS / AWB / contamination). UNCERTAIN is the documented route per `Architecture §8`. | Quality gate works; routing tested in `tests/test_decision_truth_table.py`. |
| **Tampered Result Payload / Receipt** | Receipt is unsigned (T8). Envelope payload is signed (Stage 12 `IntegrityManager.sign`). | Receipt signing is an Office Kit / verifier-side concern (Stage 16 Task 4). |
| **Live Relay / Virtual Camera Injection** | **Not mitigated.** Documented as out of scope. | Per `Requirements §6`. |

---

## 3. What this document is NOT

- Not a Common Criteria evaluation.
- Not a FIPS 140-3 statement.
- Not a penetration-test report — the implementer has not run
  one.
- Not a guarantee of any kind (`EDGEPPG_MASTER_INSTRUCTIONS.md §4`).

This document is a **design inventory** of the threat surface and
the source-level mitigations, written before the device run so
the operator's `docs/demo_run.md` §3 runs have a checklist.
