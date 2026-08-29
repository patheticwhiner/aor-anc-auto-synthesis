from __future__ import annotations

import numpy as np

from aor_anc.closed_loop import (
    controller_from_youla,
    direct_maps,
    nominal_youla_maps,
    numerical_transfer_map_audit,
    youla_maps,
)


def test_feedback_sign_for_static_example() -> None:
    plant = np.asarray([0.4])
    controller = np.asarray([0.5])
    maps = direct_maps(plant, controller)
    np.testing.assert_allclose(maps.sensitivity, [1.0 / 1.2])
    np.testing.assert_allclose(maps.control_from_disturbance, [-0.5 / 1.2])


def test_nominal_youla_maps_match_direct_maps() -> None:
    omega = np.linspace(0.0, np.pi, 1025)
    z_inverse = np.exp(-1j * omega)
    nominal = 0.2 * z_inverse - 0.05 * z_inverse**2
    youla = 0.1 + 0.02 * z_inverse
    controller = controller_from_youla(nominal, youla)
    direct = direct_maps(nominal, controller)
    derived = nominal_youla_maps(nominal, youla)
    np.testing.assert_allclose(direct.sensitivity, derived.sensitivity, rtol=1e-13)
    np.testing.assert_allclose(
        direct.control_from_disturbance,
        derived.control_from_disturbance,
        rtol=1e-13,
    )


def test_uncertain_youla_maps_match_direct_maps() -> None:
    omega = np.linspace(0.0, np.pi, 1025)
    z_inverse = np.exp(-1j * omega)
    nominal = 0.2 * z_inverse - 0.05 * z_inverse**2
    weight = np.full(omega.shape, 0.3, dtype=complex)
    delta = 0.2 + 0.1 * z_inverse
    youla = 0.1 + 0.02 * z_inverse
    controller = controller_from_youla(nominal, youla)
    direct = direct_maps(nominal + weight * delta, controller)
    derived = youla_maps(nominal, weight, delta, youla)
    np.testing.assert_allclose(direct.sensitivity, derived.sensitivity, rtol=1e-13)
    np.testing.assert_allclose(
        direct.control_from_disturbance,
        derived.control_from_disturbance,
        rtol=1e-13,
    )


def test_numerical_audit_is_well_below_phase0_tolerance() -> None:
    omega = np.linspace(0.0, np.pi, 4097)
    nominal = 0.1 * np.exp(-1j * omega)
    errors = numerical_transfer_map_audit(nominal, omega)
    assert max(errors.values()) < 1e-12
