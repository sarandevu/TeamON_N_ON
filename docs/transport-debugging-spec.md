# EdgePPG Physical iQOO Transport Debugging and Validation Specification

**Version:** 1.0  
**Status:** Implementation-Ready Specification  
**Related Documents:** `docs/Architecture.md`, `docs/Requirements.md`, `docs/TechStack.md`, `docs/ANDROID_ENVIRONMENT.md`, `docs/Workflow.md`

---

## 1. Purpose & Scope

This specification defines the investigation, fix, and validation requirements for the **physical iQOO device transport failure** currently observed when running the EdgePPG Android application on a real iQOO 15 device.

**Observed Failure:**
```
DECISION: UNCERTAIN
transport ok: false
http: 0
round-trip: 12ms
reason: network-error:UnknownServiceException
CLEARTEXT communication to 10.0.2.2 not permitted by network security policy
```

**In Scope:**
- Root cause analysis of the transport failure on physical hardware
- Minimal, scoped fix to enable the existing local Wi-Fi transport
- Real end-to-end validation: physical iQOO → actual network → actual PC verifier → actual response

**Out of Scope:**
- Redesigning the transport protocol (HTTP vs HTTPS, new protocols)
- Modifying the ML pipeline, security gates, or 28-feature schema
- Changing the cryptographic signing or transcript format
- Creating a second competing transport implementation
- Any changes to `verifier/server.py` protocol (the PC endpoint is correct)

---

## 2. Background & Current State

### 2.1 Android Transport Implementation (`LocalWifiTransport.kt`)

```kotlin
// Line 104 in LocalWifiTransport.kt
const val DEFAULT_BASE_URL: String = "http://10.0.2.2:8080"
const val DEFAULT_PATH: String = "/api/result"
```

**Critical Finding:** `10.0.2.2` is the **Android emulator's loopback alias** for reaching the host machine. It is **not routable on a physical device**. The comment on line 102–103 explicitly acknowledges this:

```kotlin
// Android emulator's loopback to the host machine. On a real
// iQOO the operator should construct with the laptop's LAN IP.
```

However, **no mechanism exists in the current codebase to configure this URL** for a physical device — the `MainActivity.kt` instantiates `LocalWifiTransport()` with no arguments (line 69), using the emulator default.

### 2.2 PC Verifier Implementation (`server.py`)

```python
# Line 166, 179 in server.py
p.add_argument("--port", type=int, default=8080)
httpd = ThreadingHTTPServer(("0.0.0.0", args.port), VerifierHandler)
```

The PC verifier correctly binds to `0.0.0.0:8080` (all interfaces), making it reachable from the local network.

### 2.3 Android Network Security Configuration

**No `network_security_config.xml` exists** in the project. The Android Manifest declares:
```xml
<uses-permission android:name="android.permission.INTERNET" />
```

But Android 9 (API 28) and higher **block cleartext HTTP by default**. Since `targetSdk = 37` (Android 14), cleartext HTTP to any host is blocked unless explicitly permitted via a Network Security Configuration.

### 2.4 Error Breakdown

| Error Component | Meaning |
|----------------|---------|
| `network-error:UnknownServiceException` | OkHttp's wrapper for "cleartext traffic not permitted" |
| `CLEARTEXT communication to 10.0.2.2 not permitted` | Android Network Security Policy rejection |
| `http: 0` | No HTTP response received (request never left the device) |
| `round-trip: 12ms` | Time spent in OkHttp before the policy rejection |

---

## 3. Root Cause Analysis (Repository-Specific Findings)

### 3.1 Why `10.0.2.2` is Used

The `DEFAULT_BASE_URL` was chosen for **emulator development convenience**. It is a documented Android emulator feature — `10.0.2.2` routes to the host machine's `127.0.0.1`. On a physical device, this IP is **unroutable** (it falls in the `10.0.0.0/8` private range but is not assigned to any interface).

