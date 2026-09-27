"""EdgePPG ML pipeline tests (PC-side).

Run with:
    .venv\\Scripts\\python.exe -m ml.tests.run_tests

These tests verify the **pipeline** is structurally correct end-to-end. They
do NOT verify any real-data metric — none exists yet, and fabricating one is
strictly forbidden (NFR-MET-1).
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.src.feature_schema import (  # noqa: E402
    FEATURE_ORDER,
    SCHEMA_VERSION,
    FeatureSchemaError,
    empty_row,
    expected_feature_count,
    full_columns_csv,
    validate_row,
)
from ml.src.calibration import (  # noqa: E402
    LIVE_THRESHOLD_DEFAULT,
    SPOOF_THRESHOLD_DEFAULT,
    PlattScaler,
    Thresholds,
    apply_thresholds,
    default_thresholds,
)
from ml.src.dataset import (  # noqa: E402
    dataset_fingerprint,
    make_synthetic_fixture,
    subject_independent_split,
)
from ml.src import train_rf, train_xgb, freeze_model, evaluate  # noqa: E402


def _assert_raises(callable_, exc_type):
    """Tiny stdlib-only equivalent of pytest.raises."""
    try:
        callable_()
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(e).__name__}: {e}"
        )
    raise AssertionError(f"expected {exc_type.__name__}, no exception raised")


# ---- feature_schema --------------------------------------------------------

class FeatureSchemaTests(unittest.TestCase):

    def test_feature_count_is_28(self):
        self.assertEqual(expected_feature_count(), 28)
        self.assertEqual(len(FEATURE_ORDER), 28)

    def test_feature_order_matches_architecture_md(self):
        self.assertEqual(FEATURE_ORDER[0], "face_confidence")
        self.assertEqual(FEATURE_ORDER[-1], "device_integrity")

    def test_empty_row_is_all_nan(self):
        row = empty_row()
        for name in FEATURE_ORDER:
            self.assertTrue(math.isnan(row[name]), name)

    def test_validate_row_rejects_zero_fill(self):
        row = empty_row()
        row["rppg_snr"] = 0.0
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_validate_row_accepts_nan(self):
        row = empty_row()
        row["rppg_snr"] = float("nan")
        validate_row(row)

    def test_validate_row_rejects_infinity(self):
        row = empty_row()
        row["rppg_snr"] = float("inf")
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_validate_row_rejects_bool(self):
        row = empty_row()
        row["rppg_snr"] = True
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_validate_row_rejects_unknown_key(self):
        row = empty_row()
        row["bogus_extra"] = 1.0
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_validate_row_rejects_missing_key(self):
        row = empty_row()
        del row["rppg_snr"]
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_validate_row_rejects_bad_decision(self):
        row = empty_row()
        row["decision"] = "MAYBE"
        _assert_raises(lambda: validate_row(row), FeatureSchemaError)

    def test_full_columns_csv_includes_aux(self):
        cols = full_columns_csv().split(",")
        for c in ("subject_id", "session_id", "decision",
                  "model_version", "protocol_version",
                  "schema_version", "split"):
            self.assertIn(c, cols)


# ---- calibration ----------------------------------------------------------

class CalibrationTests(unittest.TestCase):

    def test_default_thresholds_match_documented_placeholders(self):
        t = default_thresholds()
        self.assertEqual(t.live, LIVE_THRESHOLD_DEFAULT)
        self.assertEqual(t.spoof, SPOOF_THRESHOLD_DEFAULT)
        self.assertEqual(t.live, 0.80)
        self.assertEqual(t.spoof, 0.20)

    def test_apply_thresholds_boundaries(self):
        t = Thresholds(live=0.8, spoof=0.2, schema_version=SCHEMA_VERSION)
        self.assertEqual(apply_thresholds(0.8, t), "LIVE")
        self.assertEqual(apply_thresholds(0.81, t), "LIVE")
        self.assertEqual(apply_thresholds(0.2, t), "SPOOF")
        self.assertEqual(apply_thresholds(0.19, t), "SPOOF")
        self.assertEqual(apply_thresholds(0.5, t), "UNCERTAIN")

    def test_platt_scaler_is_identity_when_unfit(self):
        s = PlattScaler()
        p = s.transform(0.0)
        self.assertTrue(0.0 <= p <= 1.0)

    def test_platt_scaler_fit_separates_classes(self):
        s = PlattScaler()
        raw = [0.1, 0.2, 0.15, 0.8, 0.9, 0.85]
        y = [0, 0, 0, 1, 1, 1]
        s.fit(raw, y)
        p_high = s.transform(0.85)
        p_low = s.transform(0.15)
        self.assertGreater(p_high, p_low)
        self.assertGreater(p_high, 0.5)
        self.assertLess(p_low, 0.5)


# ---- dataset --------------------------------------------------------------

class DatasetTests(unittest.TestCase):

    def test_synthetic_fixture_has_expected_shape(self):
        ds = make_synthetic_fixture(n_subjects=8, sessions_per_subject=6)
        self.assertEqual(len(ds), 48)
        self.assertEqual(len(set(ds.subject_ids)), 8)
        self.assertEqual({r["decision"] for r in ds.rows},
                         {"LIVE", "SPOOF"})

    def test_synthetic_fixture_is_deterministic(self):
        a = make_synthetic_fixture()
        b = make_synthetic_fixture()
        for ra, rb in zip(a.rows, b.rows):
            for k in FEATURE_ORDER:
                self.assertEqual(ra[k], rb[k])
            self.assertEqual(ra["subject_id"], rb["subject_id"])
            self.assertEqual(ra["session_id"], rb["session_id"])

    def test_subject_independent_split_has_no_subject_leakage(self):
        ds = make_synthetic_fixture(n_subjects=8, sessions_per_subject=6)
        train_idx, val_idx, test_idx = subject_independent_split(ds)
        train_subj = {ds.rows[i]["subject_id"] for i in train_idx}
        val_subj = {ds.rows[i]["subject_id"] for i in val_idx}
        test_subj = {ds.rows[i]["subject_id"] for i in test_idx}
        self.assertTrue(train_subj.isdisjoint(val_subj))
        self.assertTrue(train_subj.isdisjoint(test_subj))
        self.assertTrue(val_subj.isdisjoint(test_subj))

    def test_subject_independent_split_partitions_nonempty(self):
        ds = make_synthetic_fixture()
        train_idx, val_idx, test_idx = subject_independent_split(ds)
        self.assertGreater(len(train_idx), 0)
        self.assertGreater(len(val_idx), 0)
        self.assertGreater(len(test_idx), 0)
        self.assertEqual(len(train_idx) + len(val_idx) + len(test_idx),
                         len(ds))

    def test_fingerprint_changes_when_rows_change(self):
        a = make_synthetic_fixture()
        b = make_synthetic_fixture(n_subjects=10)
        self.assertNotEqual(dataset_fingerprint(a), dataset_fingerprint(b))


# ---- train + freeze --------------------------------------------------------

class TrainAndFreezeTests(unittest.TestCase):

    def test_train_random_forest_pipeline_runs(self, tmp_dir=None):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            models_dir = tmp_path / "models"
            splits_dir = tmp_path / "splits"
            ds = make_synthetic_fixture()
            split_paths = train_rf.split_dataset_csv(ds, splits_dir)
            result = train_rf.train_random_forest(ds)
            paths = train_rf.write_artifact(
                models_dir, result, ds, split_paths,
                manifest_status="UNTRAINED_NO_REAL_DATA",
                notes=["synthetic only"],
            )

            artifact = Path(paths["artifact"])
            manifest = Path(paths["manifest"])
            self.assertTrue(artifact.exists())
            self.assertTrue(manifest.exists())
            body = json.loads(manifest.read_text())
            self.assertEqual(body["status"], "UNTRAINED_NO_REAL_DATA")
            self.assertEqual(body["model_type"], "RandomForestClassifier")
            self.assertEqual(body["schema_version"], SCHEMA_VERSION)
            self.assertEqual(len(body["feature_names"]), 28)

    def test_train_xgboost_pipeline_runs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            models_dir = tmp_path / "models"
            splits_dir = tmp_path / "splits"
            ds = make_synthetic_fixture()
            split_paths = train_xgb.split_dataset_csv(ds, splits_dir)
            result = train_xgb.train_xgboost(ds)
            paths = train_xgb.write_artifact(
                models_dir, result, ds, split_paths,
                status="UNTRAINED_NO_REAL_DATA",
            )
            self.assertTrue(Path(paths["artifact"]).exists())
            self.assertTrue(Path(paths["manifest"]).exists())

    def test_freeze_model_refuses_without_held_out_metrics(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = freeze_model.freeze_for_runtime(Path(tmp) / "frozen", {},
                                                  None)
            self.assertEqual(out["status"], "not_frozen")
            self.assertIn("no held-out metrics", out["reason"])

    def test_freeze_model_picks_winner(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ds = make_synthetic_fixture()
            rf_res = train_rf.train_random_forest(ds)
            xgb_res = train_xgb.train_xgboost(ds)
            train_rf.write_artifact(tmp_path, rf_res, ds, {},
                                    manifest_status="UNTRAINED_NO_REAL_DATA")
            train_xgb.write_artifact(tmp_path, xgb_res, ds, {},
                                     status="UNTRAINED_NO_REAL_DATA")
            candidates = {
                "rf":  tmp_path / "edgeppg_rf_v1.joblib",
                "xgb": tmp_path / "edgeppg_xgb_v1.joblib",
            }
            out = freeze_model.freeze_for_runtime(
                tmp_path / "frozen", candidates,
                held_out_metrics={"rf": {"roc_auc": 0.90},
                                  "xgb": {"roc_auc": 0.95}},
            )
            self.assertEqual(out["status"], "frozen")
            self.assertEqual(out["winner"], "xgb")
            self.assertTrue(Path(out["artifact"]).exists())


# ---- evaluate --------------------------------------------------------------

class EvaluateTests(unittest.TestCase):

    def test_evaluate_reports_unavailable_when_no_real_data(self):
        rep = evaluate.report_unavailable()
        self.assertEqual(rep["status"], "unavailable")
        self.assertIsNone(rep["metrics"]["roc_auc"])
        self.assertIsNone(rep["metrics"]["far"])

    def test_attack_specific_far_frr_is_empty_without_attack_column(self):
        rows = [{"decision": "LIVE", "subject_id": "S0", "session_id": "s0"}]
        self.assertEqual(evaluate.attack_specific_far_frr(rows), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
