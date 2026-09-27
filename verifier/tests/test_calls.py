"""EdgePPG PC verifier — call scheduling + Join Call tests.

Phase 1 of `docs/vkyc-call-dashboard-spec.md` (§13.1–13.2).
Stdlib unittest only. All storage goes to a tmp dir so the real
`verifier/calls/` is never touched.

Run with:
    .venv\\Scripts\\python.exe -m verifier.tests.run_tests
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from verifier import calls as call_store  # noqa: E402

NOW = 1_750_000_000_000


class CallStorageTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        call_store.reset_join_nonces()

    def tearDown(self):
        self.tmp.cleanup()
        call_store.reset_join_nonces()

    def test_create_call_ok(self):
        c = call_store.create_call("Jane", "APP-1", "2026-09-27T10:00",
                                   now_ms=NOW, base=self.base)
        self.assertEqual(c["status"], "SCHEDULED")
        self.assertEqual(c["applicant_name"], "Jane")
        self.assertEqual(c["applicant_ref"], "APP-1")
        self.assertTrue(c["call_id"].startswith("call-"))
        # Persisted to disk.
        self.assertTrue((self.base / "calls" / f"{c['call_id']}.json").exists())

    def test_create_call_rejects_blank_fields(self):
        with self.assertRaises(ValueError):
            call_store.create_call("", "APP-1", base=self.base)
        with self.assertRaises(ValueError):
            call_store.create_call("Jane", "  ", base=self.base)

    def test_list_calls_oldest_first_and_survives_restart(self):
        a = call_store.create_call("A", "R-A", now_ms=NOW, base=self.base)
        b = call_store.create_call("B", "R-B", now_ms=NOW + 1000, base=self.base)
        listed = call_store.list_calls(base=self.base)
        self.assertEqual([c["call_id"] for c in listed],
                         [a["call_id"], b["call_id"]])

    def test_set_waiting_ok_and_idempotent(self):
        c = call_store.create_call("Jane", "APP-1", base=self.base)
        out = call_store.set_waiting(c["call_id"], now_ms=NOW, base=self.base)
        self.assertTrue(out["ok"])
        self.assertEqual(out["call"]["status"], "WAITING")
        # Second call is idempotent, not an error.
        out2 = call_store.set_waiting(c["call_id"], now_ms=NOW, base=self.base)
        self.assertTrue(out2["ok"])

    def test_set_waiting_unknown_call(self):
        out = call_store.set_waiting("call-nope", now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "unknown-call")

    def test_set_waiting_bad_state(self):
        c = call_store.create_call("Jane", "APP-1", base=self.base)
        call_store.set_waiting(c["call_id"], now_ms=NOW, base=self.base)
        # Force CONNECTED via a join, then try waiting again.
        join = {
            "type": "CALL_JOIN_REQUEST", "call_id": c["call_id"],
            "applicant_ref": "APP-1", "nonce": "n" * 16,
            "timestamp_ms": NOW,
        }
        self.assertTrue(call_store.handle_join(join, now_ms=NOW,
                                               base=self.base)["ok"])
        out = call_store.set_waiting(c["call_id"], now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])
        self.assertTrue(out["reason"].startswith("bad-state:"))


class JoinCallTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        call_store.reset_join_nonces()
        self.call = call_store.create_call("Jane", "APP-1", base=self.base)
        call_store.set_waiting(self.call["call_id"], now_ms=NOW, base=self.base)

    def tearDown(self):
        self.tmp.cleanup()
        call_store.reset_join_nonces()

    def _join(self, **over):
        p = {
            "type": "CALL_JOIN_REQUEST",
            "call_id": self.call["call_id"],
            "applicant_ref": "APP-1",
            "nonce": "n" * 16,
            "timestamp_ms": NOW,
        }
        p.update(over)
        return call_store.handle_join(p, now_ms=NOW, base=self.base)

    def test_join_ok_returns_start_verification(self):
        out = self._join()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["type"], "CALL_JOIN_RESPONSE")
        self.assertEqual(out["action"], "START_VERIFICATION")
        self.assertEqual(len(out["session_seed"]), 64)
        self.assertEqual(len(out["verifier_nonce"]), 32)
        # Call moved to CONNECTED.
        self.assertEqual(
            call_store.load_call(self.call["call_id"],
                                 base=self.base)["status"], "CONNECTED")

    def test_join_unknown_call(self):
        out = self._join(call_id="call-nope")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "unknown-call")

    def test_join_applicant_mismatch(self):
        out = self._join(applicant_ref="APP-999")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "join-applicant-mismatch")

    def test_join_not_waiting(self):
        c2 = call_store.create_call("Bob", "APP-2", base=self.base)
        out = call_store.handle_join({
            "type": "CALL_JOIN_REQUEST", "call_id": c2["call_id"],
            "applicant_ref": "APP-2", "nonce": "m" * 16,
            "timestamp_ms": NOW,
        }, now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "not-yet-waiting")

    def test_join_scheduled_past_time_allowed(self):
        c2 = call_store.create_call("Bob", "APP-2", base=self.base)
        # Rewrite the record with a past scheduled epoch.
        rec = call_store.load_call(c2["call_id"], base=self.base)
        rec["scheduled_epoch_ms"] = NOW - 60_000
        call_store.save_call(rec, base=self.base)
        out = call_store.handle_join({
            "type": "CALL_JOIN_REQUEST", "call_id": c2["call_id"],
            "applicant_ref": "APP-2", "nonce": "p" * 16,
            "timestamp_ms": NOW,
        }, now_ms=NOW, base=self.base)
        self.assertTrue(out["ok"], out)

    def test_join_stale_timestamp(self):
        out = self._join(timestamp_ms=NOW - 6 * 60 * 1000)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "join-stale-timestamp")

    def test_join_replay_nonce_rejected(self):
        self.assertTrue(self._join(nonce="r" * 16)["ok"])
        # New call in WAITING, same nonce → replay.
        c2 = call_store.create_call("Bob", "APP-2", base=self.base)
        call_store.set_waiting(c2["call_id"], now_ms=NOW, base=self.base)
        out = call_store.handle_join({
            "type": "CALL_JOIN_REQUEST", "call_id": c2["call_id"],
            "applicant_ref": "APP-2", "nonce": "r" * 16,
            "timestamp_ms": NOW,
        }, now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "join-replay-nonce")

    def test_join_missing_fields(self):
        for bad in ({"type": "CALL_JOIN_REQUEST"},
                    {"type": "CALL_JOIN_REQUEST", "call_id": "x"}):
            out = call_store.handle_join(bad, now_ms=NOW, base=self.base)
            self.assertFalse(out["ok"])

    def test_join_contains_no_biometrics_or_results(self):
        out = self._join()
        blob = json.dumps(out)
        for forbidden in ("LIVE", "SPOOF", "UNCERTAIN", "feature",
                          "frame", "key", "sig"):
            self.assertNotIn(forbidden, blob)


class LinkResultTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        call_store.reset_join_nonces()

    def tearDown(self):
        self.tmp.cleanup()
        call_store.reset_join_nonces()

    def test_link_connected_to_completed(self):
        c = call_store.create_call("Jane", "APP-1", base=self.base)
        call_store.set_waiting(c["call_id"], base=self.base)
        call_store.handle_join({
            "type": "CALL_JOIN_REQUEST", "call_id": c["call_id"],
            "applicant_ref": "APP-1", "nonce": "z" * 16,
            "timestamp_ms": NOW,
        }, now_ms=NOW, base=self.base)
        out = call_store.link_verification_result(
            c["call_id"], "UNCERTAIN", "receipts/x.json",
            now_ms=NOW, base=self.base)
        self.assertTrue(out["ok"])
        self.assertEqual(out["call"]["status"], "COMPLETED")
        self.assertEqual(out["call"]["result"]["decision"], "UNCERTAIN")

    def test_link_wrong_state(self):
        c = call_store.create_call("Jane", "APP-1", base=self.base)
        out = call_store.link_verification_result(
            c["call_id"], "LIVE", None, now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])
        self.assertTrue(out["reason"].startswith("bad-state:"))

    def test_link_unknown_call(self):
        out = call_store.link_verification_result(
            "call-nope", "LIVE", None, now_ms=NOW, base=self.base)
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