### 3.2 Why Cleartext HTTP is Blocked

- `targetSdk = 37` (Android 14) → cleartext HTTP disabled by default
- No `network_security_config.xml` in `res/xml/` → no exceptions configured
- The architecture intentionally uses **local HTTP** (not HTTPS) for the primary transport — see `Architecture.md §10`, `Requirements.md FR-TR-1`, `TechStack.md §19`

### 3.3 What the Physical Device Needs

1. **Correct target IP** — The PC's LAN IP (e.g., `192.168.1.x`, `10.0.0.x`, etc.), not `10.0.2.2`
2. **Network Security Config** — Scoped permission for cleartext HTTP to the local network only
3. **PC server reachable** — PC firewall must allow inbound on port 8080

---

## 4. Non-Goals (Explicitly Prohibited)

- ❌ **Do not** change HTTP to HTTPS unless HTTPS is already in the authoritative architecture (it is not)
- ❌ **Do not** create a second transport implementation (no new HTTP stack, no WebSocket, no gRPC)
- ❌ **Do not** modify `server.py` protocol or response format
- ❌ **Do not** modify the 28-feature schema, ML model, security gates, or transcript signing
- ❌ **Do not** globally weaken network security (e.g., `android:usesCleartextTraffic="true"` on `<application>`)
- ❌ **Do not** blindly replace `10.0.2.2` without inspecting the existing source and environment first

---

## 5. Existing Architecture Dependencies

| Component | File | Role |
|-----------|------|------|
| Transport Interface | `android/app/src/main/kotlin/com/edgeppg/app/transport/Transport.kt` | Abstraction — `send(envelope): TransportResult` |
| Primary Transport | `android/app/src/main/kotlin/com/edgeppg/app/transport/LocalWifiTransport.kt` | HTTP POST to `baseUrl + /api/result` |
| Fallback Transport | `android/app/src/main/kotlin/com/edgeppg/app/transport/QrFallbackTransport.kt` | QR code rendering |
| PC Verifier | `verifier/server.py` | HTTP server on `0.0.0.0:8080`, endpoint `POST /api/result` |
| Session Orchestrator | `android/app/src/main/kotlin/com/edgeppg/app/session/SessionController.kt` | Calls `transport.send(envelope)` at session end |
| UI Entry Point | `android/app/src/main/kotlin/com/edgeppg/app/MainActivity.kt` | Instantiates `LocalWifiTransport()` (line 69) |
| Integrity/Signing | `android/app/src/main/kotlin/com/edgeppg/app/integrity/IntegrityManager.kt` | Produces `Envelope` for transport |

---

## 6. Required Behavior

### 6.1 Investigation Phase (Mandatory First Step)

The implementation agent **MUST** perform these checks **before** making any changes:

1. **Inspect `LocalWifiTransport.kt`** — Confirm `DEFAULT_BASE_URL = "http://10.0.2.2:8080"` and the comment about physical device
2. **Inspect `MainActivity.kt`** — Confirm `LocalWifiTransport()` is instantiated with no arguments
3. **Inspect `server.py`** — Confirm it binds to `0.0.0.0:8080` and handles `POST /api/result`
4. **Determine PC LAN IP** — Run `ipconfig` (Windows) or `ip addr` (Linux) on the PC to find the LAN IP reachable from the phone
5. **Verify network topology** — Confirm physical iQOO and PC are on the same LAN (same subnet, no client isolation)
6. **Check Windows Firewall** — Confirm port 8080 inbound is allowed for the Python process

### 6.2 Fix Requirements

#### 6.2.1 Network Security Configuration (Minimal, Scoped)

Create `android/app/src/main/res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">192.168.1.0/24</domain>
        <domain includeSubdomains="false">10.0.0.0/8</domain>
        <domain includeSubdomains="false">172.16.0.0/12</domain>
    </domain-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </base-config>
</network-security-config>
```

