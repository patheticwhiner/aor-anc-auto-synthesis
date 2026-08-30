from __future__ import annotations

import numpy as np

from aor_anc.fair_baseline import (
    FairBaselineParameters,
    FairMetricSpecification,
    compute_fair_metrics,
    run_fair_imc_fxlms,
)
from aor_anc.models import DiscreteTransferModel


def _path(model_id: str, gain: float = 0.5, delay: int = 1) -> DiscreteTransferModel:
    return DiscreteTransferModel(
        model_id=model_id,
        numerator=np.asarray([0.0] * delay + [gain]),
        denominator=np.asarray([1.0]),
        sample_rate_hz=100.0,
        input_delay_samples=delay,
    )


def _parameters(
    *,
    start: int = 5,
    step_size: float = 0.1,
    limit: float = 10.0,
    initial: np.ndarray | None = None,
    radius: float = 10.0,
) -> FairBaselineParameters:
    return FairBaselineParameters(
        controller_coefficients=2 if initial is None else initial.size,
        step_size=step_size,
        normalization_delta=1e-4,
        coefficient_projection_radius=radius,
        actuator_limit=limit,
        adaptation_start_sample=start,
        actuation_ramp_samples=0,
        controller_regressor_delay_samples=1,
        require_no_clipping=True,
        initial_coefficients=initial,
    )


def _budget() -> dict[str, object]:
    return {
        "id": "test-budget",
        "true_path_access": "evaluation_engine_only",
        "internal_path_access": "complete_model",
    }


def _metrics(run, disturbance, *, start: int, target: float = 10.0):
    return compute_fair_metrics(
        disturbance,
        run,
        sample_rate_hz=100.0,
        specification=FairMetricSpecification(
            target_attenuation_db=target,
            evaluation_start_sample=start,
            evaluation_stop_sample=None,
            sustain_duration_samples=10,
            metric_step_samples=5,
        ),
        disturbance_peak_bound=2.0,
    )


def test_prestart_residual_equals_physical_disturbance() -> None:
    disturbance = np.linspace(-1.0, 1.0, 40)
    run = run_fair_imc_fxlms(
        disturbance, _path("true"), _path("hat"), _parameters(start=12), _budget()
    )
    np.testing.assert_allclose(run.residual[:12], disturbance[:12])
    np.testing.assert_array_equal(run.applied_control[:12], 0.0)


def test_perfect_model_reconstruction_uses_independent_identical_paths() -> None:
    disturbance = np.sin(2.0 * np.pi * 0.07 * np.arange(100))
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true"),
        _path("hat"),
        _parameters(start=0),
        _budget(),
    )
    np.testing.assert_allclose(
        run.true_secondary_output, run.predicted_secondary_output, atol=1e-14
    )
    np.testing.assert_allclose(run.reconstructed_disturbance, disturbance, atol=1e-14)


def test_mismatch_reconstruction_is_e_plus_shat_correction_not_true_path() -> None:
    disturbance = np.sin(2.0 * np.pi * 0.05 * np.arange(80))
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true", gain=0.8),
        _path("hat", gain=0.2),
        _parameters(start=0, step_size=0.0, initial=np.asarray([0.7])),
        _budget(),
    )
    expected = disturbance + (
        run.true_secondary_output - run.predicted_secondary_output
    )
    np.testing.assert_allclose(run.reconstructed_disturbance, expected, atol=1e-14)
    expected_filtered_x = np.concatenate(
        ([0.0], 0.2 * run.reconstructed_disturbance[:-1])
    )
    np.testing.assert_allclose(run.filtered_x, expected_filtered_x, atol=1e-14)
    assert np.max(np.abs(run.reconstructed_disturbance - disturbance)) > 1e-3


def test_one_sample_delay_and_feedback_sign() -> None:
    disturbance = np.asarray([1.0, 0.0, 0.0, 0.0, 0.0])
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true", gain=1.0),
        _path("hat", gain=1.0),
        _parameters(start=0, step_size=0.0, initial=np.asarray([1.0])),
        _budget(),
    )
    assert run.applied_control[0] == 0.0
    assert run.applied_control[1] == -1.0
    assert run.true_secondary_output[1] == 0.0
    assert run.true_secondary_output[2] == -1.0
    assert run.residual[2] == -1.0


def test_time_to_10db_is_confirmed_only_after_adaptation_start() -> None:
    disturbance = np.ones(50)
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true"),
        _path("hat"),
        _parameters(start=20, step_size=0.0),
        _budget(),
    )
    run.residual[:] = 0.0
    metrics = _metrics(run, disturbance, start=20)
    assert metrics["time_to_10db_status"] == "reached"
    assert metrics["time_to_10db_reached_sample"] >= 29
    assert metrics["time_to_10db_samples"] >= 10


def test_unreached_target_returns_not_reached_without_fallback_time() -> None:
    disturbance = np.ones(50)
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true"),
        _path("hat"),
        _parameters(start=20, step_size=0.0),
        _budget(),
    )
    metrics = _metrics(run, disturbance, start=20)
    assert metrics["time_to_10db_status"] == "not_reached"
    assert metrics["time_to_10db_samples"] is None
    assert metrics["time_to_10db_seconds"] is None
    assert metrics["time_to_10db_reached_sample"] is None


def test_clipping_makes_require_no_clipping_run_infeasible() -> None:
    disturbance = np.ones(60)
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true"),
        _path("hat"),
        _parameters(
            start=0, step_size=0.0, limit=0.1, initial=np.asarray([10.0]), radius=20.0
        ),
        _budget(),
    )
    metrics = _metrics(run, disturbance, start=0)
    assert metrics["control_demand_peak"] > metrics["applied_control_peak"]
    assert metrics["saturation_count"] > 0
    assert metrics["saturation_fraction"] > 0.0
    assert not metrics["feasible"]
    assert "actuator_clipping_forbidden" in metrics["infeasibility_reasons"]


def test_result_carries_information_budget_and_path_metadata() -> None:
    disturbance = np.ones(40)
    run = run_fair_imc_fxlms(
        disturbance, _path("true"), _path("hat"), _parameters(start=5), _budget()
    )
    metrics = _metrics(run, disturbance, start=5, target=100.0)
    assert metrics["true_secondary_path_model_id"] == "true"
    assert metrics["internal_secondary_path_model_id"] == "hat"
    assert metrics["plant_information_budget"]["id"] == "test-budget"
    assert metrics["plant_information_budget_id"] == "test-budget"
    assert metrics["adaptation_start_sample"] == 5
    assert metrics["evaluation_window"]["start_sample"] == 5
    assert metrics["evaluation_start_sample"] == 5
    assert metrics["evaluation_stop_sample_exclusive"] == 40
    assert metrics["sustain_duration_samples"] == 10


def test_coefficients_are_explicitly_projected_to_l2_ball() -> None:
    disturbance = np.ones(30)
    run = run_fair_imc_fxlms(
        disturbance,
        _path("true"),
        _path("hat"),
        _parameters(
            start=0, step_size=0.0, initial=np.asarray([3.0]), radius=0.25
        ),
        _budget(),
    )
    assert np.linalg.norm(run.coefficients) <= 0.25 + 1e-14
    assert np.count_nonzero(run.coefficient_projected) >= 1
