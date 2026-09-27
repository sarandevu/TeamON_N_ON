# EdgePPG — ML Pipeline

This document describes the actual ML pipeline implemented in the
repository. It is grounded in the source code under `ml/src/`, the
on-device `features/`, and the threshold defaults from
`calibration.py`. **It is not** a description of an aspirational
or planned pipeline; it is what the code does today.

**Claim discipline:** Per `EDGEPPG_MASTER_INSTRUCTIONS.md §4` and
`Requirements §NFR-MET-1`, the system does **not** fabricate model
metrics, accuracy, precision, recall, F1, ROC-AUC, FAR, or FRR.
The training artifacts in `models/` are explicitly marked
`status: UNTRAINED_NO_REAL_DATA`; the runtime uses the
`NaNFallbackMlClient` until a real model is trained. This document
records that contract, not invented numbers.

---

## 1. Pipeline shape

The pipeline has two halves:

- **PC side (`ml/src/`)** — dataset, schema, training,
  calibration, freeze, evaluation. Not on the device. Runs on the
  developer's laptop / CI.
- **Android side (`features/`)** — the **consumer** of the
  pipeline's output. Loads a frozen artifact (when one exists),
  runs inference on the 28-feature row, returns `P(LIVE) ∈
  [0, 1]`. Today only the `NaNFallbackMlClient` is wired in; a
  real TFLite / ONNX loader is the Stage 16 deliverable.

The training pipeline (PC) does not retrain on the device. Per
`Requirements §FR-FUS-1` and `Architecture §7`, the Android app
never trains — it only loads a frozen model and infers. The
training side is the only side that touches data and labels.

---

## 2. PC side — `ml/src/`

### 2.1 `feature_schema.py`

The single source of truth for the 28-feature schema on the PC
side. Field order, names, NaN policy, no-zero-fill rule.

- `FEATURE_ORDER` — the documented 28 names in fixed order
  (`face_confidence` first, `device_integrity` last). The
  `test_schema_parity.py` suite asserts Kotlin `FeatureSchema.kt`
  matches this list byte-for-byte.
- `ZERO_FORBIDDEN` — features whose natural range excludes 0.0;
  the validator rejects a literal `0.0` in those slots because
  per `Architecture §11` "Missing values never silently zero-filled
  (unavailable rPPG ≠ 0)".
- `validate_row(row)` — checks the 28 fields, the `decision`
  field if present, the `schema_version` if present. Raises
  `FeatureSchemaError` on any deviation.
- `empty_row()` — the canonical "everything is NaN" row, used by
  the row assembler when a metric is unavailable.

`SCHEMA_VERSION = "edgeppg-1.0"`. Bumping the schema is a
versioned migration (any change to `FEATURE_ORDER` or
`ZERO_FORBIDDEN` requires a new `edgeppg-1.x` and a row-assembler
compat shim).

### 2.2 `dataset.py`

`make_synthetic_fixture()` and `split_dataset_csv()` operate on
the 28-feature schema. The synthetic fixture has 8 subjects, each
with 6 sessions — fully deterministic (seeded `random.Random`).
For real data, the same `split_dataset_csv()` writes CSVs at
`data/splits/{train,val,test}.csv` with one row per session.

The split is **subject-independent** via
`GroupShuffleSplit(test_size=val+test, ...)` followed by a
second split on the held-out group. This is the requirement
(`NFR-EVAL-1`) — no subject appears in more than one split.

### 2.3 `train_rf.py` and `train_xgb.py`

`train_rf.py` is the baseline (scikit-learn
`RandomForestClassifier(n_estimators=300, class_weight='balanced')`).
`train_xgb.py` is the challenger (XGBoost). Both:

- Drop UNCERTAIN rows (a documented decision — only LIVE/SPOOF
  rows are used for supervised training).
