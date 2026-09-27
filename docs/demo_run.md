# EdgePPG — Demo Run Procedure

**Status: PROCEDURE-ONLY — no actual demo run has been performed by the
implementer at the time of writing.** This document describes the
operator's manual run, NOT a log of observed results.

The repo contains the Stage 1-12 / 13 / 15 source code and 264
passing Python unit tests. The Android APK has not been built and
installed on the iQOO from the implementer's environment, so no
"genuine → LIVE" / "photo → SPOOF" / "replay → UNCERTAIN"
observations exist to record. When the operator runs the demo, the
**Observed Results** section at the bottom of this doc is the
template to fill in.

This file is intentionally **not** a results report. It is the
operator-side procedure; results will be appended when the demo
actually runs.

---

## 1. Pre-flight (Windows host, per `docs/ANDROID_ENVIRONMENT.md`)

```powershell
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m tests.run_all_tests
# Expect: 264 tests pass (ML pipeline, PC verifier, quality math,
# decision truth table, schema / canonical parity, challenge engine,
# behaviour estimator, rPPG DSP math, multi-tracker, transport
# contract, decision engine, integrity, etc).

cd E:\EdgePPG\android
.\gradlew.bat clean assembleDebug
# Resolve any remaining compile errors. The P1 Camera2 interop
# classpath issue under AGP 9.4.1's built-in Kotlin is the most
# likely failure mode (see Stage 13 Task 8 / Stage 15 Task 7 in
# docs/implementation_plan.md); the documented fix is a small
# androidComponents { onVariants(...) } block in app/build.gradle.kts.

adb devices
# Expect: the iQOO serial listed as `device`.

adb install -r "E:\EdgePPG\android\app\build\outputs\apk\debug\app-debug.apk"
adb shell am start -n com.edgeppg.app/.MainActivity
adb logcat -c   # clear logcat
adb logcat EdgePPG/*:V *:S
```

The app must be granted CAMERA permission at first launch. If
denied, the UI shows the message documented in `MainActivity.kt`.

---

## 2. PC verifier

Start the PC verifier on the laptop. The phone and laptop must be
on the same local network.

```powershell
cd E:\EdgePPG
.\.venv\Scripts\python.exe -m verifier.server --port 8080
# Expect: "[verifier] listening on http://0.0.0.0:8080"
```

The phone's `LocalWifiTransport` defaults to `http://10.0.2.2:8080`
(Android emulator alias for the host). On a real iQOO the operator
must edit the URL in `MainActivity.kt` (line ~127:
`LocalWifiTransport()`) to the laptop's LAN IP — for example
`http://192.168.1.42:8080`. Rebuild + reinstall after the change.

Alternative: the QR fallback path. The phone shows the envelope as a
QR code; the user scans it with the laptop webcam and pastes the
JSON into the verifier dashboard's textarea. No network
configuration needed on the phone.

---

## 3. The three demo runs

For each run:
1. Position the iQOO on a stable surface, front camera facing the
   subject, screen at eye level.
2. Open the EdgePPG app.
3. Grant CAMERA permission if asked.
4. The app shows the preview + status overlay. Wait for `lock: LOCKED`,
   `face: present`. The button becomes enabled.
5. Run the documented scenario below.
6. Watch the `adb logcat` stream for `EdgePPG/stage`, `EdgePPG/capture`,
   `EdgePPG/gate`, `EdgePPG/behavior`, `EdgePPG/integrity`,
   `EdgePPG/transport` tags.

### 3.1 Genuine live participant

A real face in front of the camera, room light, no special props.

Expected observable behaviour (per the architecture, NOT a fabricated
result):
- The status overlay shows `lock: LOCKED` within ~1 s of the
  camera starting up.
- The quality gate transitions through PASS / RETRY / FAIL based
  on lighting and motion. The UI auto-advances to the challenge
  list on PASS; on FAIL the button "I look ready" lets the operator
  override.
- Each challenge card shows e.g. "Look left", "Turn head: nod",
  "Show hand: thumbs up", "Hold still 2 s", or "(optical flash —
  see overlay)" for the optical flash variant. The participant
  performs the action; the operator taps "I did it".
- After all challenges, the motion / blink check screen appears.
  The operator taps "Done".
- The result screen shows `DECISION: LIVE / SPOOF / UNCERTAIN`
  coloured green / red / amber, plus transport `ok: true / http:
  200 / round-trip: <ms>ms`.

Record in the **Observed Results** section:
- the `EdgePPG/gate: PASS` log line
- the `EdgePPG/behavior: obs:` log lines (one per challenge)
- the `EdgePPG/integrity:` log line for the envelope signature
- the `EdgePPG/transport:` log line for the round-trip ms
- the final `decision` shown on the device

### 3.2 Printed photo attack

