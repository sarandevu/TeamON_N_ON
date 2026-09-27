"""Stage 5 / 7 — Challenge engine tests (Python mirror).

The Kotlin `ChallengeEngine.kt`, `NonceGenerator.kt`, and
`SessionStateMachine.kt` are mirrored here in Python so the algorithms
can be unit-tested in the verified venv. When an Android test runner is
provisioned, the same logic must be encoded as Kotlin/JUnit tests; the
Python mirror is the source of truth for the documented behaviour.

Behaviour verified:
  - Sequence length is configurable and respects the 4..8 range.
  - Same seed → same sequence (deterministic).
  - Different seeds → different sequences (per-session unpredictability).
  - Applicant vs trusted use independent streams (different salts).
  - Sequences always include at least one RemainStill (motion gate).
  - Sequences mix modalities.
  - Nonce / seed / sessionId have the documented sizes.
  - SessionStateMachine follows the documented path:
    CAPTURE → QUALITY_CHECK → BASELINE → RANDOMIZED_CHALLENGE →
    MOTION_BLINK_CHECK → PROCESSING → DONE
    with configurable retries on quality / motion-blank failures.
"""

from __future__ import annotations

import hashlib
import random
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---- Mirror of Kotlin ----------------------------------------------------

CHALLENGE_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                / "com" / "edgeppg" / "app" / "challenge" / "ChallengeEngine.kt")
NONCE_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
            / "com" / "edgeppg" / "app" / "challenge" / "NonceGenerator.kt")
SESSION_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
              / "com" / "edgeppg" / "app" / "challenge" / "SessionState.kt")


GAZE = ["LEFT", "RIGHT", "UP", "DOWN", "CENTER"]
HEAD = ["TURN_LEFT", "TURN_RIGHT", "TURN_UP", "TURN_DOWN", "NOD", "SHAKE_NO"]
HAND = ["RAISE_LEFT", "RAISE_RIGHT", "POINT", "THUMBS_UP", "OPEN_PALM"]


