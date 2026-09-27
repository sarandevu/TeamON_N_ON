# EdgePPG VKYC Call Dashboard / Call Join Workflow Specification

**Version:** 1.0  
**Status:** Implementation-Ready Specification  
**Related Documents:** `docs/Architecture.md`, `docs/Requirements.md`, `docs/TechStack.md`, `docs/ANDROID_ENVIRONMENT.md`, `docs/Workflow.md`, `docs/transport-debugging-spec.md`

---

## 1. Purpose & Scope

This specification defines the **VKYC (Video KYC) Call Dashboard and Call Join Workflow** for both the Android applicant side and the PC verifier side. This is a **session/call orchestration layer** that sits *above* the existing EdgePPG verification pipeline — it does not replace or modify the verification pipeline, transport, ML model, security gates, or cryptographic signing.

**In Scope:**
- Android applicant dashboard: scheduled call display, Join Call action
- PC verifier dashboard: call scheduling, waiting state, applicant join handling
- Join Call command/event using existing `Transport` abstraction
- Integration with existing `SessionController` → verification pipeline → transcript signing
- Explicit state separation: Call State ≠ Transport State ≠ Verification State ≠ Verification Result

**Out of Scope:**
- Video conferencing, voice calling, or streaming infrastructure (no Zoom/Meet competitor)
- WebRTC, SIP, or any real-time media transport
- Modifying the 28-feature schema, ML model, security gates, or transcript signing
- Creating a second transport — must reuse existing `LocalWifiTransport` / `QrFallbackTransport`
- Any changes to `IntegrityManager`, `DecisionEngine`, `FeatureSchema`, canonical JSON
- Biometric capture during the "call" — the verification pipeline *is* the biometric capture

---

## 2. Background & Current State

### 2.1 What Exists Today

| Component | Status | Location |
|-----------|--------|----------|
| Verification Pipeline | Complete (Stages 1–15) | `SessionController`, `ChallengeEngine`, `DecisionEngine`, etc. |
| Transport Layer | Complete (Stage 13) | `Transport` interface, `LocalWifiTransport`, `QrFallbackTransport` |
| PC Verifier | Baseline complete | `verifier/server.py` — HTTP `POST /api/result`, HTML dashboard at `/` |
| Session Orchestration | Complete | `SessionController` drives CAPTURE → QUALITY → BASELINE → CHALLENGE → PROCESSING → DONE |
| Cryptographic Signing | Complete | `IntegrityManager` (Android Keystore ECDSA P-256) |
| UI | Basic (MainActivity) | Renders session state via `SessionController.state` StateFlow |

### 2.2 What Does NOT Exist

- **No call/scheduling concept** — sessions start immediately on app launch
- **No "Join Call" action** — no control message from applicant to verifier
- **No call state machine** — no `SCHEDULED`, `WAITING`, `JOINING`, `CONNECTED`, `COMPLETED`
- **No PC-side call dashboard** — `server.py` only shows verification results after they arrive
- **No applicant dashboard** — `MainActivity` goes straight to camera permission → session

### 2.3 Intended Workflow (High-Level)

```
PC/Bank → Schedule VKYC Call → Android Applicant Dashboard → Applicant sees scheduled call →
Applicant presses JOIN CALL → Join Call command/event → Existing EdgePPG transport →
PC receives Join Call → PC dashboard becomes Connected/Ready → Existing EdgePPG verification starts →
Existing verification pipeline → LIVE/SPOOF/UNCERTAIN → Existing transcript/signature flow
```

---

## 3. Non-Goals (Explicitly Prohibited)

- ❌ **No video/voice streaming** — this is not a conferencing system
- ❌ **No WebRTC, SIP, TURN, STUN, media servers** — unless already in repo (they are not)
- ❌ **No second transport** — must reuse `Transport` interface and existing implementations
- ❌ **No new HTTP stack, no new protocol, no parallel session architecture**
- ❌ **No ML/security/schema changes** — the 28-feature schema, frozen model, gates, LIVE/SPOOF/UNCERTAIN are immutable
- ❌ **No collapsing of states** — Call State ≠ Verification Result (see §5)
- ❌ **No fabricating verification results** in Join Call message

