"""EdgePPG calibration + threshold policy.

The decision gates compare `P(LIVE)` to two configurable thresholds:
  * `LIVE_THRESHOLD`   (default 0.80) — at or above, and gates pass, ⇒ LIVE
  * `SPOOF_THRESHOLD`  (default 0.20) — at or below ⇒ SPOOF
  * between them     ⇒ UNCERTAIN

These are PLACEHOLDER starting values per `Requirements §FR-GATE-8`. They MUST
be re-calibrated from real validation data; the documentation calls this out
explicitly. Until real data lands, the calibration module is a thin wrapper
that returns these defaults plus a Platt-scaled fit on whatever data is fed
in.

Calibration never moves into the Android runtime. The frozen model artifact
encodes the scaler; the runtime only loads and applies it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

#: Placeholder LIVE threshold — must be re-calibrated from real data.
LIVE_THRESHOLD_DEFAULT: float = 0.80

#: Placeholder SPOOF threshold — must be re-calibrated from real data.
SPOOF_THRESHOLD_DEFAULT: float = 0.20


@dataclass(frozen=True)
class Thresholds:
    """Configurable LIVE/SPOOF thresholds + schema version for the manifest."""
    live: float
    spoof: float
    schema_version: str

    def as_dict(self) -> dict:
        return asdict(self)


def default_thresholds(schema_version: str = "edgeppg-1.0") -> Thresholds:
    """Return the documented placeholder thresholds."""
    return Thresholds(
        live=LIVE_THRESHOLD_DEFAULT,
        spoof=SPOOF_THRESHOLD_DEFAULT,
        schema_version=schema_version,
    )


def apply_thresholds(p_live: float, t: Thresholds) -> str:
    """Apply the gate pseudocode (Architecture §8) — thresholds only.

    The caller (decision engine) layers quality/integrity/challenge gates on
    top of this; this function answers "given p_live and the thresholds, what
    would the threshold-only decision be?" Useful for unit tests.
    """
    if p_live >= t.live:
        return "LIVE"
    if p_live <= t.spoof:
        return "SPOOF"
    return "UNCERTAIN"


class PlattScaler:
    """Minimal Platt scaler for the frozen model artifact.

    Fits logistic regression on (raw_score, y) pairs to map classifier
    outputs to calibrated probabilities. We persist the (a, b) parameters
    alongside the model; the runtime applies them with `1 / (1 + exp(a*x+b))`.
    """

    def __init__(self, a: float = 1.0, b: float = 0.0):
        self.a = float(a)
        self.b = float(b)

    def transform(self, raw_score: float) -> float:
        """Map raw classifier score to a calibrated P(LIVE).

        Convention: `p = sigmoid(a*x + b)`. Higher raw_score ⇒ higher p.
        At the boundary `p = 0.5` when `a*x + b = 0`.
        """
        import math
        z = self.a * float(raw_score) + self.b
        # Numerically stable sigmoid
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def fit(self, raw_scores: list[float], y: list[int]) -> "PlattScaler":
        """Fit a 1-D logistic regression. Pure Python (no sklearn dependency
        in the runtime path). Falls back to identity transform if `numpy` is
        unavailable, which is acceptable for the placeholder model."""
        try:
            import numpy as np
        except ImportError:
            return PlattScaler()
        x = np.asarray(raw_scores, dtype=float)
        yv = np.asarray(y, dtype=float)
        # Use sklearn's LogisticRegression if present; else closed-form
        # Newton step. We import lazily to keep this module's import surface
        # tiny in the runtime path.
        try:
            from sklearn.linear_model import LogisticRegression
            lr = LogisticRegression(C=1e6, solver="lbfgs").fit(x.reshape(-1, 1), yv)
            self.a = float(lr.coef_[0][0])
            self.b = float(lr.intercept_[0])
            return self
        except Exception:
            # Newton step on sigmoid fit (1-D, robust).
            a, b = 1.0, 0.0
            for _ in range(50):
                z = a * x + b
                p = 1.0 / (1.0 + np.exp(-z))
                g0 = float(np.mean(p - yv))
                g1 = float(np.mean((p - yv) * x))
                a -= 0.1 * g1
                b -= 0.1 * g0
            self.a = float(a)
            self.b = float(b)
            return self

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b}

    @staticmethod
    def from_dict(d: dict) -> "PlattScaler":
        return PlattScaler(a=float(d["a"]), b=float(d["b"]))