- Replace NaN values with the per-feature median (the
  `ZERO_FORBIDDEN` rule does NOT apply here — it applies to the
  on-device validator, not the PC trainer; the trainer is a
  research-time concern, not a runtime security boundary).
- Write `models/edgeppg_{rf,xgb}_v1.{joblib,manifest.json}`.

The manifest includes `dataset_fingerprint_sha256`,
`n_subjects`, `n_train_rows`, `train_auc`, and a literal
`status: UNTRAINED_NO_REAL_DATA` string. The status field is the
contract: a real-data run would set it to a different value
("TRAINED_ON_VALIDATION_SET_v1" or similar). The current
synthetic-fixture run sets it to the placeholder string.

### 2.4 `calibration.py`

`PlattScaler` wraps the model output. `default_thresholds()`
returns:

```python
Thresholds(live=0.80, spoof=0.20, schema_version="edgeppg-1.0")
```

These are the **placeholder starting values** per `Requirements
§FR-GATE-8`. They are calibrated from a real validation set when
one exists. The on-device `gates/Thresholds.kt.PLACEHOLDER`
mirrors these exactly (tested in `tests/test_canonical_parity.py`).

### 2.5 `freeze_model.py`

`freeze_for_runtime(out_dir, candidate_paths, held_out_metrics)`
selects the better of two candidate artifacts and writes
`models/edgeppg_frozen.{joblib,manifest.json}`. **It refuses to
freeze without held-out metrics** — calling it today returns
`{"status": "not_frozen", "reason": "no held-out metrics
available"}` because no real validation set exists.

The actual `models/edgeppg_frozen.*` artifact is **not** present
in the repo today. Only the candidate artifacts
(`edgeppg_rf_v1.*`, `edgeppg_xgb_v1.*`) are written, both with
`status: UNTRAINED_NO_REAL_DATA`.

### 2.6 `evaluate.py`

`roc_auc_score`, attack-specific FAR/FRR. The `attack_specific_far_frr(rows)`
function returns an empty dict when no `attack_type` column is
present in the rows — i.e. the real-data attack categorization
has not been done. The `report_unavailable()` function returns the
documented "we have not measured this" payload; it is what the
evaluator prints today.

---

## 3. Android side — `features/`

The Android-side consumer of the frozen artifact. Three classes:

### 3.1 `FeatureSchema.kt`

Mirrors `ml/src/feature_schema.py:FEATURE_ORDER` exactly.
`ZERO_FORBIDDEN` matches the Python side. `test_schema_parity.py`
asserts byte-for-byte equality.

### 3.2 `SchemaValidator.kt`

`validate(row, aux)` checks the 28 fields for finiteness and
rejects literal `0.0` in `ZERO_FORBIDDEN` features. This is the
runtime guard — the PC-side `validate_row` is the same logic for
training-time.

### 3.3 `MlFusionClient` interface + `NaNFallbackMlClient`

The interface:

```kotlin
interface MlFusionClient {
    suspend fun predictLiveProbability(row: FloatArray, schemaVersion: String = ...): Float
    val isModelLoaded: Boolean
    val loadedManifest: Map<String, String>?
}
```

`NaNFallbackMlClient` is the **default** at startup; it returns
`Float.NaN` for every prediction. The decision engine treats
NaN P_live as "no ML evidence" → routes to `UNCERTAIN` per
`Requirements §FR-GATE-3` and `Architecture §8`. This is the
**documented contract** of the placeholder.

A real TFLite / ONNX implementation lives in a future Stage 16
deliverable. Selection of TFLite vs. ONNX-RT vs. NNAPI is
`Requires Verification` per `TechStack §16` (iQOO 15 benchmark
gates the choice).

### 3.4 `RowAssembler.kt`

Maps per-session metrics to a length-28 `FloatArray` in
`FeatureSchema.FEATURE_ORDER`. Multi-person features default to
`NaN` (the documented "missing" sentinel). Validates with
`SchemaValidator.validate`. Used by `SessionController` after a
session completes; the result row is what would be fed to a real
`MlFusionClient.predictLiveProbability` — for now, the
`NaNFallbackMlClient` returns NaN.