---

## 4. Existing Architecture Dependencies

| Component | File | Role in This Spec |
|-----------|------|-------------------|
| Transport Interface | `android/app/src/main/kotlin/com/edgeppg/app/transport/Transport.kt` | Abstraction for Join Call message |
| LocalWifiTransport | `android/app/src/main/kotlin/com/edgeppg/app/transport/LocalWifiTransport.kt` | Primary transport for Join Call |
| QrFallbackTransport | `android/app/src/main/kotlin/com/edgeppg/app/transport/QrFallbackTransport.kt` | Fallback for Join Call |
| SessionController | `android/app/src/main/kotlin/com/edgeppg/app/session/SessionController.kt` | Triggered after Join Call acknowledged |
| ChallengeEngine | `android/app/src/main/kotlin/com/edgeppg/app/challenge/ChallengeEngine.kt` | Generates per-session challenges (unchanged) |
| IntegrityManager | `android/app/src/main/kotlin/com/edgeppg/app/integrity/IntegrityManager.kt` | Signs transcript (unchanged) |
| PC Verifier | `verifier/server.py` | Extended with call scheduling + Join Call endpoint |
| MainActivity | `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | Extended with applicant dashboard UI |
| TransportResult | `android/app/src/main/kotlin/com/edgeppg/app/transport/Transport.kt` | Carries Join Call response |

---

## 5. State Model (Mandatory Separation)

**These four state machines are INDEPENDENT and MUST NOT be collapsed.** A future implementation agent must treat them as orthogonal dimensions.

### 5.1 Call State (Session Orchestration Layer)
```
SCHEDULED → WAITING → JOINING → CONNECTED → COMPLETED
                    ↘ FAILED (timeout, declined, network error)
