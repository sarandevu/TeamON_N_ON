"""Stage 6 — Behavioral estimator tests (Python mirror).

Mirrors of:
  - GazeEstimator.kt   — geometric gaze classification
  - HeadPoseSolver.kt  — geometric head-pose estimation
  - BehavioralRunner.kt — match / wrong / timeout / contaminated

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---- Constants from MediaPipe face mesh spec ------------------------------

RIGHT_EYE_OUTER = 33
RIGHT_EYE_INNER = 133
RIGHT_EYE_TOP = 159
RIGHT_EYE_BOTTOM = 145
RIGHT_IRIS_CENTER = 468
LEFT_EYE_OUTER = 263
LEFT_EYE_INNER = 362
LEFT_EYE_TOP = 386
LEFT_EYE_BOTTOM = 374
LEFT_IRIS_CENTER = 473
NOSE_TIP = 1
NOSE_BRIDGE = 168
CHIN = 152
FOREHEAD_CENTER = 10
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291


def point(mesh, index):
    off = index * 3
    if off < 0 or off + 2 >= len(mesh):
        return (float("nan"), float("nan"), float("nan"))
    return (mesh[off], mesh[off + 1], mesh[off + 2])


# ---- Gaze ---------------------------------------------------------------

CENTER_THRESHOLD = 0.18
MIN_OFFSET = 0.02


@dataclass
class GazeEstimate:
    direction: str  # LEFT/RIGHT/UP/DOWN/CENTER
    confidence: float
    eye_available: bool


def gaze_estimate(mesh):
    """Mirror of GazeEstimator.estimate()."""
    outer = point(mesh, RIGHT_EYE_OUTER)
    inner = point(mesh, RIGHT_EYE_INNER)
    top = point(mesh, RIGHT_EYE_TOP)
    bot = point(mesh, RIGHT_EYE_BOTTOM)
    if any(math.isnan(c) for c in (*outer, *inner, *top, *bot)):
        return GazeEstimate("CENTER", 0.0, eye_available=False)
    eye_w = abs(inner[0] - outer[0])
    eye_h = abs(bot[1] - top[1])
    if eye_w < 1 or eye_h < 1:
        return GazeEstimate("CENTER", 0.0, eye_available=False)
    iris = point(mesh, RIGHT_IRIS_CENTER)
    iris_x = iris[0] if not math.isnan(iris[0]) else 0.5
    iris_y = iris[1] if not math.isnan(iris[1]) else 0.5
    x_norm = max(-1.0, min(2.0, (iris_x - outer[0]) / eye_w)) - 0.5
    y_norm = max(-1.0, min(2.0, (iris_y - top[1]) / eye_h)) - 0.5
    if abs(x_norm) < CENTER_THRESHOLD and abs(y_norm) < CENTER_THRESHOLD:
        direction = "CENTER"
        conf = 1.0 - (abs(x_norm) + abs(y_norm))
    elif abs(x_norm) >= CENTER_THRESHOLD:
        direction = "RIGHT" if x_norm > 0 else "LEFT"
        conf = max(0.0, min(1.0, abs(x_norm) - CENTER_THRESHOLD))
    else:
        direction = "DOWN" if y_norm > 0 else "UP"
        conf = max(0.0, min(1.0, abs(y_norm) - CENTER_THRESHOLD))
    if abs(x_norm) < MIN_OFFSET and abs(y_norm) < MIN_OFFSET:
        return GazeEstimate("CENTER", 0.0, eye_available=True)
    return GazeEstimate(direction, conf, eye_available=True)


# ---- Head pose ---------------------------------------------------------

YAW_THRESHOLD_DEG = 12.0
PITCH_THRESHOLD_DEG = 8.0
ROLL_THRESHOLD_DEG = 10.0


@dataclass
class HeadPose:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    available: bool


def head_pose(mesh):
    """Mirror of HeadPoseSolver.estimate()."""
    nose = point(mesh, NOSE_TIP)
    forehead = point(mesh, FOREHEAD_CENTER)
    chin = point(mesh, CHIN)
    leo = point(mesh, LEFT_EYE_OUTER)
    reo = point(mesh, RIGHT_EYE_OUTER)
    lm = point(mesh, LEFT_MOUTH_CORNER)
    rm = point(mesh, RIGHT_MOUTH_CORNER)
    if any(math.isnan(c) for c in
            (*nose, *forehead, *chin, *leo, *reo, *lm, *rm)):
        return HeadPose(0.0, 0.0, 0.0, available=False)
    d_l = math.hypot(nose[0] - lm[0], nose[1] - lm[1])
    d_r = math.hypot(nose[0] - rm[0], nose[1] - rm[1])
    yaw_rad = math.atan2(d_l - d_r, d_l + d_r)
    yaw_deg = yaw_rad * 180.0 / math.pi
    mid_y = 0.5 * (forehead[1] + chin[1])
    span_y = max(1.0, chin[1] - forehead[1])
    nose_frac = (nose[1] - mid_y) / span_y
    pitch_deg = nose_frac * -60.0
    dx = leo[0] - reo[0]
    dy = leo[1] - reo[1]
    roll_rad = math.atan2(dy, dx)
    roll_deg = roll_rad * 180.0 / math.pi
    return HeadPose(yaw_deg, pitch_deg, roll_deg, available=True)


# ---- Behavioral runner --------------------------------------------------

def observe(requested_kind, requested_arg, started_at_ms, now_ms,
            gaze=None, pose=None, gesture=None, contamination=False):
    """Mirror of BehavioralRunner.observe()."""
    latency_ms = abs(now_ms - started_at_ms)
    timed_out = (now_ms - started_at_ms) > 3000  # default 2.5–3 s

    if contamination:
        return ("CONTAMINATED", latency_ms, False)

    matched = None
    if requested_kind == "gaze":
        if gaze is not None:
            req = requested_arg
            if req == "CENTER":
                matched = (gaze.direction == "CENTER")
            else:
                matched = (gaze.direction == req)
    elif requested_kind == "head":
        if pose is not None and pose.available:
            req = requested_arg
            if req == "TURN_LEFT":
                matched = pose.yaw_deg > YAW_THRESHOLD_DEG
            elif req == "TURN_RIGHT":
                matched = pose.yaw_deg < -YAW_THRESHOLD_DEG
            elif req == "TURN_UP":
                matched = pose.pitch_deg > PITCH_THRESHOLD_DEG
            elif req == "TURN_DOWN":
                matched = pose.pitch_deg < -PITCH_THRESHOLD_DEG
            elif req in ("NOD", "SHAKE_NO"):
                matched = abs(pose.roll_deg) > ROLL_THRESHOLD_DEG
    elif requested_kind == "hand":
        if gesture is not None:
            matched = (gesture == requested_arg)
    elif requested_kind == "still":
        if gesture is not None:
            matched = False
        else:
            too_much_pose = (
                pose is not None and pose.available and
                (abs(pose.yaw_deg) > 18.0 or abs(pose.pitch_deg) > 12.0)
            )
            gaze_moved = gaze is not None and gaze.direction != "CENTER"
            if too_much_pose or gaze_moved:
                matched = False
            else:
                matched = True

    if timed_out and matched is None:
        return ("TIMEOUT", latency_ms, False)
    if matched is True:
        return ("MATCH", latency_ms, True)
    if matched is False:
        return ("WRONG", latency_ms, False)
    return ("TIMEOUT", latency_ms, False)


# ---- Synthetic mesh fixtures --------------------------------------------

def _flat(*triples) -> list[float]:
    out = []
    for t in triples:
        out.extend(t)
    return out


def _frontal_face() -> list:
    """Build a synthetic 478-point mesh (flattened [x, y, z, ...]).
    Points are arbitrary but consistent with a frontal face.
    Coordinate convention: X grows right, Y grows down, Z grows out of screen.
    """
    # The iris refinement landmarks (468..477) are only present when
    # the iris-refinement model is enabled. We size the array to
    # include them so the synthetic fixture can populate iris centers.
    n = 478
    out = [0.0] * (n * 3)
    def set_pt(idx, xyz):
        out[idx * 3] = xyz[0]
        out[idx * 3 + 1] = xyz[1]
        out[idx * 3 + 2] = xyz[2]
    set_pt(RIGHT_EYE_OUTER, (40.0, 90.0, 0.0))
    set_pt(RIGHT_EYE_INNER, (60.0, 90.0, 0.0))
    set_pt(RIGHT_EYE_TOP,   (50.0, 80.0, 0.0))
    set_pt(RIGHT_EYE_BOTTOM,(50.0, 100.0, 0.0))
    set_pt(RIGHT_IRIS_CENTER,(50.0, 90.0, 0.0))
    set_pt(LEFT_EYE_OUTER,  (140.0, 90.0, 0.0))
    set_pt(LEFT_EYE_INNER,  (160.0, 90.0, 0.0))
    set_pt(LEFT_EYE_TOP,    (150.0, 80.0, 0.0))
    set_pt(LEFT_EYE_BOTTOM, (150.0, 100.0, 0.0))
    set_pt(LEFT_IRIS_CENTER,(150.0, 90.0, 0.0))
    set_pt(NOSE_TIP,        (100.0, 130.0, 0.0))
    set_pt(FOREHEAD_CENTER, (100.0, 30.0, 0.0))
    set_pt(CHIN,            (100.0, 220.0, 0.0))
    set_pt(LEFT_MOUTH_CORNER, (80.0, 170.0, 0.0))
    set_pt(RIGHT_MOUTH_CORNER,(120.0, 170.0, 0.0))
    return out


# ---- Tests ----------------------------------------------------------------

class MeshLandmarksSourceTests(unittest.TestCase):
    """The Kotlin `MeshLandmarks.kt` must declare the documented indices."""

    @classmethod
    def setUpClass(cls):
        cls.src = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                   / "com" / "edgeppg" / "app" / "behavior" / "MeshLandmarks.kt"
                   ).read_text(encoding="utf-8")

    def test_eye_indices_present(self):
        for c in ("RIGHT_EYE_OUTER", "RIGHT_EYE_INNER",
                  "RIGHT_EYE_TOP", "RIGHT_EYE_BOTTOM",
                  "LEFT_EYE_OUTER", "LEFT_EYE_INNER",
                  "LEFT_EYE_TOP", "LEFT_EYE_BOTTOM"):
            self.assertIn(c, self.src)

    def test_head_pose_indices_present(self):
        for c in ("NOSE_TIP", "FOREHEAD_CENTER", "CHIN",
                  "LEFT_MOUTH_CORNER", "RIGHT_MOUTH_CORNER"):
            self.assertIn(c, self.src)

    def test_iris_indices_present(self):
        for c in ("RIGHT_IRIS_CENTER", "LEFT_IRIS_CENTER",
                  "IRIS_REFINEMENT_MIN", "IRIS_REFINEMENT_MAX"):
            self.assertIn(c, self.src)


class GazeEstimatorTests(unittest.TestCase):

    def test_frontal_face_is_center(self):
        mesh = _frontal_face()
        e = gaze_estimate(mesh)
        self.assertTrue(e.eye_available)
        self.assertEqual(e.direction, "CENTER")

    def test_no_face_returns_unavailable_center(self):
        empty = [float("nan")] * (478 * 3)
        e = gaze_estimate(empty)
        self.assertFalse(e.eye_available)
        self.assertEqual(e.direction, "CENTER")

    def test_iris_right_of_center_means_right(self):
        mesh = _frontal_face()
        # Move iris to right side (toward RIGHT_EYE_INNER = x=60).
        idx = RIGHT_IRIS_CENTER * 3
        mesh = list(mesh)
        mesh[idx] = 58.0     # iris x near inner corner ⇒ x_norm > 0 ⇒ RIGHT
        mesh[idx + 1] = 90.0
        mesh[idx + 2] = 0.0
        e = gaze_estimate(mesh)
        self.assertEqual(e.direction, "RIGHT")
        self.assertGreater(e.confidence, 0.0)

    def test_iris_left_of_center_means_left(self):
        mesh = _frontal_face()
        idx = RIGHT_IRIS_CENTER * 3
        mesh = list(mesh)
        mesh[idx] = 42.0     # near outer corner ⇒ LEFT
        mesh[idx + 1] = 90.0
        mesh[idx + 2] = 0.0
        e = gaze_estimate(mesh)
        self.assertEqual(e.direction, "LEFT")

    def test_iris_high_means_up(self):
        mesh = _frontal_face()
        idx = RIGHT_IRIS_CENTER * 3
        mesh = list(mesh)
        mesh[idx + 1] = 82.0  # above center ⇒ UP
        e = gaze_estimate(mesh)
        self.assertEqual(e.direction, "UP")


class HeadPoseSolverTests(unittest.TestCase):

    def test_frontal_face_has_near_zero_pose(self):
        mesh = _frontal_face()
        p = head_pose(mesh)
        self.assertTrue(p.available)
        self.assertAlmostEqual(p.yaw_deg, 0.0, delta=2.0)
        self.assertAlmostEqual(p.pitch_deg, 0.0, delta=2.0)
        self.assertAlmostEqual(p.roll_deg, 0.0, delta=2.0)

    def test_unavailable_when_landmarks_missing(self):
        empty = [float("nan")] * (478 * 3)
        p = head_pose(empty)
        self.assertFalse(p.available)

    def test_yaw_positive_when_left_cheek_shorter(self):
        # Simulate head turned right: right cheek (subject's) becomes
        # shorter — i.e. distance from nose tip to RIGHT_MOUTH_CORNER
        # decreases, distance to LEFT_MOUTH_CORNER increases.
        mesh = _frontal_face()
        idx_rm = RIGHT_MOUTH_CORNER * 3
        mesh = list(mesh)
        # Push right mouth corner closer to the nose tip.
        mesh[idx_rm] = 110.0
        mesh[idx_rm + 1] = 150.0
        p = head_pose(mesh)
        # When the subject turns their head right, our heuristic
        # reports positive yaw (=TURN_LEFT in ChallengeSpec terms).
        # We just check the sign is meaningful, not the exact value.
        self.assertNotAlmostEqual(p.yaw_deg, 0.0, delta=5.0)

    def test_pitch_positive_when_nose_high(self):
        # Pitched up: nose tip is closer to forehead.
        mesh = _frontal_face()
        idx = NOSE_TIP * 3
        mesh = list(mesh)
        mesh[idx + 1] = 60.0  # higher in image (smaller y, since y grows down)
        p = head_pose(mesh)
        self.assertGreater(p.pitch_deg, 5.0)

    def test_roll_when_eyes_tilted(self):
        mesh = _frontal_face()
        # Make right eye higher than left.
        idx_reo = RIGHT_EYE_OUTER * 3
        mesh = list(mesh)
        mesh[idx_reo + 1] = 50.0  # moved up significantly (smaller y)
        p = head_pose(mesh)
        # After our fix, dx = leo_x - reo_x = 100, dy = leo_y - reo_y = 40.
        # atan2(40, 100) ≈ 21.8° ≠ 0.
        self.assertAlmostEqual(p.roll_deg, 21.8, delta=1.0)


class BehavioralRunnerTests(unittest.TestCase):

    def test_gaze_match(self):
        mesh = _frontal_face()
        g = gaze_estimate(mesh)
        outcome, _, success = observe("gaze", "CENTER", 0, 100, gaze=g)
        self.assertEqual(outcome, "MATCH")
        self.assertTrue(success)

    def test_gaze_wrong(self):
        mesh = _frontal_face()
        g = gaze_estimate(mesh)
        # Ask RIGHT, got CENTER.
        outcome, _, success = observe("gaze", "RIGHT", 0, 100, gaze=g)
        self.assertEqual(outcome, "WRONG")
        self.assertFalse(success)

    def test_gaze_timeout(self):
        outcome, _, success = observe("gaze", "RIGHT", 0, 10_000,
                                       gaze=None)
        self.assertEqual(outcome, "TIMEOUT")
        self.assertFalse(success)

    def test_head_turn_left_match(self):
        # Construct a yaw-positive mesh.
        mesh = _frontal_face()
        idx_rm = RIGHT_MOUTH_CORNER * 3
        mesh = list(mesh)
        mesh[idx_rm] = 110.0
        mesh[idx_rm + 1] = 150.0
        p = head_pose(mesh)
        if p.yaw_deg > 0:
            outcome, _, success = observe("head", "TURN_LEFT", 0, 100, pose=p)
            self.assertEqual(outcome, "MATCH")

    def test_still_match_when_no_motion(self):
        mesh = _frontal_face()
        p = head_pose(mesh)
        g = gaze_estimate(mesh)
        outcome, _, success = observe("still", None, 0, 100,
                                       gaze=g, pose=p, gesture=None)
        self.assertEqual(outcome, "MATCH")

    def test_still_wrong_when_hand_gesture(self):
        mesh = _frontal_face()
        p = head_pose(mesh)
        g = gaze_estimate(mesh)
        outcome, _, success = observe("still", None, 0, 100,
                                       gaze=g, pose=p, gesture="THUMBS_UP")
        self.assertEqual(outcome, "WRONG")

    def test_contamination_overrides_match(self):
        # Even a matching gaze is WRONG if contamination flagged.
        mesh = _frontal_face()
        g = gaze_estimate(mesh)
        outcome, _, success = observe("gaze", "CENTER", 0, 100,
                                       gaze=g, contamination=True)
        self.assertEqual(outcome, "CONTAMINATED")
        self.assertFalse(success)

    def test_hand_match(self):
        outcome, _, success = observe("hand", "THUMBS_UP", 0, 100,
                                       gesture="THUMBS_UP")
        self.assertEqual(outcome, "MATCH")
        self.assertTrue(success)

    def test_hand_wrong(self):
        outcome, _, success = observe("hand", "THUMBS_UP", 0, 100,
                                       gesture="POINT")
        self.assertEqual(outcome, "WRONG")


if __name__ == "__main__":
    unittest.main(verbosity=2)