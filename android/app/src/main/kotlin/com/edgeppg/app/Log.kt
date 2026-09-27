package com.edgeppg.app

/**
 * EdgePPG structured logger.
 *
 * Discipline:
 *  - Tags are short and stable. They group by feature area, not by transient
 *    state.
 *  - Messages are free-form but never include PII, raw biometric templates,
 *    key material, or signed payloads. Diagnostic detail (frame counts, gate
 *    outcomes, scheme-level metrics) is fine.
 *  - No `Log.d` / `Log.v` calls are made at runtime — the dev log surface is
 *    gated behind [BuildConfig.EDGEPPG_DEV_MODE] so a release build stays
 *    quiet.
 *  - All public methods are no-ops in clean (release, non-dev) builds except
 *    for `error`, which always surfaces — failures must never be silent.
 */
object Log {
    private const val APP_TAG = "EdgePPG"

    fun tag(area: String): String = "$APP_TAG/$area"

    /** Stage / component bring-up messages. Dev-only. */
    fun stage(stage: String, msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("stage"), "[$stage] $msg")
        }
    }

    /** Camera / capture pipeline messages. Dev-only. */
    fun capture(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("capture"), msg)
        }
    }

    /** Frame quality gate messages. Dev-only. */
    fun quality(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("quality"), msg)
        }
    }

    /** rPPG DSP messages. Dev-only. */
    fun rppg(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("rppg"), msg)
        }
    }

    /** Behavioral / challenge messages. Dev-only. */
    fun behavior(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("behavior"), msg)
        }
    }

    /** Multi-person tracking. Dev-only. */
    fun multi(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("multi"), msg)
        }
    }

    /** Decision engine / gates. Dev-only. */
    fun gate(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("gate"), msg)
        }
    }

    /** Integrity / Keystore / transcript signing. Always surface (dev-only). */
    fun integrity(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("integrity"), msg)
        }
    }

    /** Transport (Wi-Fi / QR). Dev-only. */
    fun transport(msg: String) {
        if (BuildConfig.EDGEPPG_DEV_MODE) {
            android.util.Log.i(tag("transport"), msg)
        }
    }

    /**
     * Error path. Always emits, regardless of dev mode. Errors must never be
     * silent — that's a claim-discipline requirement (Architecture §11:
     * gracefully handle exceptional conditions without swallowing exceptions).
     */
    fun error(area: String, msg: String, t: Throwable? = null) {
        val tag = tag(area)
        if (t != null) android.util.Log.e(tag, msg, t) else android.util.Log.e(tag, msg)
    }
}