```
- **SCHEDULED**: PC created call record with applicant info, scheduled time
- **WAITING**: Scheduled time reached, PC waiting for applicant to join
- **JOINING**: Applicant pressed Join Call, message in flight
- **CONNECTED**: Join Call acknowledged, verification pipeline started
- **COMPLETED**: Verification finished, transcript signed, result delivered

### 5.2 Transport State (Network Layer)
```
DISCONNECTED → CONNECTING → CONNECTED → FAILED
```
- Reflects TCP/HTTP connectivity to the verifier endpoint
- `CONNECTED` means the HTTP round-trip works; does NOT mean verification passed

### 5.3 Verification State (Pipeline Execution Layer)
```
NOT_STARTED → IN_PROGRESS → COMPLETED
```
- Tracks whether the EdgePPG verification pipeline has been invoked

### 5.4 Verification Result (Security Decision Layer)
```
LIVE | SPOOF | UNCERTAIN
```
- Output of `DecisionEngine` after security gates
- **Connected call ≠ LIVE**; **Successful transport ≠ LIVE**; **Join Call ≠ verification result**

### 5.5 State Transition Rules (Invariants)

| Rule | Enforcement |
|------|-------------|
| Join Call only valid in `WAITING` or `SCHEDULED` (past scheduled time) | PC verifier rejects Join Call in other states |
| Verification pipeline starts ONLY after Join Call acknowledged | `SessionController.start()` called from PC-side trigger |
| Transport `CONNECTED` required before Join Call can be sent | Android UI disables Join Call if transport failed |
| Verification Result only meaningful when Verification State = `COMPLETED` | UI shows result only after pipeline finishes |
| `UNCERTAIN` is a valid terminal result — not an error | UI must display UNCERTAIN with gate failure reason |

---

## 6. Android Dashboard Requirements

### 6.1 Applicant Profile (Minimal)
- Full name (from bank scheduling system)
- Applicant ID / reference number (opaque token)
- No biometric data, no PII beyond what bank provides

### 6.2 Scheduled Call Display
- Bank/verifier name
- Scheduled date/time (local timezone)
- Call status: `UPCOMING` | `READY_TO_JOIN` | `IN_PROGRESS` | `COMPLETED`
- Countdown to scheduled time (if `UPCOMING`)

### 6.3 Join Call Action
- Primary button: "Join Call" — enabled when:
  - Call status = `READY_TO_JOIN` (scheduled time reached)
  - Transport state = `CONNECTED` (or `CONNECTING` with retry)
  - No active session in progress
- On press: sends Join Call command via `Transport.send()`
- Button changes to "Joining..." with spinner during `JOINING` state

### 6.4 Call Status Display (During Verification)
Once Join Call acknowledged and verification starts, reuse existing `MainActivity` session UI:
- Challenge prompts (gaze, head, hand, still, optical flash)
- Real-time quality indicators (fps, lock, face present)
- Progress through CAPTURE → QUALITY → BASELINE → CHALLENGE → PROCESSING
- Final decision screen (LIVE/SPOOF/UNCERTAIN) with transport result

### 6.5 UI Architecture
- Extend `MainActivity` with a **pre-session dashboard fragment/view**
- Reuse existing `SessionController.state` StateFlow for verification phase
- Add new `CallState` StateFlow for pre-verification phase
- No new Activity — single Activity, view switching

---

## 7. PC Dashboard Requirements

### 7.1 Verifier/Bank Information
- Verifier name / institution
- Operator ID (if multi-operator)

### 7.2 Call Scheduling (Create Call)
- Input: Applicant name, applicant reference ID, scheduled date/time
- Output: Call record with unique `call_id`, stored locally (JSON/file)
- UI: Simple form → "Schedule Call" → appears in call list

### 7.3 Call List / Dashboard
| Column | Value |
|--------|-------|
| Call ID | Unique identifier |
| Applicant | Name + reference |
| Scheduled Time | Date/time |
| Status | `SCHEDULED` / `WAITING` / `JOINING` / `CONNECTED` / `COMPLETED` / `FAILED` |
| Actions | "Start Waiting" (if SCHEDULED), "View Result" (if COMPLETED) |

### 7.4 Waiting State
- When operator clicks "Start Waiting" for a `SCHEDULED` call:
  - Call status → `WAITING`
  - PC listens for Join Call on existing `POST /api/result` endpoint (extended)
  - Dashboard shows "Waiting for applicant to join..." with timeout countdown

### 7.5 Join Call Event Handling
- New endpoint or extended `POST /api/result` payload to distinguish Join Call from verification result
- On valid Join Call: call status → `CONNECTED`, trigger verification pipeline start
- Response to applicant: `{ "ok": true, "call_id": "...", "action": "START_VERIFICATION" }`

### 7.6 Verification Integration
- After Join Call acknowledged: PC signals Android to start verification
- Android runs existing `SessionController.start()` → full pipeline
- PC receives verification result via existing `POST /api/result` (unchanged envelope)
- PC dashboard updates: call status → `COMPLETED`, shows decision, receipt link

### 7.7 PC Dashboard Implementation
- **Extend `server.py` HTML dashboard** — add call scheduling UI, call list, waiting view
- **No new server process** — same Python HTTP server, new routes:
  - `GET /api/calls` — list calls
  - `POST /api/calls` — create/schedule call
  - `POST /api/calls/{id}/wait` — enter waiting state
  - `POST /api/result` — extended to accept Join Call + verification envelope
- **Offline receipt generation** — reuse existing `receipt.py`

---

## 8. Join Call Command/Event

### 8.1 Transport Reuse (Mandatory)

**The Join Call message MUST use the existing `Transport` interface.** No new transport, no new protocol.

```kotlin
// Existing interface — used as-is
interface Transport {
    suspend fun send(envelope: IntegrityManager.Envelope): TransportResult
}
```

### 8.2 Join Call Envelope Design

The Join Call is a **control message**, not a verification result. It uses a **minimal envelope** distinct from the verification transcript envelope.

**Option A: Extended Envelope with `type` field (Recommended)**
```json
// Join Call Request (Android → PC)
{
  "type": "CALL_JOIN_REQUEST",
  "call_id": "call-2026-09-26-001",
  "applicant_ref": "APP-12345",
  "nonce": "a3f1c9e2b4d60718",
  "timestamp_ms": 1700000000000
}