def _seeded_random(seed_hex: str, salt: str) -> random.Random:
    """Mirror of ChallengeEngine.seededRng."""
    digest = hashlib.sha256(bytes.fromhex(seed_hex) + salt.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big", signed=False)
    return random.Random(seed)


def _generate(seed_hex: str, salt: str, length: int = 5) -> list[str]:
    """Return a list of `ChallengeSpec` short forms."""
    if not (4 <= length <= 8):
        raise ValueError(f"sequenceLength must be 4..8; got {length}")
    rng = _seeded_random(seed_hex, salt)
    out: list[str] = []
    prev_mod: Optional[str] = None
    for i in range(length):
        if i == length - 1 and prev_mod != "still":
            modality = "still"
        else:
            r = rng.random()
            if r < 0.35:
                modality = "gaze"
            elif r < 0.65:
                modality = "head"
            elif r < 0.85:
                modality = "hand"
            else:
                modality = "still"
        # Mirror of Kotlin: retry draw up to 8 times if it would repeat.
        if modality != "still" and prev_mod is not None:
            attempts = 0
            while modality == prev_mod and attempts < 8:
                r = rng.random()
                if r < 0.35:
                    modality = "gaze"
                elif r < 0.65:
                    modality = "head"
                elif r < 0.85:
                    modality = "hand"
                else:
                    modality = "still"
                attempts += 1
        if modality == "gaze":
            out.append(f"GAZE:{rng.choice(GAZE)}")
        elif modality == "head":
            out.append(f"HEAD:{rng.choice(HEAD)}")
        elif modality == "hand":
            out.append(f"HAND:{rng.choice(HAND)}")
        else:
            duration = 1500 + rng.randint(0, 1499)
            out.append(f"STILL:{duration}")
        prev_mod = modality
    if not any(s.startswith("STILL:") for s in out):
        out[-1] = "STILL:2000"
    return out


def _applicant(seed_hex: str) -> list[str]:
    return _generate(seed_hex, salt="applicant", length=5)


def _trusted(seed_hex: str) -> list[str]:
    return _generate(seed_hex, salt="trusted", length=5)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---- Tests ----------------------------------------------------------------

class ChallengeEngineSourceTests(unittest.TestCase):
    """The Kotlin source must declare the documented constants and the
    documented modality probabilities."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_source(CHALLENGE_KT)

    def test_sequence_length_default_is_5(self):
        m = re.search(r'sequenceLength\s*:\s*Int\s*=\s*(\d+)', self.src)
        self.assertIsNotNone(m, "sequenceLength default not found")
        self.assertEqual(int(m.group(1)), 5)

    def test_sequence_length_min_4_max_8_enforced(self):
        self.assertIn("sequenceLength in 4..8", self.src)
        self.assertIn("4..8", self.src)

    def test_modality_probabilities_documented(self):
        # The Kotlin source spells out the modality pick. We don't pin the
        # exact numbers (they're heuristic starting values) but assert the
        # boundary thresholds 0.35, 0.65, 0.85 are present.
        for bound in ("0.35", "0.65", "0.85"):
            self.assertIn(bound, self.src,
                f"modality probability bound {bound} missing")

    def test_modalities_must_mix(self):
        # The Kotlin code forbids two consecutive same-modality picks.
        self.assertIn("modality == prevModality", self.src)

    def test_must_include_still(self):
        self.assertIn("RemainStill", self.src)
        self.assertIn('none { it is ChallengeSpec.RemainStill }', self.src)

    def test_applicant_and_trusted_use_different_salts(self):
        # Salt values are spelled out in the source.
        self.assertIn('salt = "applicant"', self.src)
        self.assertIn('salt = "trusted"', self.src)

    def test_seed_is_sha256(self):
        self.assertIn('"SHA-256"', self.src)


class ChallengeEngineAlgorithmTests(unittest.TestCase):

    def test_same_seed_same_sequence(self):
        s = "00112233445566778899aabbccddeeff" * 2  # 64 hex
        a = _applicant(s)
        b = _applicant(s)
        self.assertEqual(a, b)

    def test_different_seeds_different_sequences(self):
        s1 = "0" * 64
        s2 = "f" * 64
        self.assertNotEqual(_applicant(s1), _applicant(s2))

    def test_applicant_and_trusted_differ_under_same_seed(self):
        s = "01" * 32
        a = _applicant(s)
        t = _trusted(s)
        self.assertNotEqual(a, t)

    def test_sequence_contains_still(self):
        # Generate many sequences; every one must contain a STILL.
        for seed_byte in range(64):
            seed = f"{seed_byte:02x}" * 32
            seq = _applicant(seed)
            self.assertTrue(any(s.startswith("STILL:") for s in seq),
                            f"no STILL in {seq}")

    def test_sequence_length_is_five(self):
        for seed_byte in range(8):
            seed = f"{seed_byte:02x}" * 32
            seq = _applicant(seed)
            self.assertEqual(len(seq), 5)

    def test_no_modality_repeats_consecutively(self):
        # Two consecutive GAZE/HEAD/HAND entries would be a bug — the
        # Kotlin code forces a re-draw on those. STILL may follow STILL.
        for seed_byte in range(64):
            seed = f"{seed_byte:02x}" * 32
            seq = _applicant(seed)
            mods = [s.split(":", 1)[0] for s in seq]
            for i in range(len(mods) - 1):
                if mods[i] == "STILL":
                    continue
                self.assertNotEqual(mods[i], mods[i + 1],
                    f"consecutive {mods[i]} in {seq}")

    def test_each_modality_appears_at_least_once_over_many_runs(self):
        seen = set()
        for seed_byte in range(64):
            seed = f"{seed_byte:02x}" * 32
            seq = _applicant(seed)
            for s in seq:
                seen.add(s.split(":", 1)[0])
        # We expect at least gaze, head, hand, and still to appear.
        self.assertIn("GAZE", seen)
        self.assertIn("HEAD", seen)
        self.assertIn("HAND", seen)
        self.assertIn("STILL", seen)


class NonceGeneratorTests(unittest.TestCase):

    def test_session_id_is_uuid_v4_shaped(self):
        src = _read_source(NONCE_KT)
        # The Kotlin side uses UUID.randomUUID().
        self.assertIn("UUID.randomUUID()", src)

    def test_nonce_and_seed_are_hex(self):
        src = _read_source(NONCE_KT)
        self.assertIn('"%02x".format(it)', src)
        self.assertIn("ByteArray(byteCount)", src)
        self.assertIn("byteCount: Int = 16", src)
        self.assertIn("byteCount: Int = 32", src)


# ---- Session state machine ----------------------------------------------

STATE_KT = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
            / "com" / "edgeppg" / "app" / "challenge" / "SessionState.kt")


@dataclass
class Transition:
    frm: str
    to: str
    reason: str


class _Machine:
    def __init__(self, max_retries: int = 1):
        self.state = "CAPTURE"
        self.retries = max_retries
        self.history: list[Transition] = []

    def _move(self, to: str, reason: str) -> Transition:
        t = Transition(self.state, to, reason)
        self.history.append(t)
        self.state = to
        return t

    def begin(self):
        assert self.state == "CAPTURE"
        return self._move("QUALITY_CHECK", "begin")

    def quality_pass(self):
        assert self.state == "QUALITY_CHECK"
        return self._move("BASELINE", "quality-pass")

    def quality_fail(self, reason: str):
        assert self.state == "QUALITY_CHECK"
        if self.retries > 0:
            self.retries -= 1
            self._move("QUALITY_CHECK", f"quality-fail-retry:{reason}")
            return self._move("CAPTURE", "restart-for-retry")
        return self._move("DONE", f"retries-exhausted:{reason}")

    def baseline_complete(self):
        assert self.state == "BASELINE"
        return self._move("RANDOMIZED_CHALLENGE", "baseline-complete")

    def challenge_complete(self):
        assert self.state == "RANDOMIZED_CHALLENGE"
        return self._move("MOTION_BLINK_CHECK", "challenge-complete")

    def motion_blink_pass(self):
        assert self.state == "MOTION_BLINK_CHECK"
        return self._move("PROCESSING", "motion-blink-pass")

    def motion_blink_fail(self, reason: str):
        assert self.state == "MOTION_BLINK_CHECK"
        if self.retries > 0:
            self.retries -= 1
            self._move("MOTION_BLINK_CHECK",
                       f"motion-blink-fail-retry:{reason}")
            return self._move("RANDOMIZED_CHALLENGE", "restart-challenge")
        return self._move("DONE", f"retries-exhausted:{reason}")

    def processing_complete(self, reason: str):
        assert self.state == "PROCESSING"
        return self._move("DONE", reason)


class SessionStateMachineSourceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read_source(STATE_KT)

    def test_documented_states_all_present(self):
        for s in ("CAPTURE", "QUALITY_CHECK", "BASELINE",
                  "RANDOMIZED_CHALLENGE", "MOTION_BLINK_CHECK",
                  "PROCESSING", "DONE"):
            self.assertIn(s, self.src, f"state {s} missing")

    def test_default_max_retries_is_one(self):
        m = re.search(r'maxRetries\s*:\s*Int\s*=\s*(\d+)', self.src)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1)

    def test_quality_fail_can_retry(self):
        # The Kotlin qualityFail must branch on retriesRemaining > 0.
        self.assertIn("retriesRemaining > 0", self.src)

    def test_quality_fail_exhausted_routes_to_done(self):
        self.assertIn("retries-exhausted", self.src)


class SessionStateMachineBehaviourTests(unittest.TestCase):

    def test_happy_path(self):
        m = _Machine()
        m.begin()
        m.quality_pass()
        m.baseline_complete()
        m.challenge_complete()
        m.motion_blink_pass()
        m.processing_complete("decision:LIVE")
        self.assertEqual(m.state, "DONE")
        self.assertEqual(len(m.history), 6)
        self.assertEqual([t.to for t in m.history],
                         ["QUALITY_CHECK", "BASELINE",
                          "RANDOMIZED_CHALLENGE", "MOTION_BLINK_CHECK",
                          "PROCESSING", "DONE"])

    def test_quality_fail_then_pass(self):
        m = _Machine(max_retries=1)
        m.begin()
        m.quality_fail("low-light")
        # After retry, we should be back at CAPTURE.
        self.assertEqual(m.state, "CAPTURE")
        # Begin again to resume, then pass on the retry.
        m.begin()
        m.quality_pass()
        m.baseline_complete()
        m.challenge_complete()
        m.motion_blink_pass()
        m.processing_complete("decision:LIVE")
        self.assertEqual(m.state, "DONE")

    def test_retries_exhausted_terminate_at_done(self):
        m = _Machine(max_retries=1)
        m.begin()
        m.quality_fail("dark")  # retry → CAPTURE
        # Retry round.
        m.begin()
        m.quality_fail("still-dark")  # no retry left → DONE
        self.assertEqual(m.state, "DONE")
        self.assertEqual(m.history[-1].reason, "retries-exhausted:still-dark")

    def test_motion_blink_fail_can_retry_then_pass(self):
        m = _Machine(max_retries=2)
        m.begin()
        m.quality_pass()
        m.baseline_complete()
        m.challenge_complete()
        m.motion_blink_fail("blink")  # retry → RANDOMIZED_CHALLENGE
        m.challenge_complete()
        m.motion_blink_pass()
        m.processing_complete("decision:LIVE")
        self.assertEqual(m.state, "DONE")

    def test_invalid_transition_raises(self):
        m = _Machine()
        with self.assertRaises(AssertionError):
            m.quality_pass()  # state is CAPTURE, not QUALITY_CHECK


if __name__ == "__main__":
    unittest.main(verbosity=2)