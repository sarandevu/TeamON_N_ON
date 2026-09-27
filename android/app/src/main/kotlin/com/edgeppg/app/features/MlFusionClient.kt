package com.edgeppg.app.features

/**
 * Stage 10 — Frozen-model ML fusion client (runtime only).
 *
 * The Android/iQOO runtime NEVER trains; it loads a frozen classifier
 * artifact (produced by `ml/src/freeze_model.py` on the PC side) and
 * uses it to compute `P(LIVE) ∈ [0, 1]`. This interface is the only
 * allowed way for the rest of the app to obtain a probability — the
 * decision engine (Stage 11) consumes `P(LIVE)` plus independent
 * quality / integrity signals.
 *
 * Until a real model is loaded, the fallback returns `Float.NaN`.
 * Per `FR-GATE-3 / FR-GATE-4`, missing ML evidence routes to UNCERTAIN
 * — never to SPOOF. (Architecture §8.)
 */
interface MlFusionClient {
    /**
     * Predict `P(LIVE)` for a single feature row. Returns NaN when no
     * model is loaded (training not yet run / model file missing /
     * artifact is the UNTRAINED placeholder).
     *
     * @param row a length-28 float array ordered as
     *   [FeatureSchema.FEATURE_ORDER]. Must be NaN-clean (no
     *   silent zero-fills — see SchemaValidator).
     * @param schemaVersion the row's declared schema version. The
     *   client may reject rows whose version doesn't match the
     *   loaded artifact's version.
     */
    fun predictLiveProbability(
        row: FloatArray,
        schemaVersion: String = FeatureSchema.SCHEMA_VERSION,
    ): Float

    /** True iff a real (non-UNTRAINED) model is loaded. */
    val isModelLoaded: Boolean

    /** Manifest of the loaded artifact, or null when no model. */
    val loadedManifest: Map<String, String>?
}
