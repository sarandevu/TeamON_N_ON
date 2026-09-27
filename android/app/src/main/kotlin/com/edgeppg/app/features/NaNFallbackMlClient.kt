package com.edgeppg.app.features

/**
 * Stage 10 — NaN-fallback ML fusion client.
 *
 * Used until a real frozen-model artifact exists (which is currently
 * always — no real validation data has been collected). Emits
 * `Float.NaN` for every prediction so the decision engine (Stage 11)
 * routes to UNCERTAIN (per `FR-GATE-3` and `Architecture §8`).
 *
 * This is the **default** at startup; it is replaced by a real loader
 * (TFLite / ONNX-RT / NNAPI / vendor runtime, per `TechStack §16`)
 * once a real model artifact is provisioned. The exact runtime
 * selection is `Requires Verification` until iQOO 15 benchmarks
 * determine latency / memory budget.
 */
object NaNFallbackMlClient : MlFusionClient {
    override val isModelLoaded: Boolean = false
    override val loadedManifest: Map<String, String>? = null

    override fun predictLiveProbability(
        row: FloatArray,
        schemaVersion: String,
    ): Float {
        // Per Architecture §11 / FR-GATE-4: missing ML evidence must
        // not silently be treated as low P(LIVE). Return NaN so the
        // decision engine routes to UNCERTAIN.
        return Float.NaN
    }
}
