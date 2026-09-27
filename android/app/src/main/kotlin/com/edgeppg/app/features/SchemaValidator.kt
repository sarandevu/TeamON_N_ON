package com.edgeppg.app.features

/**
 * Stage 9 — Schema validator.
 *
 * Strict row validator that mirrors `ml/src/feature_schema.py:validate_row`.
 * Raises [FeatureSchemaError] on any violation. Validation rules:
 *
 *  - Every feature in [FeatureSchema.FEATURE_ORDER] must be present.
 *  - No unknown feature keys.
 *  - Values are real numbers (including NaN) — never strings, lists, null.
 *  - `decision ∈ {LIVE, SPOOF, UNCERTAIN}` when present.
 *  - A value of exactly 0.0 in a feature whose natural range excludes
 *    0.0 is rejected — this is the silent-zero-fill detector
 *    (Architecture §11).
 *
 * Use [validate] before persisting a row to disk or feeding it to the
 * ML fusion client.
 */
object SchemaValidator {

    class FeatureSchemaError(message: String) : IllegalArgumentException(message)

    private val ALLOWED_DECISIONS = setOf("LIVE", "SPOOF", "UNCERTAIN")

    /**
     * Validate a feature row.
     *
     * @param values an array of length [FeatureSchema.FEATURE_COUNT].
     * @param aux an optional map of auxiliary columns. Validated keys are
     *   a subset of [FeatureSchema.AUX_COLUMNS]; missing keys are
     *   allowed (only `decision` is required when present, and only
     *   when this method is called with a non-null aux map).
     */
    fun validate(values: FloatArray, aux: Map<String, String>? = null) {
        if (values.size != FeatureSchema.FEATURE_COUNT) {
            throw FeatureSchemaError(
                "row must have exactly ${FeatureSchema.FEATURE_COUNT} " +
                    "features; got ${values.size}"
            )
        }

        for (i in FeatureSchema.FEATURE_ORDER.indices) {
            val name = FeatureSchema.FEATURE_ORDER[i]
            val v = values[i]
            if (v.isNaN()) continue  // missing is allowed
            if (v == Float.POSITIVE_INFINITY || v == Float.NEGATIVE_INFINITY) {
                throw FeatureSchemaError(
                    "feature $name has non-finite, non-NaN value $v"
                )
            }
            if (name in FeatureSchema.ZERO_FORBIDDEN && v == 0.0f) {
                throw FeatureSchemaError(
                    "feature $name is exactly 0.0 — this is treated as a " +
                        "silent zero-fill of a missing value; use NaN " +
                        "instead (Architecture §11)."
                )
            }
        }

        if (aux != null) {
            val unknown = aux.keys - FeatureSchema.AUX_COLUMNS.toSet()
            if (unknown.isNotEmpty()) {
                throw FeatureSchemaError(
                    "unknown aux keys: ${unknown.sorted()}"
                )
            }
            aux["decision"]?.let {
                if (it !in ALLOWED_DECISIONS) {
                    throw FeatureSchemaError("bad decision value: $it")
                }
            }
            aux["schema_version"]?.let {
                if (it != FeatureSchema.SCHEMA_VERSION) {
                    // Don't fail outright — the model might be trained on
                    // a slightly older schema; surface a log instead.
                    com.edgeppg.app.Log.error(
                        "features",
                        "row schema_version=$it, " +
                            "runtime=${FeatureSchema.SCHEMA_VERSION}"
                    )
                }
            }
        }
    }
}