Hold a high-resolution printed photo of a face (or a phone /
tablet showing a photo) in front of the camera at the same distance
and angle as the genuine run. The face mesh detects a face (printed
photos have landmarks), but the rPPG signal is absent (paper does
not pulse), AWB stability drifts (paper reflectivity differs), and
no behavioural response to a fresh optical challenge is present.

Expected observable behaviour (per the architecture):
- The quality gate may briefly PASS (printed photos can pass face
  detection) but the contamination flag should trip when the
  camera refocuses.
- The behavioural runner emits `BehavioralOutcome.WRONG` for the
  motion / blink challenge (printed photos don't blink on cue).
- The decision engine routes to `SPOOF` (low P_live + behavioural
  failure) or `UNCERTAIN` (if P_live is NaN because no model is
  loaded — the documented `NaNFallbackMlClient` returns NaN). The
  result screen colour is red (`SPOOF`) or amber (`UNCERTAIN`).

Record the actual observation. The hackathon philosophy says
**do not claim successful attack rejection that was not observed**.
If the print is detected as SPOOF: report it. If the print passes
as LIVE: report that too. The current ML model is the
`NaNFallbackMlClient` placeholder (P_live = NaN), so the
decision-engine truth table forces `UNCERTAIN` for any genuine
case where integrity_ok but P_live is NaN — which means the
demo's "live" run may also land on UNCERTAIN, not LIVE. That is
**not a bug**; it is the documented contract of the placeholder
model.

### 3.3 Phone / tablet replay attack

A second device plays a video of a genuine EdgePPG run (or any
video of a face). The video includes face mesh-detectable motion and
the camera can re-detect the face. The rPPG signal in the captured
video is at the replay device's display refresh rate, not the
subject's pulse.

Expected observable behaviour (per the architecture, plus the
demo limitations):
- Same face-detection pass as the genuine run.
- The optical flash challenge: a video of a previous flash is
  unsynchronised to the new flash, so the camera-side correlation
  fails. With the hackathon `OpticalFlashOverlay` simply showing a
  full-screen colour without an active correlation stage, the demo
  **cannot distinguish** a real flash response from a video
  response at this stage. The architecture documents this as
  FR-OPT-2 / FR-OPT-3 (verifier-side correlation) which is
  **[Requires Device Test]** and **not** implemented end-to-end
  here. Record the actual observation.
- The behavioural challenges have the same issue: a video plays
  back the same motion pattern. With the timeout-based matcher
  the demo routes to MATCH. Record the actual observation.

---

## 4. Failure / regression scenarios

The following are *not* part of the demo, but should be noted if
encountered:

- **Camera permission denied.** The UI shows "Camera permission
  denied. Grant CAMERA in system settings." No logcat for
  `EdgePPG/*` from the analyzer thread.
- **AE / AWB lock fails (`CONTROL_AE_STATE` stuck on `FLASH_REQUIRED`).**
  The quality gate stays in RETRY; the UI button "I look ready"
  remains the operator's escape hatch.
- **Verifier unreachable.** `LocalWifiTransport` returns
  `TransportResult.localError("network-error:ConnectException:...")`.
  The result screen shows the error and the user can scan the QR
  fallback instead.

---

## 5. Observed Results  (to be filled by the operator)

> The following is a TEMPLATE. Replace each `____` with the actual
> value observed during the operator's run. Do not invent numbers.

### Genuine (real face)

- Quality gate outcome: ____
- Optical flash visible? ____
- Behavioural observations: ____
- Decision shown on device: ____
- Verifier HTTP status: ____
- Round-trip ms: ____
- adb logcat (paste / attach): ____

### Printed photo

- Quality gate outcome: ____
- Optical flash visible? ____
- Behavioural observations: ____
- Decision shown on device: ____
- Verifier HTTP status: ____
- Round-trip ms: ____
- adb logcat: ____

### Replay (video on second device)

- Quality gate outcome: ____
- Optical flash visible? ____
- Behavioural observations: ____
- Decision shown on device: ____
- Verifier HTTP status: ____
- Round-trip ms: ____
- adb logcat: ____

---

## 6. Claim discipline

The claim-discipline rule (`EDGEPPG_MASTER_INSTRUCTIONS.md` §4) is
enforced here:

- Do NOT claim "the photo attack was rejected" unless the
  observation explicitly says so.
- Do NOT claim "rPPG detected X bpm" — the rPPG DSP is in
  place (Stage 4, pure-Kotlin) but the optical-flash correlation
  and the trained ML model are not. P_live is NaN at runtime.
- Do NOT extrapolate from one observation. If the genuine run
  landed on UNCERTAIN (because of the NaN P_live), say so.

Any result that says "claimed as per architecture" without an
adb-logcat excerpt and a verifier response is fabricated and will
not be accepted as evidence.
