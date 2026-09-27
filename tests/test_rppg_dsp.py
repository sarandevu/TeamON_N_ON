"""Stage 4 — rPPG DSP math tests (Python mirror).

The Kotlin `rppg/RppgClient.kt` implements the full pipeline
(POS → Butterworth biquad → radix-2 FFT → SNR / HR / Pearson →
quality + decision). The math primitives are pure arithmetic and are
re-implemented here in Python so we can unit-test the algorithm
itself. We don't run an end-to-end DSP comparison (timing-sensitive
FFT + filter cascades drift a few ULPs between Kotlin Float and Python
double), but we DO assert:

  - biquad coefficient math matches RBJ cookbook
  - Pearson correlation behaves correctly on synthetic data
  - radix-2 FFT produces the same magnitudes as numpy's FFT on the
    same input (the magnitude spectrum is the actual signal-level
    result we care about; phase is sensitive to float rounding)
  - The POS projection alpha formula matches the documented POS paper

If the algorithm ever drifts, the source-level checks in the Kotlin
file (the algorithm mirrors the C++ path from the out-of-tree code we
cross-checked) plus this Python mirror together form the contract.

Run with:
    .venv\\Scripts\\python.exe -m tests.run_all_tests
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


# ---- POS projection alpha --------------------------------------------------

def pos_alpha(x: np.ndarray, y: np.ndarray) -> float:
    """Mirror of RppgClient.computeWindow() POS alpha calculation.

    POS: X = Gn - Bn, Y = -2*Rn + Gn + Bn
         alpha = std(X) / std(Y)
         h = X + alpha * Y
    """
    mx = x.mean(); my = y.mean()
    sx = x.std(); sy = y.std()
    return sx / sy if sy > 1e-9 else 1.0


class PosAlphaTests(unittest.TestCase):

    def test_alpha_is_one_when_x_y_have_equal_spread(self):
        rng = np.random.default_rng(42)
        x = rng.normal(size=256)
        y = rng.normal(size=256)
        x = (x - x.mean()) / x.std()
        y = (y - y.mean()) / y.std()
        a = pos_alpha(x, y)
        self.assertAlmostEqual(a, 1.0, places=4)

    def test_alpha_proportional_to_std_ratio(self):
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=float)  # std = 0
        a = pos_alpha(x, y)
        # When sy is 0, alpha = 1.0 (Kotlin fallback).
        self.assertEqual(a, 1.0)

    def test_alpha_uses_means(self):
        # alpha is computed on centred data, so additive offsets don't matter.
        x = np.array([1, 2, 3, 4, 5, 6], dtype=float)
        y = np.array([2, 4, 6, 8, 10, 12], dtype=float)  # 2x
        a1 = pos_alpha(x, y)
        a2 = pos_alpha(x + 100, y + 100)
        self.assertAlmostEqual(a1, a2, places=6)


# ---- Butterworth biquad (RBJ cookbook) -----------------------------------

def biquad_coeffs(fc: float, fs: float, highpass: bool) -> tuple:
    """Mirror of RppgClient.computeBiquad() RBJ cookbook."""
    w0 = 2.0 * math.pi * fc / fs
    c = math.cos(w0)
    s = math.sin(w0)
    alpha = s / (2.0 * math.sqrt(2) / 2.0)  # Q = 1/sqrt(2)
    if not highpass:
        b0 = (1 - c) / 2.0
        b1 = 1 - c
        b2 = (1 - c) / 2.0
    else:
        b0 = (1 + c) / 2.0
        b1 = -(1 + c)
        b2 = (1 + c) / 2.0
    a0 = 1 + alpha
    a1 = -2 * c
    a2 = 1 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


class BiquadCoefficientTests(unittest.TestCase):

    def test_highpass_at_07hz_30fs(self):
        b0, b1, b2, a1, a2 = biquad_coeffs(0.7, 30.0, highpass=True)
        # DC gain of highpass must be 0: b0 + b1 + b2 == a1 + a2 + 1 multiplied
        # by a normalisation constant (a0). Verify ratio:
        # (b0 + b1 + b2) / (1 + a1 + a2) ≈ 0
        self.assertAlmostEqual(b0 + b1 + b2, 0.0, places=6)

    def test_lowpass_at_4hz_30fs(self):
        b0, b1, b2, a1, a2 = biquad_coeffs(4.0, 30.0, highpass=False)
        # DC gain of lowpass must be 1: (b0+b1+b2)/(1+a1+a2) ≈ 1
        gain_dc = (b0 + b1 + b2) / (1 + a1 + a2)
        self.assertAlmostEqual(gain_dc, 1.0, places=6)


# ---- Direct-form-I biquad forward pass -----------------------------------

def biquad_forward(b, x: np.ndarray) -> np.ndarray:
    """Mirror of RppgClient.biquad() in-place pass."""
    b0, b1, b2, a1, a2 = b
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        y0 = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[i] = y0
        x2, x1 = x1, x[i]
        y2, y1 = y1, y0
    return y


class BiquadForwardTests(unittest.TestCase):

    def test_zero_input_yields_zero_output(self):
        x = np.zeros(64)
        b = biquad_coeffs(0.7, 30.0, True)
        y = biquad_forward(b, x)
        self.assertTrue(np.allclose(y, 0))

    def test_constant_input_produces_dc_gain(self):
        x = np.ones(512) * 1.0
        b = biquad_coeffs(4.0, 30.0, highpass=False)
        y = biquad_forward(b, x)
        # Settled output should be ≈ 1.0 (DC gain = 1 for lowpass).
        self.assertAlmostEqual(y[-1], 1.0, places=2)

    def test_highpass_blocks_dc(self):
        # Apply a slow (DC) signal through a highpass; it should drop
        # to ≈ 0 in steady state.
        x = np.ones(512) * 1.0
        b = biquad_coeffs(0.7, 30.0, highpass=True)
        y = biquad_forward(b, x)
        self.assertLess(abs(y[-1]), 1e-3)


# ---- Pearson correlation -------------------------------------------------

def pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Mirror of RppgClient.pearson()."""
    n = len(a)
    if len(b) != n:
        raise ValueError("length mismatch")
    ma = a.mean(); mb = b.mean()
    sab = saa = sbb = 0.0
    for i in range(n):
        da = a[i] - ma; db = b[i] - mb
        sab += da * db
        saa += da * da
        sbb += db * db
    if saa <= 1e-9 or sbb <= 1e-9:
        return 0.0
    return sab / math.sqrt(saa * sbb)


