# EdgePPG — Payload / Envelope Format

Authoritative description of the signed transcript that the Android
session produces and the PC verifier consumes. Mirrors the actual
code; do not drift.

* Source of truth (Android side): `app/src/main/kotlin/com/edgeppg/app/integrity/IntegrityManager.kt`
* Source of truth (PC side): `verifier/canonical.py`, `verifier/verify.py`
* Enforced by: `tests/test_canonical_parity.py` (7 tests assert the
  Kotlin `canonicalJson()` and the Python `canonical_payload()`
  produce byte-exact JSON on the same payload).

---

## 1. The signed `Envelope`

The Android Keystore signs the canonical payload and wraps it in an
`Envelope`:

```kotlin
data class Envelope(
    val data: String,        // canonical JSON (see §2)
    val sig: String,         // Base64 NO_WRAP of the raw ECDSA sig
    val alg: String = "SHA256withECDSA",
    val keyAlias: String = "edgeppg_device_key_v2",
)
```

`Envelope` is what the `Transport` interface carries. It is the
single wire format shared by `LocalWifiTransport` (HTTP POST) and
`QrFallbackTransport` (QR payload).

---

## 2. Canonical payload

The `data` field is JSON with **fixed alphabetical key order** and
**no whitespace**. The fields and order are the union of
`Requirements §FR-CRY-3` and `Architecture §9` (we resolve the
documented contradiction by including the full `Requirements` set;
this is what `tests/test_canonical_parity.py` pins):

| key              | type     | meaning                                             |
| ---------------- | -------- | --------------------------------------------------- |
| `challenge_id`   | string   | session-unique identifier                            |
| `confidence`     | float    | ML fusion confidence, `[0, 1]`                      |
| `decision`       | string   | one of `LIVE`, `SPOOF`, `UNCERTAIN`                  |
| `expected_seq`   | string   | the optical-challenge sequence (JSON-as-string)     |
| `hr_bpm`         | float    | rPPG heart-rate estimate, bpm; `0` if not measured  |
| `model_version`  | string   | `v2.1-edge` today                                    |
| `nonce`          | string   | 32 hex chars; per-session random                     |
| `roi_corr`       | float    | rPPG ROI pairwise Pearson; `[-1, 1]`; `0` if absent |
| `signal_quality` | float    | DSP quality, `[0, 1]`                                |
| `snr`            | float    | rPPG SNR; `[0, 1]`; `0` if not measured             |
| `timestamp_ms`   | int      | epoch ms (wall clock)                                |

Float format: 4dp fixed, trailing zeros stripped, `NaN`/`Inf` → `0`
(matches between Kotlin and Python — see
`tests/test_canonical_parity.py:test_kotlin_canonical_handles_nan`).
String escaping: minimal JSON (`\"`, `\\`, `\n`, `\r`, `\t`,
`\u00xx` for `< 0x20`).

This format is owned by `IntegrityManager.canonicalJson()` on the
device and `verifier.canonical.canonical_payload()` on the PC.
Both are pinned by `tests/test_canonical_parity.py` to remain
byte-exact.

---

## 3. Signature

Algorithm: `SHA256withECDSA` over the UTF-8 bytes of the canonical
`data` string.

Key:
* `EC_P256` (`secp256r1` / `prime256v1`)
* `AndroidKeyStore` provider; `StrongBox` preferred, silently
  falls back to TEE if the device doesn't expose `StrongBox`
  (`IntegrityManager.generate()`).
* `User-authentication required = false`. The current alias is
  `edgeppg_device_key_v2`.
* The raw signature (ASN.1 DER) is Base64-encoded with
  `Base64.NO_WRAP` and stored in `Envelope.sig`.

The PC verifier's `verify_envelope()` decodes the signature and
verifies it against the **byte-exact** `data` string. Any byte
change to `data` (e.g. trimming whitespace, reordering keys) makes
the signature invalid.

---

## 4. Transport envelopes

The transport layer adds no fields of its own. The two existing
transports share the `Envelope` shape; they only differ in how they
get it from the device to the verifier.