**Then reference it in `AndroidManifest.xml`:**
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    ... >
```

**Why this approach:**
- Scoped to private RFC 1918 ranges only — no public internet cleartext
- Does not globally enable cleartext (`base-config` remains `false`)
- Follows Android best practice for local development

#### 6.2.2 Configurable Base URL for Physical Device

**Option A (Recommended — minimal code change):** Modify `MainActivity.kt` to construct `LocalWifiTransport` with the PC's LAN IP:
```kotlin
// In MainActivity.kt, replace line 69:
private val controller = SessionController(transport = LocalWifiTransport())

// With:
private val controller = SessionController(
    transport = LocalWifiTransport(baseUrl = "http://<PC_LAN_IP>:8080")
)
```
Where `<PC_LAN_IP>` is determined during deployment (e.g., `192.168.1.47`).

**Option B (Build-time configuration):** Add a `buildConfigField` in `build.gradle.kts` for the verifier URL, or use a `local.properties` entry.

**Option C (Runtime discovery):** Implement mDNS/SSDP discovery — **deferred, not required for baseline**.

> **Decision:** Option A is the smallest change. The spec requires the implementation agent to choose the simplest working approach and document it.

#### 6.2.3 PC Server Validation

- Ensure `server.py` is running: `.venv\Scripts\python.exe -m verifier.server --port 8080`
- Verify it's accessible from another device on the LAN: `curl -X POST http://<PC_LAN_IP>:8080/api/result -H "Content-Type: application/json" -d '{"data":"{}","sig":"","alg":"SHA256withECDSA"}'`
- Should return JSON with `"ok":false` (invalid envelope) but **HTTP 200** — proves the server is reachable

---

## 7. Debugging Strategy

### 7.1 Step-by-Step Validation Checklist

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Build APK with network security config | `gradlew.bat assembleDebug` succeeds |
| 2 | Install on physical iQOO | `adb install -r app-debug.apk` succeeds |
| 3 | Start PC verifier | `python -m verifier.server` prints "listening on http://0.0.0.0:8080" |
| 4 | Verify PC reachable from phone | `adb shell ping <PC_LAN_IP>` succeeds |
| 5 | Verify port 8080 open | `adb shell nc -z <PC_LAN_IP> 8080` succeeds (or use `telnet`) |
| 6 | Launch app, complete session | App runs through CAPTURE → QUALITY → BASELINE → CHALLENGE → PROCESSING → DONE |
| 7 | Observe transport result | `transport ok: true`, `http: 200`, `decision: LIVE/SPOOF/UNCERTAIN`, `reason: null` |
| 8 | Verify PC received request | PC console shows `[verifier] "POST /api/result" 200` |
| 9 | Verify receipt written | `verifier/receipts/` contains new JSON file |

### 7.2 Failure Modes & Diagnostics

| Symptom | Likely Cause | Diagnostic |
|---------|--------------|------------|
| `network-error:UnknownServiceException` persists | Network security config not applied / wrong domain | Check `adb logcat` for `NetworkSecurityConfig` logs |
| `http: 0`, `reason: network-error:ConnectException` | Wrong IP, firewall, wrong subnet | `adb shell nc -z <IP> 8080` |
| `http: 404` | Wrong path | Verify `DEFAULT_PATH = "/api/result"` matches server |
| `http: 200`, `ok: false`, `reason: bad-pubkey` | PC verifier missing `pubkey.b64` | Provision public key per `IntegrityManager.exportPublicKeyB64()` |
| `transport ok: true` but `decision: UNCERTAIN` | Normal — verification pipeline working, transport fixed | Success! |

---

## 8. Testing & Acceptance Criteria

### 8.1 Definition of Transport Success (Mandatory)

**NONE of the following count as success:**
- Changing a UI label to say "Connected"
- Constructing a request object without sending it
- Opening a socket without completing the HTTP round-trip
- Assuming HTTP 200 without the PC actually receiving the request
- Using a mock server, hard-coded response, or fake connected state

