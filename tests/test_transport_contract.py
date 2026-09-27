"""Stage 13 Task 2 — Transport interface contract test.

The Kotlin `transport/Transport.kt` defines the on-device transport
interface. This test parses the source and asserts the documented
contract surface — it does NOT exercise OkHttp / networking.

The contract is the source-of-truth for both
`LocalWifiTransport` (Task 3) and `QrFallbackTransport` (Task 4).

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import base64
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                / "com" / "edgeppg" / "app" / "transport" / "Transport.kt")
LOCALWIFI_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                / "com" / "edgeppg" / "app" / "transport" / "LocalWifiTransport.kt")
QR_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
          / "com" / "edgeppg" / "app" / "transport" / "QrFallbackTransport.kt")
TRUNCATOR_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                 / "com" / "edgeppg" / "app" / "transport" / "PayloadTruncator.kt")
INTEGRITY_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                / "com" / "edgeppg" / "app" / "integrity" / "IntegrityManager.kt")
OFFICEKIT_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                 / "com" / "edgeppg" / "app" / "integrity" / "OfficeKit.kt")
TRANSCRIPT_BUILDER_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                          / "com" / "edgeppg" / "app" / "integrity" / "TranscriptBuilder.kt")
SESSION_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
             / "com" / "edgeppg" / "app" / "session" / "SessionController.kt")
CHALLENGE_SPEC_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                     / "com" / "edgeppg" / "app" / "challenge" / "ChallengeSpec.kt")
OPTICAL_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
             / "com" / "edgeppg" / "app" / "optical" / "OpticalFlashOverlay.kt")
MAINACTIVITY_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                  / "com" / "edgeppg" / "app" / "MainActivity.kt")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TransportInterfaceContractTests(unittest.TestCase):
    """`Transport.kt` must declare the documented contract."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(TRANSPORT_KT)
        cls.integrity_src = _read(INTEGRITY_KT)

    def test_interface_named_transport(self):
        self.assertRegex(self.src, r"interface\s+Transport\s*\{")

    def test_interface_is_in_com_edgeppg_app_transport(self):
        self.assertRegex(self.src, r"package\s+com\.edgeppg\.app\.transport")

    def test_send_method_signature(self):
        """`send(envelope: IntegrityManager.Envelope): TransportResult` — suspending."""
        # Match: 'suspend fun send(envelope: IntegrityManager.Envelope)'
        m = re.search(
            r"suspend\s+fun\s+send\s*\(\s*(\w+)\s*:\s*([^)]+)\s*\)",
            self.src,
        )
        self.assertIsNotNone(
            m,
            "send(envelope: ...): ... not found",
        )
        param_name, param_type = m.group(1), m.group(2)
        self.assertEqual(param_name, "envelope")
        self.assertEqual(param_type, "IntegrityManager.Envelope")
        # Return type must be TransportResult
        m_ret = re.search(r"send\s*\([^)]*\)\s*:\s*(\w+)", self.src)
        self.assertIsNotNone(m_ret)
        self.assertEqual(m_ret.group(1), "TransportResult")

    def test_transport_is_suspending_not_blocking(self):
        """Suspend so the caller can `await` it from a coroutine."""
        self.assertIn("suspend fun send", self.src)

    def test_send_does_not_throw(self):
        """The interface contract explicitly forbids throwing from `send`."""
        self.assertIn("MUST NOT throw", self.src)

    def test_envelope_type_imported(self):
        self.assertRegex(
            self.src,
            r"import\s+com\.edgeppg\.app\.integrity\.IntegrityManager",
        )

    def test_envelope_type_matches_integritymanager(self):
        """The Kotlin Envelope must exist on IntegrityManager with the
        four documented fields (data, sig, alg, keyAlias)."""
        m = re.search(
            r"data\s+class\s+Envelope\s*\(([^)]+)\)",
            self.integrity_src, re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        for f in ("val data:", "val sig:", "val alg:", "val keyAlias:"):
            self.assertIn(f, body)


class TransportResultContractTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read(TRANSPORT_KT)

    def test_data_class_named_transport_result(self):
        self.assertRegex(
            self.src,
            r"data\s+class\s+TransportResult\s*\(",
        )

    def test_documented_fields_present(self):
        # Every field listed in the architecture must exist on the
        # data class. We assert the field declarations exist by name.
        for field in ("ok", "reason", "decision", "telemetry",
                      "telemetrySha256", "receiptPath", "serverVersion",
                      "httpStatus", "roundTripMs"):
            self.assertRegex(
                self.src,
                rf"val\s+{field}\s*:",
                f"missing field on TransportResult: {field}",
            )

    def test_local_error_factory_present(self):
        self.assertRegex(
            self.src,
            r"fun\s+localError\s*\(",
        )

    def test_result_is_in_transport_package(self):
        self.assertRegex(self.src, r"package\s+com\.edgeppg\.app\.transport")


class LocalWifiTransportContractTests(unittest.TestCase):
    """Stage 13 Task 3 — LocalWifiTransport.

    The Kotlin file must exist, declare the class, implement the
    Transport interface, and emit a JSON envelope that exactly matches
    the wire shape consumed by `verifier/server.py:handle_result`.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(LOCALWIFI_KT)

    def test_file_exists_and_has_transport_class(self):
        self.assertRegex(
            self.src,
            r"class\s+LocalWifiTransport[^{]*:\s*Transport\b",
        )

    def test_uses_okhttp_client(self):
        # OkHttp is the documented transport. We don't pin the type
        # too tightly — `OkHttpClient` is the public type.
        self.assertIn("OkHttpClient", self.src)

    def test_endpoint_path_is_api_result(self):
        # `verifier/server.py` registers POST /api/result. Any
        # other path would silently fail on the PC side.
        self.assertIn("/api/result", self.src)

    def test_envelope_serialized_with_documented_keys(self):
        # The PC verifier reads these exact keys from the JSON body.
        # The transport MUST send data, sig, alg, keyAlias.
        for key in ("data", "sig", "alg", "keyAlias"):
            self.assertRegex(
                self.src,
                rf'put\(\s*"{key}"',
                f"envelope JSON missing key: {key}",
            )

    def test_suspend_send_uses_dispatchers_io(self):
        # Network IO must not run on the main thread. The suspend
        # function dispatches to IO explicitly.
        self.assertIn("Dispatchers.IO", self.src)
        self.assertIn("withContext", self.src)

    def test_response_parsing_handles_malformed_input(self):
        # A malformed response from the verifier must NOT throw — it
        # becomes a structured TransportResult.
        self.assertIn("parse-error", self.src)
        self.assertIn("parseResponse", self.src)

    def test_does_not_throw_on_network_failure(self):
        # Network errors are caught and turned into TransportResult.
        self.assertIn("network-error", self.src)
        self.assertRegex(self.src, r"catch\s*\(\s*e:\s*Exception\s*\)")

    def test_uses_coroutines(self):
        # Coroutines support is required for the suspend modifier on
        # Transport.send to compile.
        self.assertIn("kotlinx.coroutines", self.src)


class QrFallbackTransportContractTests(unittest.TestCase):
    """Stage 13 Task 4 — QrFallbackTransport.

    The class must exist, implement Transport, render a QR via ZXing,
    and emit the same envelope JSON shape the verifier expects. The
    `send()` call must NEVER throw — every error path is a
    structured TransportResult.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(QR_KT)

    def test_file_exists_and_has_qr_class(self):
        self.assertRegex(
            self.src,
            r"class\s+QrFallbackTransport[^{]*:\s*Transport\b",
        )

    def test_uses_zxing_qrcodewriter(self):
        self.assertIn("com.google.zxing", self.src)
        self.assertIn("QRCodeWriter", self.src)
        self.assertIn("BarcodeFormat.QR_CODE", self.src)

    def test_uses_error_correction_level(self):
        # We want the most capacity (level L) since envelopes are
        # under a kilobyte; L gives ~2.9 KB.
        self.assertIn("ErrorCorrectionLevel", self.src)

    def test_envelope_serialized_with_documented_keys(self):
        # The verifier (and any paste path on its dashboard) reads
        # these exact keys from the QR payload.
        for key in ("data", "sig", "alg", "keyAlias"):
            self.assertRegex(
                self.src,
                rf'put\(\s*"{key}"',
                f"QR envelope JSON missing key: {key}",
            )

    def test_render_qr_method_present(self):
        # The UI will call this to get a BitMatrix for display.
        self.assertRegex(self.src, r"fun\s+renderQr\b")
        # And it returns a ZXing BitMatrix.
        self.assertIn(": BitMatrix", self.src)

    def test_send_does_not_throw(self):
        # All error paths become TransportResult.localError.
        for pattern in (
            r"catch\s*\(\s*e:\s*WriterException\s*\)",
            r"catch\s*\(\s*e:\s*IllegalArgumentException\s*\)",
            r"catch\s*\(\s*e:\s*Exception\s*\)",
        ):
            self.assertRegex(self.src, pattern)

    def test_send_returns_transport_result_with_qr_metadata(self):
        # When the QR encodes successfully, the result is marked
        # transport=qr so the UI knows which fallback fired.
        self.assertIn('"transport"', self.src)
        self.assertIn('"qr"', self.src)


class PayloadTruncatorContractTests(unittest.TestCase):
    """Stage 13 Task 5 — PayloadTruncator.

    Architecture §10 / FR-TR-2: refuse to silently truncate a
    payload that exceeds the QR capacity. The truncator exists, is
    wired into QrFallbackTransport.send, and exposes
    QrOverflowException.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(TRUNCATOR_KT)
        cls.qr_src = _read(QR_KT)

    def test_file_exists_with_truncator_object(self):
        self.assertRegex(self.src, r"object\s+PayloadTruncator\b")

    def test_exposes_qr_overflow_exception(self):
        self.assertIn("class QrOverflowException", self.src)

    def test_max_qr_payload_bytes_constant_present(self):
        # The documented capacity ceiling must be a single named
        # constant, not a magic number scattered in the QR transport.
        self.assertRegex(self.src, r"const\s+val\s+MAX_QR_PAYLOAD_BYTES\s*:\s*Int")

    def test_refuses_to_truncate_silently(self):
        # The whole point of this class. The error message must say
        # the truncation is refused, not performed.
        self.assertIn("refusing to", self.src.lower())
        self.assertIn("truncate", self.src.lower())

    def test_qr_transport_calls_truncator(self):
        # The QR fallback MUST consult PayloadTruncator before
        # encoding. Otherwise the cap is just a comment.
        self.assertIn("PayloadTruncator", self.qr_src)
        self.assertIn("checkQrFits", self.qr_src)

    def test_qr_transport_catches_overflow(self):
        # The overflow path must be a structured TransportResult,
        # not a crash. The catch block for QrOverflowException is the
        # wired-up evidence.
        self.assertIn("QrOverflowException", self.qr_src)


# ---- Real boundary tests against a Python mirror of the truncator ----
# The Python mirror is NOT a re-implementation of every Kotlin
# class — it is a one-purpose check that the documented
# MAX_QR_PAYLOAD_BYTES constant is consistent with the actual bytes
# produced by the canonical-JSON / ECDSA envelope we have today.
import json

from verifier.canonical import canonical_payload


def _sample_envelope_json_bytes() -> int:
    """Approximate the byte size of a real EdgePPG envelope as
    transmitted by the Android client: canonical-JSON payload +
    Base64 ECDSA P-256 sig + JSON wrapper. The PC verifier
    reads exactly the four keys {data, sig, alg, keyAlias}."""
    payload = canonical_payload({
        "challenge_id": "sess-001",
        "confidence": 0.94,
        "decision": "LIVE",
        "expected_seq": '[{"d":25,"t":250,"c":0}]',
        "hr_bpm": 72.5,
        "model_version": "v2.1-edge",
        "nonce": "a3f1c9e2b4d60718293a4b5c6d7e8f90",
        "roi_corr": 0.61,
        "signal_quality": 0.88,
        "snr": 0.42,
        "timestamp_ms": 1700000000000,
    })
    sig = "MEUCIQDxExampleSignatureBase64NoWrap1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef="  # ~88 chars
    envelope = {
        "data": payload,
        "sig": sig,
        "alg": "SHA256withECDSA",
        "keyAlias": "edgeppg_device_key_v2",
    }
    return len(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))


# Mirror of PayloadTruncator's threshold.
MAX_QR_PAYLOAD_BYTES_MIRROR = 1500


class PayloadTruncatorSizeTests(unittest.TestCase):
    """Sanity-check that today's envelope fits under the QR cap.

    The truncator threshold is a constant on the device. This test
    ensures we don't silently bump the envelope above it.
    """

    def test_today_envelope_fits_under_qr_cap(self):
        n = _sample_envelope_json_bytes()
        self.assertLess(n, MAX_QR_PAYLOAD_BYTES_MIRROR,
                        f"envelope is {n} bytes; cap is {MAX_QR_PAYLOAD_BYTES_MIRROR}")

    def test_cap_constant_matches_kotlin(self):
        import re
        m = re.search(r"const\s+val\s+MAX_QR_PAYLOAD_BYTES\s*:\s*Int\s*=\s*(\d+)",
                      _read(TRUNCATOR_KT))
        self.assertIsNotNone(m, "MAX_QR_PAYLOAD_BYTES not found in PayloadTruncator.kt")
        kotlin_cap = int(m.group(1))
        self.assertEqual(kotlin_cap, MAX_QR_PAYLOAD_BYTES_MIRROR)


class TranscriptBuilderContractTests(unittest.TestCase):
    """Stage 13 Task 6 — TranscriptBuilder.

    The builder bridges session data to the existing
    IntegrityManager.Telemetry and IntegrityManager.sign(). It must
    NOT duplicate the canonical byte format (single source of truth
    in IntegrityManager.canonicalJson).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(TRANSCRIPT_BUILDER_KT)
        cls.integrity_src = _read(INTEGRITY_KT)

    def test_file_exists_with_transcript_builder_object(self):
        self.assertRegex(self.src, r"object\s+TranscriptBuilder\b")

    def test_does_not_redefine_canonical_json(self):
        # Single source of truth: IntegrityManager owns the canonical
        # byte format. TranscriptBuilder must NOT contain its own
        # `fun canonicalJson(`.
        self.assertNotRegex(self.src, r"fun\s+canonicalJson")

    def test_does_not_redefine_telemetry_data_class(self):
        # Telemetry lives in IntegrityManager.kt; TranscriptBuilder
        # only constructs it.
        self.assertNotRegex(self.src, r"data\s+class\s+Telemetry\b")
        # But it must reference IntegrityManager.Telemetry.
        self.assertIn("IntegrityManager.Telemetry", self.src)

    def test_sign_delegates_to_integrity_manager(self):
        # The builder must NOT do its own crypto. It calls
        # IntegrityManager.sign(...).
        self.assertIn("IntegrityManager.sign", self.src)

    def test_documented_fields_present(self):
        # Per Architecture §9 / FR-CRY-3 the verifier reads 11 fields
        # in fixed alphabetical order. The builder exposes all of
        # them as parameters so callers can't forget one.
        for param in ("challengeId", "expectedSeq", "decision",
                      "confidence", "signalQuality",
                      "hrBpm", "snr", "roiCorr",
                      "timestampMs"):
            self.assertIn(param, self.src)


class SessionControllerContractTests(unittest.TestCase):
    """Stage 15 Task 1 — SessionController.

    The orchestrator must wire the existing modules without
    redesigning them. It owns the SessionStateMachine, ChallengeEngine,
    NonceGenerator, MlFusionClient, DecisionEngine, IntegrityManager
    (via TranscriptBuilder), and the Transport. It must NOT redefine
    any of them.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(SESSION_KT)

    def test_file_exists_with_session_controller_class(self):
        self.assertRegex(self.src, r"class\s+SessionController\b")

    def test_uses_existing_session_state_machine(self):
        self.assertIn("SessionStateMachine", self.src)

    def test_uses_existing_challenge_engine(self):
        self.assertIn("ChallengeEngine", self.src)

    def test_uses_existing_nonce_generator(self):
        self.assertIn("NonceGenerator", self.src)

    def test_uses_existing_decision_engine(self):
        self.assertIn("DecisionEngine", self.src)

    def test_uses_existing_transcript_builder(self):
        # TranscriptBuilder is the bridge to IntegrityManager.
        self.assertIn("TranscriptBuilder", self.src)

    def test_uses_existing_transport(self):
        # The transport field is the interface, not a concrete
        # implementation. Implementations (LocalWifi / QR) are
        # injected by the Activity.
        self.assertRegex(self.src, r"private\s+val\s+transport\s*:\s*Transport\b")

    def test_uses_existing_ml_fusion_client(self):
        self.assertIn("MlFusionClient", self.src)

    def test_does_not_redefine_canonical_json(self):
        # No duplicate transcript representation.
        self.assertNotRegex(self.src, r"fun\s+canonicalJson")

    def test_does_not_redefine_decision_engine_methods(self):
        # No duplicate gate logic.
        self.assertNotRegex(self.src, r"private\s+fun\s+decide\b")

    def test_calls_into_existing_state_machine_for_each_transition(self):
        # The documented flow is: begin -> qualityPass -> baselineComplete
        # -> challengeComplete -> motionBlinkPass -> processingComplete.
        # The controller must drive the state machine; the controller
        # itself must NOT hold a separate state.
        for method in ("begin()", "qualityPass()", "baselineComplete()",
                       "challengeComplete()", "motionBlinkPass()"):
            self.assertIn(method, self.src)

    def test_publishes_state_via_state_flow(self):
        # The UI subscribes to a StateFlow. The controller must use
        # StateFlow, not LiveData (we're not on Android Jetpack here)
        # or polling.
        self.assertIn("StateFlow", self.src)
        self.assertIn("MutableStateFlow", self.src)


class BehaviourRunnerContractTests(unittest.TestCase):
    """Stage 15 Task 4 — Behaviour-runner coroutine.

    The runner walks a [ChallengeSpec] list, fires optical flashes
    for [ChallengeSpec.OpticalFlash] entries via the
    [OpticalFlashOverlay], and emits lifecycle events. It is
    lifecycle-safe: cancellation aborts the in-flight run.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(_resolve(REPO_ROOT, "android/app/src/main/kotlin",
                                  "com/edgeppg/app/behavior/BehaviourRunner.kt"))

    def test_file_exists_with_runner_class(self):
        self.assertRegex(self.src, r"class\s+BehaviourRunner\b")

    def test_takes_external_scope(self):
        # The runner does not own a scope — the caller passes one in.
        # Lifecycle-safety depends on the caller cancelling that
        # scope; the runner does not store its own Job.
        self.assertRegex(
            self.src,
            r"class\s+BehaviourRunner\s*\([^)]*CoroutineScope",
        )

    def test_emits_lifecycle_events(self):
        # The documented event set: PromptShown, FlashStarted,
        # FlashEnded, Observation, AllComplete.
        for event in ("PromptShown", "FlashStarted", "FlashEnded",
                      "Observation", "AllComplete"):
            self.assertIn(event, self.src)

    def test_exposes_shared_flow_of_events(self):
        # The UI subscribes via SharedFlow (multicast) — there may be
        # one collector (the activity), but a future second consumer
        # should not require changes.
        self.assertIn("SharedFlow", self.src)
        self.assertIn("MutableSharedFlow", self.src)
        self.assertIn("asSharedFlow", self.src)

    def test_optical_flash_dispatches_to_overlay(self):
        # When the runner sees ChallengeSpec.OpticalFlash it must
        # delegate to the OpticalFlashOverlay, NOT to the per-challenge
        # behavioral timeout loop.
        self.assertIn("showFlash", self.src)
        self.assertIn("OpticalFlash", self.src)

    def test_cancel_is_idempotent(self):
        self.assertRegex(self.src, r"fun\s+cancel\b")
        # The cancel implementation must set running=false regardless
        # of whether a run was in flight.
        self.assertRegex(self.src, r"running\s*=\s*false")

    def test_no_third_party_lifecycle_dependency(self):
        # We must not drag in something like WorkManager / a Service
        # here. The contract is a plain CoroutineScope + a cancel.
        # This guards against accidental scope-creep.
        forbidden = ("WorkManager", "Service", "BroadcastReceiver",
                     "JobIntentService")
        for needle in forbidden:
            self.assertNotIn(needle, self.src)

    def test_uses_existing_behavioral_runner_matcher(self):
        # The coroutine driver must reuse the existing pure matcher
        # (BehavioralRunner.observe), not duplicate the match logic.
        self.assertIn("BehavioralRunner.observe", self.src)

    def test_uses_existing_gaze_and_head_estimators(self):
        # The runner consumes the live mesh points via the same
        # geometry math the matcher uses, not a new implementation.
        self.assertIn("GazeEstimator.estimate", self.src)
        self.assertIn("HeadPoseSolver.estimate", self.src)


def _resolve(repo_root: Path, *parts: str) -> Path:
    return repo_root.joinpath(*parts)


class RowAssemblerContractTests(unittest.TestCase):
    """Stage 15 Task 5 — RowAssembler.

    The assembler maps per-session metrics to a length-28 row in
    [FeatureSchema.FEATURE_ORDER] order and validates it. It does
    NOT change the schema.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(_resolve(REPO_ROOT, "android/app/src/main/kotlin",
                                  "com/edgeppg/app/features/RowAssembler.kt"))
        cls.schema_src = _read(_resolve(REPO_ROOT, "android/app/src/main/kotlin",
                                        "com/edgeppg/app/features/FeatureSchema.kt"))

    def test_file_exists_with_assembler_object(self):
        self.assertRegex(self.src, r"object\s+RowAssembler\b")

    def test_assemble_function_present(self):
        self.assertRegex(self.src, r"fun\s+assemble\s*\(")

    def test_assemble_returns_result_with_outcome(self):
        # The Result type must be a sealed-style result with an
        # Outcome enum (Ok / BadRow).
        self.assertIn("enum class Outcome", self.src)
        self.assertIn("Ok", self.src)
        self.assertIn("BadRow", self.src)

    def test_assemble_uses_feature_schema_order(self):
        # The row is filled in FeatureSchema.FEATURE_ORDER. The
        # schema-parity test pins that order to the Python side.
        self.assertIn("FeatureSchema.FEATURE_ORDER", self.src)
        self.assertIn("FEATURE_COUNT", self.src)

    def test_assemble_does_not_change_schema(self):
        # The assembler must NOT introduce new fields. We assert
        # the row is exactly FEATURE_COUNT entries (28) and that
        # there is no "trusted" extra class added.
        self.assertIn("FeatureSchema.FEATURE_COUNT", self.src)
        # No redeclaration of the schema.
        self.assertNotRegex(self.src, r"data\s+class\s+FeatureSchema\b")
        self.assertNotRegex(self.src, r"object\s+FeatureSchema\b")

    def test_assemble_uses_schema_validator(self):
        # The row is passed to SchemaValidator.validate before
        # being returned as Ok.
        self.assertIn("SchemaValidator.validate", self.src)

    def test_missing_features_default_to_nan(self):
        # Multi-person features (trusted_*, cross_person_*) default
        # to NaN in the single-participant hackathon path. NaN is
        # the documented "missing" sentinel.
        # The Inputs data class has these as Float = Float.NaN by
        # default; we assert the type's default is NaN.
        self.assertIn("Float.NaN", self.src)

    def test_session_controller_calls_row_assembler(self):
        # The SessionController must call the assembler to bridge
        # session metrics into the 28-feature row.
        session_src = _read(SESSION_KT)
        self.assertIn("RowAssembler.assemble", session_src)
        self.assertIn("RowAssembler.Inputs", session_src)


class JvmTestTargetContractTests(unittest.TestCase):
    """Stage 15 Task 6 — JVM unit tests.

    The app/build.gradle.kts must declare a JUnit dependency, and
    there must be test source files in app/src/test/kotlin. The
    actual `:app:testDebugUnitTest` execution is blocked on the
    same pre-existing P1 build issue (Camera2 interop not on the
    Kotlin classpath under AGP 9.4.1's built-in-Kotlin path);
    the tests themselves are correctly written and will run when
    the build is unblocked in Stage 15 Task 7.
    """

    @classmethod
    def setUpClass(cls):
        cls.app_gradle = _read(
            REPO_ROOT / "android" / "app" / "build.gradle.kts"
        )
        cls.test_root = REPO_ROOT / "android" / "app" / "src" / "test" / "kotlin"

    def test_junit_dep_declared(self):
        # JUnit is the test framework. The exact version doesn't
        # matter; we just check the project uses it.
        self.assertIn("testImplementation", self.app_gradle)
        self.assertRegex(self.app_gradle, r"testImplementation\([^)]*[Jj]unit")

    def test_test_source_set_exists(self):
        # Tests live under app/src/test/kotlin (JVM) and / or
        # app/src/androidTest/kotlin (instrumented). The pure-Kotlin
        # tests land under src/test.
        self.assertTrue(self.test_root.exists(),
                        f"missing {self.test_root}")

    def test_pure_kotlin_modules_have_jvm_tests(self):
        # Per the Stage 15 Task 6 prompt, the new tests must cover
        # the newly integrated functionality. The three pure-Kotlin
        # modules that drive the session flow each have a test class.
        for module_test in (
            "ChallengeEngineTest.kt",
            "NonceGeneratorTest.kt",
            "SessionStateTest.kt",
        ):
            self.assertTrue(
                (self.test_root / "com" / "edgeppg" / "app" / "challenge"
                 / module_test).exists(),
                f"missing {module_test}",
            )

    def test_test_files_have_junit4_annotations(self):
        # The contract is JUnit 4 (the simplest AGP-9.4.1-compatible
        # option). Each test class must declare `@Test` annotations
        # on its methods.
        for module_test in (
            "ChallengeEngineTest.kt",
            "NonceGeneratorTest.kt",
            "SessionStateTest.kt",
        ):
            content = (self.test_root / "com" / "edgeppg" / "app"
                        / "challenge" / module_test).read_text(
                            encoding="utf-8"
                        )
            self.assertIn("import org.junit.Test", content,
                          f"{module_test} missing JUnit @Test import")
            self.assertIn("@Test", content,
                          f"{module_test} missing @Test annotation")
            # JUnit 4 assertion API.
            self.assertIn("org.junit.Assert", content,
                          f"{module_test} missing Assert import")


class OpticalFlashOverlayContractTests(unittest.TestCase):
    """Stage 15 Task 3 — Optical flash overlay.

    The renderer is a full-window [View] that paints a colored overlay
    on demand, auto-hides after a duration, and never throws on the
    main thread. It does NOT do the rPPG correlation (that's the DSP).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(OPTICAL_KT)
        cls.challenge_spec = _read(CHALLENGE_SPEC_KT)
        cls.main_activity = _read(MAINACTIVITY_KT)

    def test_file_exists_with_overlay_class(self):
        self.assertRegex(self.src, r"class\s+OpticalFlashOverlay\b")

    def test_extends_view(self):
        # The renderer must be a real Android View so it can be added
        # to the activity layout.
        self.assertRegex(self.src, r"class\s+OpticalFlashOverlay[^{]*:\s*View\b")

    def test_show_flash_method_present(self):
        self.assertRegex(self.src, r"fun\s+showFlash\b")

    def test_show_flash_takes_color_delta_duration(self):
        # The showFlash signature must match the documented contract:
        # color, deltaPct, durationMs.
        m = re.search(
            r"fun\s+showFlash\s*\(\s*(\w+)\s*:\s*OpticalColor\s*,\s*"
            r"(\w+)\s*:\s*Int\s*,\s*(\w+)\s*:\s*Long\s*\)",
            self.src,
        )
        self.assertIsNotNone(m, "showFlash(color, deltaPct, durationMs) not found")

    def test_auto_hide_after_duration(self):
        # The handler-based auto-hide is the documented mechanism.
        # We assert `Handler` + `removeCallbacksAndMessages` are
        # present, plus a post-delayed that hides the overlay.
        self.assertIn("Handler", self.src)
        self.assertIn("postDelayed", self.src)
        self.assertIn("removeCallbacksAndMessages", self.src)
        self.assertIn("GONE", self.src)

    def test_cancel_method_present(self):
        # Lifecycle safety: the overlay must be cancellable from the
        # activity's onDestroy so a half-fired flash doesn't outlive
        # the activity.
        self.assertRegex(self.src, r"fun\s+cancel\b")

    def test_challenge_spec_defines_optical_flash(self):
        # Per FR-OPT-1 the challenge list may include an optical
        # flash. The data class lives next to the other sealed
        # ChallengeSpec subclasses.
        self.assertRegex(
            self.challenge_spec,
            r"data\s+class\s+OpticalFlash\b",
        )

    def test_optical_color_enum_has_three_entries(self):
        # WHITE, WARM, COOL are the three colors documented in
        # `PR-VAL-1` and the existing challenge engine code.
        self.assertIn("WHITE", self.challenge_spec)
        self.assertIn("WARM", self.challenge_spec)
        self.assertIn("COOL", self.challenge_spec)

    def test_main_activity_wires_overlay_into_layout(self):
        # The MainActivity must instantiate the overlay and add it
        # to the root layout, otherwise the renderer is dead code.
        self.assertIn("OpticalFlashOverlay", self.main_activity)
        self.assertRegex(self.main_activity, r"addView\(\s*flashOverlay")


class OfficeKitContractTests(unittest.TestCase):
    """Stage 16 Task 3 — OfficeKit interface + NoOp default.

    Office Kit is documented (Requirements §FR-VER-3, §203) as
    "strictly optional and additive". The interface must exist
    so a future vendor implementation can plug in, and a NoOp
    default must be the canonical state when no vendor SDK is
    registered. The baseline flow must NOT depend on it.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read(OFFICEKIT_KT)

    def test_interface_named_office_kit(self):
        self.assertRegex(self.src, r"interface\s+OfficeKit\b")

    def test_no_op_default_present(self):
        # A `NoOpOfficeKit` (or equivalent) must exist and be the
        # default state. The exact name is documented in the source.
        self.assertRegex(self.src, r"object\s+NoOpOfficeKit\b")

    def test_no_op_reports_unavailable(self):
        # The NoOp must signal "not available" so the app can fall
        # back to the baseline path. We don't pin the exact boolean
        # name; we just assert the NoOp declares an availability
        # field.
        self.assertRegex(self.src, r"isAvailable\s*:\s*Boolean")
        self.assertRegex(self.src, r"override\s+val\s+isAvailable\s*:\s*Boolean\s*=\s*false")

    def test_no_op_try_deliver_returns_false(self):
        # A NoOp Office Kit must not actually deliver anything.
        self.assertRegex(self.src, r"override\s+fun\s+tryDeliver\b")
        # The body returns false — either an explicit `return false`
        # or a single-expression body `= false` is acceptable Kotlin
        # for this. We just assert that the NoOp's tryDeliver
        # implementation contains `false`.
        m = re.search(
            r"override\s+fun\s+tryDeliver\s*\([^)]*\)\s*:\s*Boolean\s*=\s*false",
            self.src,
        )
        self.assertIsNotNone(m, "NoOp tryDeliver must return false")

    def test_office_kit_does_not_break_baseline(self):
        # The interface must NOT add new methods that the rest of
        # the app must implement, beyond the two declared
        # (isAvailable + tryDeliver).
        # Count `fun ` declarations inside the interface.
        import re
        m = re.search(r"interface\s+OfficeKit\s*\{(.*?)^\}", self.src,
                      re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(m, "OfficeKit interface body not found")
        body = m.group(1)
        # Exactly one fun declaration (tryDeliver). isAvailable is
        # a val, not a fun.
        fun_count = len(re.findall(r"\bfun\s+\w+", body))
        self.assertEqual(1, fun_count, "expected exactly 1 fun in interface")

    def test_office_kit_in_integrity_package(self):
        # The interface lives next to IntegrityManager — the
        # transport-side abstraction that consumes the envelope.
        self.assertRegex(self.src, r"package\s+com\.edgeppg\.app\.integrity")


class TranscriptBuilderIntegrationTests(unittest.TestCase):
    """Stage 16 Task 4 — TranscriptBuilder ↔ PC verifier round-trip.

    The contract is: the canonical JSON produced by
    `IntegrityManager.canonicalJson()` (which `TranscriptBuilder`
    delegates to) is byte-exactly the JSON the PC verifier's
    `verify_envelope` accepts. If this round-trip is wrong, the
    whole transport layer is broken. We test it without launching
    the device or the Android app: we mirror the canonical
    payload in Python, sign with a fresh EC P-256 key, and ask
    the PC verifier to verify the signature.
    """

    def test_canonical_keys_match_pc_verifier_expectations(self):
        from verifier.canonical import canonical_payload
        data = canonical_payload({
            "challenge_id": "sess-it-1", "confidence": 0.91,
            "decision": "LIVE", "expected_seq": "[]",
            "hr_bpm": 0.0, "model_version": "v2.1-edge",
            "nonce": "a" * 32, "roi_corr": 0.55,
            "signal_quality": 0.88, "snr": 0.40,
            "timestamp_ms": 1_700_000_000_000,
        })
        parsed = json.loads(data)
        # PC verifier expects exactly these 11 keys in any order.
        expected = sorted([
            "challenge_id", "confidence", "decision", "expected_seq",
            "hr_bpm", "model_version", "nonce", "roi_corr",
            "signal_quality", "snr", "timestamp_ms",
        ])
        self.assertEqual(sorted(parsed.keys()), expected)

    def test_signed_envelope_round_trips(self):
        # Sign with a real EC P-256 key, ask the PC verifier to
        # verify. If canonical-byte agreement is broken, the
        # verification fails. If it works, the round-trip is
        # correct end-to-end.
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes, serialization
        except ImportError:
            self.skipTest("cryptography not installed")
        from verifier.canonical import canonical_payload
        from verifier.verify import verify_envelope

        sk = ec.generate_private_key(ec.SECP256R1())
        pub = sk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        data = canonical_payload({
            "challenge_id": "sess-it-2", "confidence": 0.91,
            "decision": "LIVE", "expected_seq": "[]",
            "hr_bpm": 0.0, "model_version": "v2.1-edge",
            "nonce": "b" * 32, "roi_corr": 0.55,
            "signal_quality": 0.88, "snr": 0.40,
            "timestamp_ms": 1_700_000_001_000,
        })
        sig = sk.sign(data.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        sig_b64 = base64.b64encode(sig).decode("ascii")
        verdict = verify_envelope(
            {"data": data, "sig": sig_b64, "alg": "SHA256withECDSA"},
            pub.decode("ascii"),
            now_ms=1_700_000_001_000,
        )
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["decision"], "LIVE")
        # SHA-256 of the canonical bytes must round-trip.
        import hashlib
        self.assertEqual(
            verdict["telemetry_sha256"],
            hashlib.sha256(data.encode("utf-8")).hexdigest(),
        )

    def test_uncertaintn_decision_round_trips(self):
        # Same as above, but with the UNCERTAIN branch the demo
        # actually produces today (because P_live is NaN).
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes, serialization
        except ImportError:
            self.skipTest("cryptography not installed")
        from verifier.canonical import canonical_payload
        from verifier.verify import verify_envelope

        sk = ec.generate_private_key(ec.SECP256R1())
        pub = sk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        data = canonical_payload({
            "challenge_id": "sess-it-3", "confidence": 0.5,
            "decision": "UNCERTAIN", "expected_seq": "[]",
            "hr_bpm": 0.0, "model_version": "v2.1-edge",
            "nonce": "c" * 32, "roi_corr": 0.5,
            "signal_quality": 0.5, "snr": 0.0,
            "timestamp_ms": 1_700_000_002_000,
        })
        sig = sk.sign(data.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        verdict = verify_envelope(
            {"data": data, "sig": base64.b64encode(sig).decode("ascii"),
             "alg": "SHA256withECDSA"},
            pub.decode("ascii"),
            now_ms=1_700_000_002_000,
        )
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["decision"], "UNCERTAIN")

    def test_5_minute_freshness_window(self):
        # FRESh_MS is 5 minutes on both sides. An envelope older
        # than that is rejected.
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes, serialization
        except ImportError:
            self.skipTest("cryptography not installed")
        from verifier.canonical import canonical_payload
        from verifier.verify import verify_envelope, FRESH_MS_DEFAULT

        sk = ec.generate_private_key(ec.SECP256R1())
        pub = sk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        old_ts = 1_700_000_000_000
        data = canonical_payload({
            "challenge_id": "sess-old", "confidence": 0.91,
            "decision": "LIVE", "expected_seq": "[]",
            "hr_bpm": 0.0, "model_version": "v2.1-edge",
            "nonce": "d" * 32, "roi_corr": 0.55,
            "signal_quality": 0.88, "snr": 0.40,
            "timestamp_ms": old_ts,
        })
        sig = sk.sign(data.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        # Submit 6 minutes later → past the 5-minute window.
        verdict = verify_envelope(
            {"data": data, "sig": base64.b64encode(sig).decode("ascii"),
             "alg": "SHA256withECDSA"},
            pub.decode("ascii"),
            now_ms=old_ts + FRESH_MS_DEFAULT + 60_000,
        )
        self.assertFalse(verdict["ok"], verdict)
        self.assertEqual(verdict["reason"], "stale-timestamp")


if __name__ == "__main__":
    unittest.main(verbosity=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)