### 4.1 Local Wi-Fi (primary, `LocalWifiTransport`)

* `POST {baseUrl}/api/result`
* `Content-Type: application/json; charset=utf-8`
* Body is a JSON object — the **same four keys** the verifier reads:

  ```json
  {
    "data":     "<canonical JSON, see §2>",
    "sig":      "<Base64 NO_WRAP ECDSA sig>",
    "alg":      "SHA256withECDSA",
    "keyAlias": "edgeppg_device_key_v2"
  }
  ```

  (`LocalWifiTransport.encodeEnvelope()` builds this object via
  `org.json.JSONObject`.)

* Server reply shape (parsed back into `TransportResult`):
  `verifier/server.py:handle_result` returns
  `{ok, reason, telemetry, telemetry_sha256, server_version}`. We
  surface `decision` (from `telemetry.decision` if present) and
  `httpStatus`.

### 4.2 QR fallback (`QrFallbackTransport`)

* The same 4-key object from §4.1 is encoded as the **payload** of
  a QR code (ZXing `core:3.5.4`, `BarcodeFormat.QR_CODE`,
  `ErrorCorrectionLevel.L`, default 480×480 px).
* The user scans the QR with the laptop webcam (or copies the
  JSON from the on-screen "show payload" view) and the laptop
  dashboard POSTs it to its own `/api/result` endpoint. From the
  verifier's perspective, the QR path is identical to the Wi-Fi
  path.

### 4.3 Capacity (QR)

Today's envelope is ≈440 bytes (canonical JSON 274 + Base64 ECDSA
sig 88 + JSON wrapper 78). ZXing at `L` × 480 px holds ~2.9 KB
binary; ~1.5 KB is the conservative `MAX_QR_PAYLOAD_BYTES` ceiling
enforced by `PayloadTruncator.checkQrFits()`. Anything bigger
raises `QrOverflowException` → `TransportResult.localError("qr-overflow:...")`,
and the user is steered to the local Wi-Fi path.

Local Wi-Fi is capped by the PC server's `MAX_BODY = 256 KB` in
`verifier/server.py` — not a device-side concern.

---

## 5. Freshness and replay

* Envelope carries `timestamp_ms` (wall-clock epoch ms at signing).
* The PC verifier requires `|now - timestamp_ms| ≤ 5 min` (see
  `FRESh_MS` in `verifier/verify.py` and the parallel
  `IntegrityManager.FRESH_MS`).
* Each envelope has a per-session `nonce` (32 hex chars; 16 random
  bytes from `SecureRandom`). The PC verifier keeps a per-process
  LRU of seen nonces within the freshness window and rejects
  duplicates. (`seenNonces` in `verifier/verify.py`.)

---

## 6. Provisioning

One-time on first run on a device:

1. `IntegrityManager.ensureKey()` (idempotent) generates the
   `edgeppg_device_key_v2` EC P-256 key in `AndroidKeyStore`. No
   user interaction.
2. `IntegrityManager.exportPublicKeyB64()` returns the
   X.509-encoded public key, Base64 NO_WRAP.
3. Operator pastes that single line into the PC's
   `verifier/pubkey.b64` (next to `verifier/verify.py`). Done.

After provisioning, every `IntegrityManager.sign()` produces
envelopes the PC verifier accepts.

---

## 7. What this doc does NOT cover

* The **feature schema** (Stage 9) is a different artefact. The
  28-feature schema is what the row assembler writes to disk /
  feeds to ML; the 11-field canonical payload is what the device
  signs and ships. They are independent.
* The **decision engine** output (`LIVE`/`SPOOF`/`UNCERTAIN`) is
  one of the 11 fields. See `Architecture §8` and
  `tests/test_decision_truth_table.py`.
* The **canonical byte format is not a future change point**. Any
  change to the key set or the float format is a one-file edit
  to `IntegrityManager.canonicalJson()` (and a corresponding edit
  in `verifier/canonical.py`), pinned by
  `tests/test_canonical_parity.py`.
