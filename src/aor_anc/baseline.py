"""Source-exact reproduction of the audited external IMC-FxLMS baseline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat


@dataclass(frozen=True)
class BaselineParameters:
    controller_coefficients: int
    step_size: float
    delta: float
    ramp_seconds: float
    coefficient_norm_limit: float
    actuator_limit: float


@dataclass
class BaselineRun:
    residual: np.ndarray
    control: np.ndarray
    control_demand: np.ndarray
    clipped: np.ndarray
    coefficients: np.ndarray
    start_sample_matlab: int


def load_stage_suite(path: Path, split: str) -> dict[str, Any]:
    payload = loadmat(path, simplify_cells=True)
    suite = payload["suite"]
    return suite[split]


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def run_source_exact(
    disturbance: np.ndarray,
    sample_rate_hz: float,
    numerator: np.ndarray,
    denominator: np.ndarray,
    parameters: BaselineParameters,
) -> BaselineRun:
    """Reproduce ``controller_imc_fxlms.m`` including its startup semantics."""

    d_sig = np.asarray(disturbance, dtype=float).reshape(-1)
    a_plant = np.asarray(denominator, dtype=float).reshape(-1)
    b_poly = np.asarray(numerator, dtype=float).reshape(-1)
    b_plant = b_poly[1:]
    n_a = a_plant.size - 1
    l_b = b_plant.size
    n_fir = parameters.controller_coefficients
    ramp_samples = round(parameters.ramp_seconds * sample_rate_hz)
    k_start = max(n_fir, n_a + l_b + 2, ramp_samples + 10)

    sample_count = d_sig.size
    residual = np.zeros(sample_count)
    control = np.zeros(sample_count)
    control_demand = np.zeros(sample_count)
    clipped = np.zeros(sample_count, dtype=bool)
    secondary_output = np.zeros(sample_count)
    reconstructed_disturbance = np.zeros(sample_count)
    filtered_x = np.zeros(sample_count)
    coefficients = np.zeros(n_fir)

    # MATLAB loop: for k = k_start:Nsim, where k is one-based.
    for index in range(k_start - 1, sample_count):
        if n_a:
            output_history = secondary_output[index - np.arange(1, n_a + 1)]
            recursive_term = -float(a_plant[1:] @ output_history)
        else:
            recursive_term = 0.0
        control_history = control[index - np.arange(1, l_b + 1)]
        secondary_output[index] = recursive_term + float(b_plant @ control_history)

        error = d_sig[index] + secondary_output[index]
        residual[index] = error
        reconstructed_disturbance[index] = error - secondary_output[index]

        if n_a:
            filtered_history = filtered_x[index - np.arange(1, n_a + 1)]
            filtered_recursive = -float(a_plant[1:] @ filtered_history)
        else:
            filtered_recursive = 0.0
        disturbance_history = reconstructed_disturbance[
            index - np.arange(1, l_b + 1)
        ]
        filtered_x[index] = filtered_recursive + float(b_plant @ disturbance_history)

        if (index + 1) > n_fir and not clipped[max(0, index - 1)]:
            filtered_vector = filtered_x[index - np.arange(1, n_fir + 1)]
            disturbance_vector = reconstructed_disturbance[
                index - np.arange(1, n_fir + 1)
            ]
            normalization = float(filtered_vector @ filtered_vector) + parameters.delta
            coefficients += (
                parameters.step_size * error * filtered_vector / normalization
            )
            coefficient_norm = float(np.linalg.norm(coefficients))
            if coefficient_norm > parameters.coefficient_norm_limit:
                coefficients *= parameters.coefficient_norm_limit / coefficient_norm
            request = -float(coefficients @ disturbance_vector)
        else:
            request = 0.0

        ramp = min(
            1.0,
            max(0.0, ((index + 1) - k_start) / max(1, ramp_samples)),
        )
        request *= ramp
        if not np.isfinite(request):
            request = 0.0
        actual = float(np.clip(request, -parameters.actuator_limit, parameters.actuator_limit))
        control[index] = actual
        control_demand[index] = request
        clipped[index] = abs(actual - request) > 1e-10

    return BaselineRun(
        residual=residual,
        control=control,
        control_demand=control_demand,
        clipped=clipped,
        coefficients=coefficients,
        start_sample_matlab=k_start,
    )


def compute_source_metrics(
    disturbance: np.ndarray,
    run: BaselineRun,
    sample_rate_hz: float,
    simulation_seconds: float,
) -> dict[str, float | int | bool | str]:
    """Match the adaptive branch of the external ``compute_metrics.m``."""

    y_open = np.asarray(disturbance, dtype=float).reshape(-1)
    sample_count = y_open.size
    idx_start_matlab = min(
        round(3.0 * sample_rate_hz) + 1,
        max(1, sample_count - round(0.5 * sample_rate_hz)),
    )
    idx_start = idx_start_matlab - 1
    n_total = sample_count - idx_start
    steady_offset_matlab = max(1, round(0.2 * n_total))
    steady_start = idx_start + steady_offset_matlab - 1
    open_rms = _rms(y_open[steady_start:])
    closed_rms = _rms(run.residual[steady_start:])
    attenuation_db = float(20.0 * np.log10(open_rms / max(closed_rms, 1e-12)))

    window_length = round(0.2 * sample_rate_hz)
    window_step = round(0.05 * sample_rate_hz)
    window_count = (sample_count - window_length) // window_step
    moving_suppression = np.zeros(window_count)
    moving_time = np.zeros(window_count)
    for window_index in range(window_count):
        start = window_index * window_step
        stop = start + window_length
        moving_suppression[window_index] = 20.0 * np.log10(
            _rms(y_open[start:stop])
            / max(_rms(run.residual[start:stop]), 1e-12)
        )
        # MATLAB uses the one-based i0 in this expression.
        moving_time[window_index] = (start + 1 + window_length / 2.0) / sample_rate_hz

    target = 0.5 * attenuation_db
    convergence_time = 0.0
    sustained = 0
    for window_index, suppression in enumerate(moving_suppression):
        if suppression >= target:
            sustained += 1
            if sustained >= 3:
                convergence_time = float(moving_time[window_index - 2])
                break
        else:
            sustained = 0
    if convergence_time == 0.0:
        best = int(np.argmax(moving_suppression))
        convergence_time = (
            float(moving_time[best])
            if moving_suppression[best] >= 0.0
            else float(simulation_seconds)
        )

    startup_stop = run.start_sample_matlab - 1
    startup_is_nonphysical = bool(
        startup_stop > 0
        and np.all(run.residual[:startup_stop] == 0.0)
        and np.any(y_open[:startup_stop] != 0.0)
    )
    return {
        "attenuation_db": attenuation_db,
        "convergence_time_s": convergence_time,
        "convergence_metric_valid": not startup_is_nonphysical,
        "convergence_metric_limitation": (
            "prestart residual is zero while disturbance is nonzero"
            if startup_is_nonphysical
            else "none"
        ),
        "control_peak": float(np.max(np.abs(run.control))),
        "control_rms": _rms(run.control),
        "unclipped_control_peak": float(np.max(np.abs(run.control_demand))),
        "saturation_count": int(np.count_nonzero(run.clipped)),
        "coefficient_norm": float(np.linalg.norm(run.coefficients)),
        "y_open_rms": open_rms,
        "y_closed_rms": closed_rms,
        "start_sample_matlab": run.start_sample_matlab,
    }
