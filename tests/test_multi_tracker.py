"""Stage 8 — Multi-face tracker tests (Python mirror).

Mirrors `multi/MultiFaceTracker.kt` — the IoU + centroid tracker used
in multi-person mode. Tested in pure Python because the algorithm has
no Android dependencies.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import unittest
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class FaceBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def cx(self):
        return (self.left + self.right) / 2.0

    @property
    def cy(self):
        return (self.top + self.bottom) / 2.0


SUBJECT_UNASSIGNED = 0
SUBJECT_APPLICANT = 1
SUBJECT_TRUSTED = 2


@dataclass
class Track:
    id: int
    box: FaceBox
    mesh_points: list
    frames_since_seen: int = 0
    assigned_subject: int = SUBJECT_UNASSIGNED


class MultiFaceTracker:
    MIN_IOU = 0.10

    def __init__(self, max_participants: int = 2,
                 max_frames_since_seen: int = 30):
        self.max_participants = max_participants
        self.max_frames_since_seen = max_frames_since_seen
        self._next_id = 0
        self._tracks: List[Track] = []

    def assign_subject(self, track_id: int, subject: int) -> None:
        for t in self._tracks:
            if t.id == track_id:
                t.assigned_subject = subject
                return

    def snapshot(self) -> List[Track]:
        return list(self._tracks)

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 0

    def update(self, detections: List[Tuple[FaceBox, list]]
               ) -> List[Track]:
        matched = [False] * len(self._tracks)

        for box, mesh in detections:
            match_idx = self._best_match(box, matched)
            if match_idx is not None:
                t = self._tracks[match_idx]
                self._tracks[match_idx] = Track(
                    id=t.id, box=box, mesh_points=mesh,
                    frames_since_seen=0,
                    assigned_subject=t.assigned_subject,
                )
                matched[match_idx] = True
            elif len(self._tracks) < self.max_participants:
                self._tracks.append(Track(
                    id=self._next_id, box=box, mesh_points=mesh,
                    frames_since_seen=0,
                ))
                self._next_id += 1
                matched.append(True)  # newly added — mark as "matched"

        # Bump unseen counters and drop stale.
        kept: List[Track] = []
        for i, t in enumerate(self._tracks):
            if i < len(matched) and not matched[i]:
                t.frames_since_seen += 1
            if t.frames_since_seen <= self.max_frames_since_seen:
                kept.append(t)
        self._tracks = kept
        return self.snapshot()

    def _best_match(self, box: FaceBox,
                    matched: List[bool]) -> Optional[int]:
        best_idx = -1
        best_score = -math.inf
        for i, t in enumerate(self._tracks):
            if i < len(matched) and matched[i]:
                continue
            iou = self._iou(box, t.box)
            dist = math.hypot(box.cx - t.box.cx, box.cy - t.box.cy)
            score = iou if iou >= self.MIN_IOU else -dist / 1000.0
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx if best_idx >= 0 else None

    @staticmethod
    def _iou(a: FaceBox, b: FaceBox) -> float:
        ix0 = max(a.left, b.left)
        iy0 = max(a.top, b.top)
        ix1 = min(a.right, b.right)
        iy1 = min(a.bottom, b.bottom)
        if ix0 >= ix1 or iy0 >= iy1:
            return 0.0
        inter = (ix1 - ix0) * (iy1 - iy0)
        union = a.width * a.height + b.width * b.height - inter
        if union <= 0:
            return 0.0
        return inter / union


# ---- Tests ----------------------------------------------------------------

def _box(l, t, r, b):
    return FaceBox(l, t, r, b)


class MultiFaceTrackerTests(unittest.TestCase):

    def test_new_face_creates_track(self):
        t = MultiFaceTracker()
        out = t.update([(_box(10, 10, 110, 110), [])])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, 0)

    def test_same_face_same_id(self):
        t = MultiFaceTracker()
        t.update([(_box(10, 10, 110, 110), [])])
        # Tiny motion — should still match the same track.
        out = t.update([(_box(15, 12, 115, 112), [])])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, 0)

    def test_two_distinct_faces_get_distinct_ids(self):
        t = MultiFaceTracker()
        out = t.update([
            (_box(10, 10, 110, 110), []),
            (_box(300, 300, 400, 400), []),
        ])
        self.assertEqual(len(out), 2)
        ids = {tr.id for tr in out}
        self.assertEqual(len(ids), 2)

    def test_max_participants_caps_at_two(self):
        t = MultiFaceTracker()
        out = t.update([
            (_box(10, 10, 110, 110), []),
            (_box(300, 300, 400, 400), []),
            (_box(600, 600, 700, 700), []),  # 3rd — dropped
        ])
        self.assertEqual(len(out), 2)

    def test_unseen_track_dropped_after_timeout(self):
        t = MultiFaceTracker(max_frames_since_seen=3)
        t.update([(_box(10, 10, 110, 110), [])])
        for _ in range(4):
            t.update([])  # no detections
        self.assertEqual(len(t.snapshot()), 0)

    def test_subject_assignment_persists(self):
        t = MultiFaceTracker()
        t.update([(_box(10, 10, 110, 110), [])])
        tid = t.snapshot()[0].id
        t.assign_subject(tid, SUBJECT_APPLICANT)
        # Move the face slightly; identity must stick.
        t.update([(_box(15, 12, 115, 112), [])])
        self.assertEqual(t.snapshot()[0].assigned_subject, SUBJECT_APPLICANT)

    def test_reset_clears_state(self):
        t = MultiFaceTracker()
        t.update([(_box(10, 10, 110, 110), [])])
        t.reset()
        self.assertEqual(t.snapshot(), [])
        # New tracks after reset start at id 0 again.
        t.update([(_box(10, 10, 110, 110), [])])
        self.assertEqual(t.snapshot()[0].id, 0)

    def test_iou_zero_for_disjoint_boxes(self):
        self.assertEqual(MultiFaceTracker._iou(
            _box(0, 0, 10, 10), _box(20, 20, 30, 30)), 0.0)

    def test_iou_one_for_identical_boxes(self):
        self.assertAlmostEqual(MultiFaceTracker._iou(
            _box(0, 0, 10, 10), _box(0, 0, 10, 10)), 1.0)

    def test_face_swap_detected(self):
        # Two faces cross each other; the tracker must keep both
        # identities alive (i.e. not drop or merge them).
        t = MultiFaceTracker()
        # Initial positions: face A on left, face B on right.
        t.update([
            (_box(10, 10, 100, 100), []),
            (_box(300, 10, 400, 100), []),
        ])
        # They move toward each other but don't overlap yet.
        t.update([
            (_box(100, 10, 200, 100), []),
            (_box(200, 10, 300, 100), []),
        ])
        # The tracker should still hold two tracks (no drop, no merge).
        self.assertEqual(len(t.snapshot()), 2)


class MultiFaceTrackerSourceTests(unittest.TestCase):
    """The Kotlin `multi/MultiFaceTracker.kt` must declare the documented
    constants and the documented API surface."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        cls.src = (Path(__file__).resolve().parents[1] / "android"
                   / "app" / "src" / "main" / "kotlin"
                   / "com" / "edgeppg" / "app" / "multi"
                   / "MultiFaceTracker.kt").read_text(encoding="utf-8")

    def test_max_participants_default_is_two(self):
        import re
        m = re.search(r"maxParticipants\s*:\s*Int\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 2)

    def test_min_iou_constant_present(self):
        self.assertIn("MIN_IOU", self.src)

    def test_subject_enum_present(self):
        self.assertIn("Subject", self.src)
        for s in ("UNASSIGNED", "APPLICANT", "TRUSTED_PARTICIPANT"):
            self.assertIn(s, self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)