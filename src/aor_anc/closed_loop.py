"""Closed-loop maps for the sign convention e=d+Gu, u=-Ke."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClosedLoopMaps:
    sensitivity: np.ndarray
    control_from_disturbance: np.ndarray


def direct_maps(plant: np.ndarray, controller: np.ndarray) -> ClosedLoopMaps:
    denominator = 1.0 + plant * controller
    return ClosedLoopMaps(
        sensitivity=1.0 / denominator,
        control_from_disturbance=-controller / denominator,
    )


def controller_from_youla(nominal_plant: np.ndarray, youla: np.ndarray) -> np.ndarray:
    return youla / (1.0 - nominal_plant * youla)


def youla_maps(
    nominal_plant: np.ndarray,
    uncertainty_weight: np.ndarray,
    delta: np.ndarray,
    youla: np.ndarray,
) -> ClosedLoopMaps:
    denominator = 1.0 + uncertainty_weight * delta * youla
    return ClosedLoopMaps(
        sensitivity=(1.0 - nominal_plant * youla) / denominator,
        control_from_disturbance=-youla / denominator,
    )


def nominal_youla_maps(
    nominal_plant: np.ndarray, youla: np.ndarray
) -> ClosedLoopMaps:
    return ClosedLoopMaps(
        sensitivity=1.0 - nominal_plant * youla,
        control_from_disturbance=-youla,
    )


def relative_error(actual: np.ndarray, expected: np.ndarray) -> float:
    scale = np.maximum(np.maximum(np.abs(actual), np.abs(expected)), 1e-14)
    return float(np.max(np.abs(actual - expected) / scale))


def numerical_transfer_map_audit(
    nominal_response: np.ndarray, omega_rad_per_sample: np.ndarray
) -> dict[str, float]:
    """Compare independently evaluated direct and Youla closed-loop maps."""

    z_inverse = np.exp(-1j * omega_rad_per_sample)
    youla = 0.06 - 0.015 * z_inverse + 0.01 * z_inverse**2
    weight = np.full_like(nominal_response, 0.2 + 0.0j)
    delta = 0.25 + 0.1 * z_inverse
    true_plant = nominal_response + weight * delta
    controller = controller_from_youla(nominal_response, youla)

    direct_true = direct_maps(true_plant, controller)
    derived_true = youla_maps(nominal_response, weight, delta, youla)
    direct_nominal = direct_maps(nominal_response, controller)
    derived_nominal = nominal_youla_maps(nominal_response, youla)

    return {
        "true_sensitivity_relative_error": relative_error(
            direct_true.sensitivity, derived_true.sensitivity
        ),
        "true_control_relative_error": relative_error(
            direct_true.control_from_disturbance,
            derived_true.control_from_disturbance,
        ),
        "nominal_sensitivity_relative_error": relative_error(
            direct_nominal.sensitivity, derived_nominal.sensitivity
        ),
        "nominal_control_relative_error": relative_error(
            direct_nominal.control_from_disturbance,
            derived_nominal.control_from_disturbance,
        ),
    }