---

## 4. End-to-end flow (current state, no fabrication)

```
PC side (offline, never on device):
  real validation set (not present) → ml/src/train_rf.py / train_xgb.py
    → models/edgeppg_{rf,xgb}_v1.{joblib,manifest.json} (status=UNTRAINED)
  real held-out metrics (not present) → freeze_model.freeze_for_runtime
    → models/edgeppg_frozen.{joblib,manifest.json} (DOES NOT EXIST TODAY)

Android side (runtime, on device):
  camera + face mesh + quality gate
    → SessionController.commitAndDispatch()
    → RowAssembler.assemble(Inputs(...))
        → validates with SchemaValidator.validate(...)
    → MlFusionClient.predictLiveProbability(row)
        → NaNFallbackMlClient returns Float.NaN
    ��� DecisionEngine.decide(...)
        → routes to UNCERTAIN when P_live is NaN
    → TranscriptBuilder.sign(...)
        → IntegrityManager.sign(...) → Envelope
    → Transport.send(Envelope)
        → LocalWifiTransport or QrFallbackTransport
        → PC verifier (verifier/server.py)
            → verifier.verify.verify_envelope(Envelope, pubkey)
            → returns {ok, reason, telemetry, ...}
    → result screen on device
```

The decision shown to the operator in the demo is the result of
`DecisionEngine.decide(...)`. With the current `NaNFallbackMlClient`,
that result is **`UNCERTAIN` for any case where integrity is
satisfied** — because `P_live` is NaN, the threshold gates
(`live_probability >= LIVE_THRESHOLD` and `live_probability <=
SPOOF_THRESHOLD`) are both false, and the gate routes to the
"borderline" arm which is `UNCERTAIN` (per
`tests/test_decision_truth_table.py`).

This is **not** a bug. It is the explicit contract of the
placeholder model. A trained model would replace
`NaNFallbackMlClient` and the demo would show `LIVE` for genuine
sessions.

---

## 5. What the demo will and will not show (claim discipline)

The current build, when run on the iQOO, will demonstrate:

- ✅ The camera captures face mesh landmarks.
- ✅ AE / AWB lock fires; the quality gate transitions to PASS.
- ✅ The challenge list renders and the participant can tap
  "I did it" to advance.
- ✅ Optical flash colours the screen (white / warm / cool) at
  the documented brightness and duration.
- ✅ A signed envelope is produced and POSTed to the verifier
  (or shown as a QR if Wi-Fi is unavailable).
- ✅ The verifier accepts the envelope (or rejects if a tamper is
  attempted) — the cryptographic round-trip is end-to-end and
  the test suite covers it (`tests/test_canonical_parity.py`).

The current build will **not** demonstrate:

- ❌ A trained ML model that returns a real `P(LIVE)` (it returns
  NaN).
- ❌ Attack-vs-genuine discrimination (the placeholder model
  cannot distinguish them — both route to `UNCERTAIN`).
- ❌ ROC-AUC, F1, FAR, FRR numbers (no real validation set exists;
  fabricating them is prohibited by `NFR-MET-1`).

When a real validation set is available, the documented procedure
to upgrade is:

1. `data/raw/<subject_id>/<session_id>.csv` — one row per session.
2. `python -m ml.src.train_rf --data-source raw` — overwrites the
   synthetic-fixture artifacts.
3. `python -m ml.src.freeze_model` — produces `edgeppg_frozen.*`
   with `status: TRAINED_*`.
4. Bundle the artifact in the APK (TFLite AAR).
5. Replace `NaNFallbackMlClient` with the TFLite-backed client.

`docs/payload_format.md` and `docs/demo_run.md` are the operator-
side procedure for steps 4-5.
