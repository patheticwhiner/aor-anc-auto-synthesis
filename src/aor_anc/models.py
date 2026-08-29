"""Discrete-time model conventions and diagnostics used in Phase 0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal


@dataclass(frozen=True)
class DiscreteTransferModel:
    """A SISO transfer function in ascending powers of ``z^-1``."""

    model_id: str
    numerator: np.ndarray
    denominator: np.ndarray
    sample_rate_hz: float
    input_delay_samples: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DiscreteTransferModel":
        numerator = np.asarray(config["numerator"], dtype=float)
        denominator = np.asarray(config["denominator"], dtype=float)
        model = cls(
            model_id=str(config["id"]),
            numerator=numerator,
            denominator=denominator,
            sample_rate_hz=float(config["sample_rate_hz"]),
            input_delay_samples=int(config["input_delay_samples"]),
        )
        model.validate()
        return model

    def validate(self) -> None:
        if self.numerator.ndim != 1 or self.denominator.ndim != 1:
            raise ValueError("SISO numerator and denominator must be one-dimensional")
        if not self.numerator.size or not self.denominator.size:
            raise ValueError("empty transfer-function coefficient array")
        if not np.all(np.isfinite(self.numerator)) or not np.all(
            np.isfinite(self.denominator)
        ):
            raise ValueError("non-finite transfer-function coefficient")
        if self.denominator[0] == 0:
            raise ValueError("denominator a[0] must be nonzero")
        leading_zeros = int(np.argmax(self.numerator != 0))
        if leading_zeros != self.input_delay_samples:
            raise ValueError(
                "declared input delay does not equal leading numerator zeros: "
                f"{self.input_delay_samples} != {leading_zeros}"
            )
        if self.sample_rate_hz <= 0:
            raise ValueError("sample rate must be positive")

    def frequency_response(self, omega_rad_per_sample: np.ndarray) -> np.ndarray:
        _, response = signal.freqz(
            self.numerator, self.denominator, worN=omega_rad_per_sample
        )
        return response

    def impulse_response(self, samples: int) -> np.ndarray:
        impulse = np.zeros(samples, dtype=float)
        impulse[0] = 1.0
        return signal.lfilter(self.numerator, self.denominator, impulse)

    def poles_and_zeros(self) -> tuple[np.ndarray, np.ndarray]:
        """Return roots after expressing B(z^-1)/A(z^-1) as a ratio in z.

        Padding the shorter polynomial at the low-order end preserves explicit
        delays and the zero poles introduced by a long FIR numerator.
        """

        degree = max(self.numerator.size - 1, self.denominator.size - 1)
        numerator_z = np.pad(self.numerator, (0, degree + 1 - self.numerator.size))
        denominator_z = np.pad(
            self.denominator, (0, degree + 1 - self.denominator.size)
        )
        zeros = np.roots(np.trim_zeros(numerator_z, trim="f"))
        poles = np.roots(np.trim_zeros(denominator_z, trim="f"))
        return poles, zeros

    def diagnostic_summary(self) -> dict[str, Any]:
        poles, zeros = self.poles_and_zeros()
        return {
            "model_id": self.model_id,
            "sample_rate_hz": self.sample_rate_hz,
            "nyquist_hz": self.sample_rate_hz / 2.0,
            "numerator_coefficients": int(self.numerator.size),
            "denominator_coefficients": int(self.denominator.size),
            "input_delay_samples": self.input_delay_samples,
            "pole_count_including_delay_states": int(poles.size),
            "zero_count": int(zeros.size),
            "max_pole_radius": float(np.max(np.abs(poles), initial=0.0)),
            "unstable_pole_count": int(np.count_nonzero(np.abs(poles) >= 1.0)),
            "nonminimum_phase_zero_count": int(np.count_nonzero(np.abs(zeros) > 1.0)),
            "unit_circle_zero_count": int(
                np.count_nonzero(np.isclose(np.abs(zeros), 1.0, atol=1e-9))
            ),
        }


def plot_model_diagnostics(
    model: DiscreteTransferModel, output_path: Path, frequency_points: int
) -> None:
    """Plot poles/zeros, impulse response, and the complete 0--Nyquist FRF."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    poles, zeros = model.poles_and_zeros()
    omega = np.linspace(0.0, np.pi, frequency_points)
    response = model.frequency_response(omega)
    frequency_hz = omega * model.sample_rate_hz / (2.0 * np.pi)
    impulse = model.impulse_response(max(32, 2 * model.numerator.size))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    ax = axes[0, 0]
    angle = np.linspace(0.0, 2.0 * np.pi, 512)
    ax.plot(np.cos(angle), np.sin(angle), "k--", linewidth=0.8, label="unit circle")
    if zeros.size:
        ax.scatter(zeros.real, zeros.imag, marker="o", facecolors="none", edgecolors="C0", label="zeros")
    if poles.size:
        ax.scatter(poles.real, poles.imag, marker="x", color="C3", label="poles")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Real(z)")
    ax.set_ylabel("Imag(z)")
    ax.set_title("Poles and zeros (delay states included)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

    ax = axes[0, 1]
    ax.stem(np.arange(impulse.size), impulse, basefmt=" ")
    ax.set_xlabel("Sample")
    ax.set_ylabel("Amplitude")
    ax.set_title("Impulse response")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(response), 1e-15))
    ax.plot(frequency_hz, magnitude_db)
    ax.set_xlim(0.0, model.sample_rate_hz / 2.0)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Magnitude (dB)")
    ax.set_title("0--Nyquist frequency response")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    ax.plot(frequency_hz, np.unwrap(np.angle(response)) * 180.0 / np.pi)
    ax.set_xlim(0.0, model.sample_rate_hz / 2.0)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Unwrapped phase (deg)")
    ax.set_title("0--Nyquist phase")
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"Phase 0 nominal model: {model.model_id}")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