**ONLY this counts as success:**
```
Physical iQOO → actual Android HTTP request → actual network → 
actual PC/server receives POST /api/result → actual PC response → 
Android receives and parses TransportResult with ok=true
```

### 8.2 Acceptance Criteria

| Criterion | Pass Condition |
|-----------|----------------|
| Network security config present | `res/xml/network_security_config.xml` exists and is referenced in Manifest |
| Cleartext HTTP permitted for local LAN only | Config allows RFC 1918 ranges only; base-config remains secure |
| Physical device uses correct PC IP | `LocalWifiTransport` constructed with PC LAN IP, not `10.0.2.2` |
| PC verifier receives request | Server logs show `POST /api/result` with envelope JSON |
| TransportResult.ok == true | Android UI shows `transport ok: true`, `http: 200` |
| Receipt generated | `verifier/receipts/<session>_<ts>_<sha>.json` exists |
| No architecture changes | 28-feature schema, ML model, security gates, signing unchanged |

---

## 9. Build & Environment Constraints

- **Use existing Android project:** `E:\EdgePPG\android`
- **Use project-local Gradle wrapper:** `.\gradlew.bat assembleDebug`
- **Preserve verified toolchain:** JDK 25.0.3, Gradle 9.6.0, AGP 9.4.1, Kotlin via AGP built-in
- **Do not modify:** `gradle-wrapper.properties`, `build.gradle.kts` (except if adding buildConfigField for Option B), `settings.gradle.kts`
- **Do not recreate** Android project, reinstall SDK, or migrate build system

---

## 10. Implementation Sequence

1. **Create** `android/app/src/main/res/xml/network_security_config.xml` (scoped cleartext for RFC 1918)
2. **Update** `AndroidManifest.xml` to reference `android:networkSecurityConfig="@xml/network_security_config"`
3. **Determine** PC LAN IP (run `ipconfig` on Windows host)
4. **Modify** `MainActivity.kt` line 69 to pass `baseUrl = "http://<PC_LAN_IP>:8080"` to `LocalWifiTransport`
5. **Build** APK: `.\gradlew.bat clean assembleDebug`
6. **Install** on physical iQOO: `adb install -r app-debug.apk`
7. **Start** PC verifier: `.venv\Scripts\python.exe -m verifier.server --port 8080`
8. **Run** session on device, observe transport result
9. **Verify** PC receipt generated
10. **Document** the working IP and any environment-specific notes

---

## 11. Consistency Validation (Pre-Submission Checklist)

- [ ] No changes to `Transport.kt` interface
- [ ] No changes to `LocalWifiTransport.kt` logic (only construction parameters)
- [ ] No changes to `server.py` protocol or endpoints
- [ ] No changes to `IntegrityManager`, `TranscriptBuilder`, canonical JSON
- [ ] No changes to 28-feature schema (`FeatureSchema.kt`, `canonical.py`)
- [ ] No changes to `DecisionEngine`, security gates, `LIVE`/`SPOOF`/`UNCERTAIN` semantics
- [ ] No changes to Android Keystore usage or signing algorithm
- [ ] No new transport classes created
- [ ] Network security config is scoped (not global `usesCleartextTraffic`)
- [ ] PC verifier binds to `0.0.0.0` (unchanged)

---

## 12. Unresolved Items (To Be Determined During Implementation)

| Item | Status | Resolution Approach |
|------|--------|---------------------|
| Exact PC LAN IP | TBD at deploy time | Operator runs `ipconfig`; documented in deployment notes |
| Windows Firewall rule for port 8080 | TBD | Operator ensures inbound allowed; documented in deployment notes |
| Whether mDNS discovery is needed | Deferred | Not required for baseline; Option A (hardcoded IP) sufficient |
| Build-time vs runtime URL configuration | Option A chosen | Minimal code change; can be improved later if needed |

---

*End of Transport Debugging Specification*