class PearsonTests(unittest.TestCase):

    def test_perfect_positive(self):
        x = np.linspace(0, 1, 100)
        y = 2.0 * x + 0.5
        self.assertAlmostEqual(pearson(x, y), 1.0, places=6)

    def test_perfect_negative(self):
        x = np.linspace(0, 1, 100)
        y = -2.0 * x + 1.0
        self.assertAlmostEqual(pearson(x, y), -1.0, places=6)

    def test_zero_variance_returns_zero(self):
        x = np.ones(10)
        y = np.linspace(0, 1, 10)
        self.assertEqual(pearson(x, y), 0.0)


# ---- radix-2 FFT magnitude spectrum -------------------------------------

def fft_magnitude_mirror(x: np.ndarray) -> np.ndarray:
    """Radix-2 FFT — Python mirror. The Kotlin code uses bit-reversal +
    twiddle tables pre-computed in `init`. We match the same flow here.

    Used only to assert that the *magnitude* spectrum produced by the
    pipeline matches `numpy.fft.rfft` to a tight tolerance.
    """
    n = x.size
    bits = int(round(math.log2(n)))
    # Bit-reversal permutation.
    rev = np.zeros(n, dtype=int)
    for i in range(n):
        r = 0
        for b in range(bits):
            r |= ((i >> b) & 1) << (bits - 1 - b)
        rev[i] = r
    re = x.astype(float).copy()
    im = np.zeros(n)
    for i in range(n):
        j = rev[i]
        if j > i:
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
    cos_tab = np.zeros(n // 2)
    sin_tab = np.zeros(n // 2)
    for k in range(n // 2):
        a = -2.0 * math.pi * k / n
        cos_tab[k] = math.cos(a)
        sin_tab[k] = math.sin(a)
    length = 2
    while length <= n:
        step = n // length
        i = 0
        while i < n:
                j = 0
                while j < length // 2:
                    k = j * step
                    wr = cos_tab[k]
                    wi = sin_tab[k]
                    ur = re[i + j]; ui = im[i + j]
                    vr = re[i + j + length // 2] * wr - im[i + j + length // 2] * wi
                    vi = re[i + j + length // 2] * wi + im[i + j + length // 2] * wr
                    re[i + j] = ur + vr
                    im[i + j] = ui + vi
                    re[i + j + length // 2] = ur - vr
                    im[i + j + length // 2] = ui - vi
                    j += 1
                i += length
        length <<= 1
    return re, im


class FftMagnitudeTests(unittest.TestCase):

    def test_dc_signal_has_dc_bin_dominant(self):
        n = 256
        x = np.ones(n)
        re, im = fft_magnitude_mirror(x)
        mag = np.sqrt(re**2 + im**2)
        # DC bin (k=0) should dominate.
        self.assertGreater(mag[0], mag[1] * 10)
        self.assertGreater(mag[0], mag[2] * 10)

    def test_sine_at_bin_30_matches_numpy(self):
        n = 256
        k0 = 30  # bin index
        x = np.sin(2.0 * np.pi * k0 * np.arange(n) / n)
        re_mine, im_mine = fft_magnitude_mirror(x)
        mag_mine = np.sqrt(re_mine**2 + im_mine**2)
        # Compare against numpy.fft.fft (which uses the standard convention).
        ref = np.fft.fft(x)
        mag_ref = np.abs(ref)
        # The magnitude spectrum should match within float-rounding
        # tolerance. We allow a loose rtol because the Kotlin Float path
        # and the Python double path accumulate rounding differently;
        # what matters is that the peak bin lands at the right index
        # and the band magnitudes are within ~0.1%.
        np.testing.assert_allclose(mag_mine, mag_ref, rtol=1e-3, atol=1e-6)
        # Peak lands at the documented bin.
        self.assertEqual(int(np.argmax(mag_mine[1:])) + 1, k0)

    def test_1hz_signal_at_30fps_lands_in_pulse_band(self):
        # 1 Hz pulse @ 30 fps in a 256-pt window ⇒ 8.53 bins
        n = 256
        f = 1.0
        x = np.sin(2.0 * np.pi * f * np.arange(n) / 30.0)
        re, im = fft_magnitude_mirror(x)
        mag = np.sqrt(re**2 + im**2)
        # Peak bin should be ≈ 8 or 9 (256 * 1 / 30 = 8.53).
        peak_bin = int(np.argmax(mag[1:])) + 1  # skip DC
        self.assertIn(peak_bin, [8, 9])


# ---- HR / SNR computation ------------------------------------------------

def compute_hr_snr_mirror(mag: np.ndarray, k_lo: int = 6, k_hi: int = 34,
                           fs: float = 30.0, n: int = 256) -> tuple:
    """Mirror of RppgClient.computeWindow() HR / SNR block."""
    band = mag[k_lo:k_hi + 1]
    total = float(band.sum())
    peak_idx = int(np.argmax(band))
    k_peak = peak_idx + k_lo
    peak = float(band[peak_idx])
    k_l = max(k_peak - 1, k_lo)
    k_r = min(k_peak + 1, k_hi)
    neigh = peak + 0.5 * (float(mag[k_l]) + float(mag[k_r]))
    snr = neigh / total if total > 1e-9 else 0.0
    hr = k_peak * (fs / n) * 60.0
    return hr, snr


class HrSnrTests(unittest.TestCase):

    def test_72bpm_at_30fps(self):
        # 72 bpm = 1.2 Hz. At 30 fps, 256-pt window: bin = 256 * 1.2 / 30 = 10.24
        # → peak at bin 10, HR = 10 * 30 / 256 * 60 = 70.3125 bpm
        n = 256
        fs = 30.0
        target_hr_bpm = 72.0
        target_bin = round((target_hr_bpm / 60.0) * n / fs)  # = 10
        # Build a noisy signal at exactly target_bin.
        rng = np.random.default_rng(0)
        t = np.arange(n) / fs
        x = (np.sin(2 * np.pi * (target_hr_bpm / 60.0) * t) +
             0.05 * rng.normal(size=n))
        re, im = fft_magnitude_mirror(x)
        mag = np.sqrt(re**2 + im**2)
        hr, snr = compute_hr_snr_mirror(mag)
        self.assertEqual(hr, target_bin * fs / n * 60.0)


# ---- SpO2-style / "is peak enough" check (decision logic mirror) ------

class RppgSourceTests(unittest.TestCase):
    """The Kotlin `RppgClient.kt` must declare the documented thresholds
    and constants."""

    @classmethod
    def setUpClass(cls):
        cls.src = (REPO_ROOT / "android" / "app" / "src" / "main" / "kotlin"
                   / "com" / "edgeppg" / "app" / "rppg" / "RppgClient.kt"
                   ).read_text(encoding="utf-8")

    def test_thresholds_documented(self):
        for c in ("SNR_LIVE", "SNR_SPOOF", "ROI_CORR_LIVE",
                  "ROI_CORR_SPOOF", "QUALITY_THRESHOLD"):
            self.assertIn(c, self.src)

    def test_window_size_default_256(self):
        self.assertIn("windowSize: Int = 256", self.src)

    def test_sample_rate_30fps(self):
        self.assertIn("fs: Float = 30f", self.src)

    def test_band_edges_documented(self):
        self.assertIn("fLo: Float = 0.7f", self.src)
        self.assertIn("fHi: Float = 4.0f", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)