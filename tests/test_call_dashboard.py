"""VKYC call dashboard contract tests (spec docs/vkyc-call-dashboard-spec.md).

Phase 2. Source-parsing contracts only — no network, no device:
  * CallController surface (§5.1, §8): CallState enum, CallView,
    setScheduled/join/markCompleted/reset, Transport.send reuse,
    no org.json (JVM-safe), no new transport.
  * SessionController.start(externalSeed) overload (§10.2).
  * TransportResult.rawResponse for Join responses.
  * MainActivity dashboard wiring (§6, §11.1).
  * Server Join branch accepts envelope-wrapped payloads (§8.4).

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _kt(*parts: str) -> str:
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


CALL_KT = _kt("android", "app", "src", "main", "kotlin",
              "com", "edgeppg", "app", "session", "CallController.kt")
SESS_KT = _kt("android", "app", "src", "main", "kotlin",
              "com", "edgeppg", "app", "session", "SessionController.kt")
MAIN_KT = _kt("android", "app", "src", "main", "kotlin",
              "com", "edgeppg", "app", "MainActivity.kt")
TRANSPORT_KT = _kt("android", "app", "src", "main", "kotlin",
                   "com", "edgeppg", "app", "transport", "Transport.kt")
LOCALWIFI_KT = _kt("android", "app", "src", "main", "kotlin",
                   "com", "edgeppg", "app", "transport", "LocalWifiTransport.kt")
SERVER_PY = (REPO_ROOT / "verifier" / "server.py").read_text(encoding="utf-8")


class CallControllerContractTests(unittest.TestCase):
    """CallState machine + Join Call reuse of Transport (§5.1, §8, §9)."""

    def test_call_state_enum_has_spec_states(self):
        for s in ("IDLE", "SCHEDULED", "JOINING", "CONNECTED",
                  "COMPLETED", "FAILED"):
            self.assertRegex(CALL_KT, rf"\b{s}\b",
                             f"CallState missing {s}")

    def test_call_view_fields(self):
        for f in ("callId", "applicantRef", "scheduledTime",
                  "sessionSeed", "lastError"):
            self.assertRegex(CALL_KT, rf"\b{f}\b",
                             f"CallView missing {f}")

    def test_public_api_surface(self):
        for m in (r"fun\s+setScheduled\s*\(",
                  r"suspend\s+fun\s+join\s*\(",
                  r"fun\s+markCompleted\s*\(",
                  r"fun\s+reset\s*\("):
            self.assertRegex(CALL_KT, m, f"missing {m}")

    def test_join_uses_transport_send(self):
        # §9: no second transport. The only wire path is
        # Transport.send().
        self.assertRegex(CALL_KT, r"transport\.send\s*\(")
        self.assertNotRegex(CALL_KT, r"OkHttpClient|WebSocket|Socket")

    def test_join_wraps_envelope_structure(self):
        # §8.4: reuse IntegrityManager.Envelope with the join JSON
        # as `data`.
        self.assertIn("IntegrityManager.Envelope", CALL_KT)
        self.assertIn("CALL_JOIN_REQUEST", CALL_KT)

    def test_no_org_json_import(self):
        # org.json is Android-only at runtime; CallController must
        # stay plain-JVM so the JUnit tests can construct payloads.
        self.assertNotIn("import org.json", CALL_KT)

    def test_state_flow_exposed(self):
        self.assertIn("StateFlow", CALL_KT)
        self.assertIn("MutableStateFlow", CALL_KT)

    def test_join_payload_has_exactly_the_control_keys(self):
        # §8.3: control fields only. Extract the key names from the
        # buildJoinPayload string template and assert the exact set —
        # no feature vectors, frames, keys, results, or templates.
        m = re.search(
            r"fun\s+buildJoinPayload\(\s*\n\s*callId:[^)]+\)\s*:\s*String\s*=(.*?)(?=\n\s*(?:/\*\*|\Z))",
            CALL_KT, re.DOTALL)
        self.assertIsNotNone(m, "buildJoinPayload template not found")
        keys = set(re.findall(r'\\"([a-z_]+)\\":', m.group(1)))
        self.assertEqual(
            keys, {"type", "call_id", "applicant_ref", "nonce",
                   "timestamp_ms"})


class SessionStartSeedTests(unittest.TestCase):
    """start(externalSeed) overload (§10.2)."""

    def test_start_overload_with_external_seed(self):
        self.assertRegex(
            SESS_KT, r"fun\s+start\s*\(\s*externalSeed\s*:\s*String\?\s*\)")

    def test_plain_start_delegates(self):
        self.assertRegex(SESS_KT, r"fun\s+start\s*\(\s*\)[^{]*start\(null\)")

    def test_blank_seed_falls_back_to_generated(self):
        self.assertIn("isNullOrBlank", SESS_KT)


class TransportResultJoinTests(unittest.TestCase):
    """rawResponse carries Join responses without schema change."""

    def test_raw_response_field_present(self):
        self.assertRegex(TRANSPORT_KT, r"val\s+rawResponse\s*:")

    def test_local_wifi_populates_raw_response(self):
        self.assertIn("rawResponse", LOCALWIFI_KT)

    def test_documented_verdict_fields_untouched(self):
        for f in ("val\\s+ok\\s*:", "val\\s+reason\\s*:",
                  "val\\s+decision\\s*:", "val\\s+telemetry\\s*:",
                  "val\\s+httpStatus\\s*:", "val\\s+roundTripMs\\s*:"):
            self.assertRegex(TRANSPORT_KT, f)


class MainActivityDashboardTests(unittest.TestCase):
    """Pre-session dashboard in the single Activity (§6, §11.1)."""

    def test_dashboard_views_present(self):
        for v in ("dashboardView", "sessionView", "callIdInput",
                  "applicantRefInput", "callStatusView", "joinButton"):
            self.assertIn(v, MAIN_KT)

    def test_join_handler_present(self):
        self.assertRegex(MAIN_KT, r"fun\s+onJoinClicked\s*\(")

    def test_shared_transport_instance(self):
        # §9: one transport for session + Join. The controller and
        # the join path must share a single LocalWifiTransport.
        self.assertRegex(
            MAIN_KT, r"private\s+val\s+transport\s*:\s*Transport\s*=\s*LocalWifiTransport\(\)")
        self.assertIn("SessionController(transport = transport)", MAIN_KT)
        self.assertIn("callController.join(transport)", MAIN_KT)

    def test_seed_threaded_into_session_start(self):
        self.assertIn("pendingSessionSeed", MAIN_KT)
        self.assertIn("controller.start(pendingSessionSeed)", MAIN_KT)

    def test_no_second_activity(self):
        # Only MainActivity itself may be declared as an Activity
        # subclass in this file.
        found = re.findall(r"class\s+(\w+)\s*:[^{]*ComponentActivity\s*\(\)", MAIN_KT)
        self.assertEqual(found, ["MainActivity"])

    def test_done_marks_call_completed(self):
        self.assertIn("callController.markCompleted()", MAIN_KT)


class ServerJoinUnwrapTests(unittest.TestCase):
    """Server accepts envelope-wrapped Join Calls (§8.4)."""

    def test_unwrap_branch_present(self):
        self.assertIn("join_payload", SERVER_PY)
        self.assertIn("CALL_JOIN_REQUEST", SERVER_PY)

    def test_plain_join_still_accepted(self):
        # Backward compat: a bare join dict (curl-style) must still
        # route to handle_join. The branch checks env.get("type")
        # first, before attempting the unwrap.
        m = re.search(
            r'if env\.get\("type"\) == "CALL_JOIN_REQUEST":\s*\n\s*join_payload = env',
            SERVER_PY)
        self.assertIsNotNone(m)

    def test_verification_flow_untouched(self):
        self.assertIn("verdict = verify_envelope(env, self.pubkey)", SERVER_PY)

    def test_call_id_link_present(self):
        self.assertIn("link_verification_result", SERVER_PY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