// Join Call Response (PC → Android)
{
  "type": "CALL_JOIN_RESPONSE",
  "ok": true,
  "call_id": "call-2026-09-26-001",
  "action": "START_VERIFICATION",
  "session_seed": "hex_seed_for_challenge_engine",
  "verifier_nonce": "verifier_generated_nonce"
}
```

**Option B: Separate endpoint `/api/call/join`**
- Simpler separation but requires new server route
- Still uses `Transport` interface (just different path)

> **Decision:** Option A preferred — single endpoint, type-discriminated, reuses all transport logic (retries, timeouts, QR fallback).

### 8.3 Join Call Payload Constraints

**MUST contain:**
- `call_id` — correlates with PC scheduled call
- `applicant_ref` — opaque applicant identifier
- `nonce` — fresh per Join Call attempt (replay protection)
- `timestamp_ms` — freshness window

**MUST NOT contain:**
- ❌ 28-feature vector
- ❌ Raw camera frames or sensor streams
- ❌ Private keys or cryptographic material
- ❌ Fabricated verification results (LIVE/SPOOF/UNCERTAIN)
- ❌ Challenge responses (those come later in verification envelope)
- ❌ Biometric templates or embeddings

### 8.4 Signing

- Join Call request **may be signed** using `IntegrityManager` for authenticity
- Join Call response **must be signed** by PC (or at least include verifier nonce)
- Reuse `IntegrityManager.Envelope` structure — `data` = canonical JSON of Join Call payload

---

## 9. Transport Reuse Requirement (Explicit Prohibition)

> **NO SECOND TRANSPORT.** The implementation agent must inspect and reuse the existing EdgePPG transport.

| Prohibited | Required |
|------------|----------|
| New HTTP client/OkHttp instance | Use `LocalWifiTransport` (already constructed in `MainActivity`) |
| WebSocket / Socket.IO / gRPC | Use existing HTTP `POST /api/result` |
| New QR protocol | Use `QrFallbackTransport` for Join Call fallback |
| Parallel session architecture | Single `SessionController` per call |
| Custom retry logic | Use `TransportResult` error handling |

The `Transport` interface was designed for exactly this: **any envelope delivery**. Join Call is just another envelope type.

---

## 10. Integration with Existing Verification Pipeline

### 10.1 Flow Summary

```
1. PC: Operator schedules call → creates call record (SCHEDULED)
2. PC: Operator clicks "Start Waiting" → call status = WAITING
3. Android: Applicant sees call in dashboard (READY_TO_JOIN)
4. Android: Applicant taps "Join Call"
5. Android: LocalWifiTransport.send(JoinCallEnvelope) → PC
6. PC: Validates Join Call (call_id exists, status=WAITING, nonce fresh)
7. PC: Responds with CALL_JOIN_RESPONSE { action: "START_VERIFICATION", session_seed }
8. Android: Receives response → SessionController.start() with provided seed
9. Android: Runs FULL existing pipeline (challenges, rPPG, optical, ML, gates)
10. Android: IntegrityManager.sign(verification transcript) → Transport.send()
11. PC: Receives verification envelope → verifies signature → writes receipt
12. PC: Updates call status = COMPLETED, displays decision + receipt
```

### 10.2 SessionController Integration

- `SessionController.start()` already accepts no parameters and generates its own seed
- **Modification needed:** Add overload `start(externalSeed: String?)` to use PC-provided seed for challenge reproducibility
- PC includes `session_seed` in Join Call response so both sides can reproduce challenges

### 10.3 ChallengeEngine Determinism

`ChallengeEngine.generateApplicant(seedHex)` and `generateTrusted(seedHex)` are **deterministic** for a given seed. This allows PC to know the expected challenge sequence for audit — already implemented.

---

## 11. UI Requirements

### 11.1 Android (Applicant Side)

| Screen | Implementation |
|--------|----------------|
| Pre-session Dashboard | New `CallDashboardFragment` or view state in `MainActivity` |
| Call List | `RecyclerView` with scheduled calls (typically 1) |
| Join Call Button | Material Button, enabled per §6.3 conditions |
| Joining Spinner | `ProgressBar` + "Joining..." text |
| Verification Phase | **Existing `MainActivity` rendering** — zero changes needed |
| Result Screen | **Existing `MainActivity` DONE state rendering** — zero changes |

### 11.2 PC (Verifier Side)

| Screen | Implementation |
|--------|----------------|
| Call Scheduling | HTML form in `server.py` dashboard (`/` endpoint) |
| Call List | HTML table with status badges, action buttons |
| Waiting View | Auto-refreshing status, "Applicant joined" detection |
| Verification Result | **Existing `server.py` dashboard log table** — extended with call context |
| Receipt View | Link to `verifier/receipts/` JSON (existing) |

---

## 12. Implementation Sequence

### Phase 1: PC Dashboard Extension (Foundation)
1. Extend `server.py` with call storage (in-memory + JSON file persistence)
2. Add routes: `GET/POST /api/calls`, `POST /api/calls/{id}/wait`
3. Extend `POST /api/result` to handle `type: "CALL_JOIN_REQUEST"`
4. Update HTML dashboard with call scheduling UI, call list, waiting view
5. Test: Schedule call → enter waiting → simulate Join Call via curl → verify response

### Phase 2: Android Join Call Integration
1. Add `CallState` enum and StateFlow to `SessionController` or new `CallController`
2. Extend `MainActivity` with pre-session dashboard view (call list + Join button)
3. Implement Join Call envelope construction (minimal payload, signed)
4. Wire Join Call button → `transport.send(joinCallEnvelope)`
5. Handle `CALL_JOIN_RESPONSE` → call `SessionController.start(externalSeed)`
6. Test: Real Join Call → verification pipeline runs → result delivered

### Phase 3: End-to-End Validation
1. PC: Schedule call for +2 minutes
2. PC: Click "Start Waiting"
3. Android: App shows call as "Ready to Join"
4. Android: Tap "Join Call"
5. Verify: PC receives Join Call, responds with session seed
6. Verify: Android starts verification (existing UI appears)
7. Verify: Session completes → transcript signed → sent via transport
8. Verify: PC receives verification envelope, writes receipt
9. Verify: Both dashboards show COMPLETED with decision

---

## 13. Testing & Acceptance Criteria

### 13.1 Unit/Contract Tests
- Join Call envelope serialization/deserialization
- Call state machine transitions (invalid transitions rejected)
- PC call scheduling persistence (survives server restart)
- Transport reuse: Join Call uses same `LocalWifiTransport` instance

### 13.2 Integration Tests
- Full flow: Schedule → Wait → Join → Verify → Receipt
- Transport failure during Join Call → Android shows retry / FAILED state
- Join Call replay attack → PC rejects (nonce cache)
- Join Call for non-existent call_id → PC rejects
- Join Call when call status ≠ WAITING → PC rejects

### 13.3 Acceptance Criteria

| Criterion | Pass Condition |
|-----------|----------------|
| Call scheduling works | PC operator can create call with applicant info + time |
| Join Call uses existing transport | No new transport classes; `LocalWifiTransport.send()` called |
| State separation enforced | Call State, Transport State, Verification State, Result all tracked independently |
| Verification pipeline unchanged | Same `SessionController`, `ChallengeEngine`, `DecisionEngine`, `IntegrityManager` |
| No mocks in final validation | Real PC server, real Android device, real network, real transport |
| PC dashboard shows full lifecycle | SCHEDULED → WAITING → JOINING → CONNECTED → COMPLETED with decision |
| Android dashboard shows full lifecycle | UPCOMING → READY_TO_JOIN → JOINING → verification UI → result |

---

## 14. Build & Environment Constraints

- **Use existing Android project:** `E:\EdgePPG\android`
- **Use project-local Gradle wrapper:** `.\gradlew.bat assembleDebug`
- **Preserve verified toolchain:** JDK 25.0.3, Gradle 9.6.0, AGP 9.4.1
- **No new dependencies** unless absolutely required (prefer stdlib / existing deps)
- **PC side:** Python 3.11+, stdlib only (no new pip packages for baseline)

---

## 15. Consistency Validation (Pre-Submission Checklist)

- [ ] Call State, Transport State, Verification State, Verification Result all modeled separately
- [ ] Join Call message contains only control fields (no feature vectors, frames, keys, fabricated results)
- [ ] Join Call uses `Transport` interface — no new HTTP client, no WebSocket, no second transport
- [ ] PC verifier extended, not replaced — `server.py` gains routes, keeps `POST /api/result` for verification
- [ ] `SessionController` integration uses existing methods (add `start(externalSeed?)` overload only)
- [ ] 28-feature schema unchanged (`FeatureSchema.kt`, `canonical.py`)
- [ ] Security gates unchanged (`DecisionEngine.kt`, `verify.py`)
- [ ] LIVE/SPOOF/UNCERTAIN semantics unchanged
- [ ] Android Keystore signing unchanged (`IntegrityManager.kt`)
- [ ] Canonical JSON format unchanged (`IntegrityManager.canonicalJson`, `verifier/canonical.py`)
- [ ] QR fallback available for Join Call (reuse `QrFallbackTransport`)
- [ ] No video/voice/media streaming code introduced

---

## 16. Unresolved Items (To Be Determined During Implementation)

| Item | Status | Resolution Approach |
|------|--------|---------------------|
| Exact Join Call envelope schema | TBD | Design during Phase 1; follow existing envelope patterns |
| PC call storage format | TBD | JSON file per call in `verifier/calls/` — simple, auditable |
| Join Call signing requirement | TBD | Start unsigned for simplicity; add signing if replay risk warrants |
| Android dashboard: Fragment vs View | TBD | Fragment preferred for lifecycle; single Activity constraint |
| Scheduled time timezone handling | TBD | Store UTC in PC, convert to device timezone on Android |
| Call timeout / expiry policy | TBD | Configurable (default 5 min wait after scheduled time) |
| Multi-applicant queue support | Deferred | Single active call per verifier for baseline |

---

## 17. Appendix: Join Call vs Verification Envelope Comparison

| Aspect | Join Call Envelope | Verification Envelope |
|--------|-------------------|----------------------|
| **Purpose** | Control: "Start verification for this call" | Evidence: "Here is the signed verification result" |
| **Trigger** | Applicant taps Join Call | SessionController.commitAndDispatch() |
| **Direction** | Android → PC | Android → PC |
| **Response** | PC → Android (START_VERIFICATION) | PC → Android (verdict + receipt) |
| **Payload** | call_id, applicant_ref, nonce, timestamp | 28-feature decision, transcript, signature |
| **Signing** | Optional (recommended) | Mandatory (IntegrityManager) |
| **PC Action** | Validate call, respond with seed | Verify signature, write receipt, log |
| **Android Next** | Start SessionController | Show result, allow new session |

---

*End of VKYC Call Dashboard Specification*