from __future__ import annotations

import inspect

import numpy as np
import pytest

from aor_anc.fair_baseline import (
    FairBaselineParameters,
    FairMetricSpecification,
    compute_fair_metrics,
    run_fair_imc_fxlms,
)
from aor_anc.models import DiscreteTransferModel
from aor_anc.robust_baseline import (
    BENCHMARK_FAMILY_QUALIFICATION,
    BenchmarkCase,
    evaluate_frozen_candidate,
    interpolate_stable_delayed_paths,
    select_best_candidate,
    tune_candidates,
    validate_design_heldout_split,
)


def _fir(model_id: str = "fir") -> DiscreteTransferModel:
    return DiscreteTransferModel(
        model_id=model_id,
        numerator=np.asarray([0.0, 0.5]),
        denominator=np.asarray([1.0]),
        sample_rate_hz=100.0,
        input_delay_samples=1,
    )


def _armax(model_id: str = "armax") -> DiscreteTransferModel:
    return DiscreteTransferModel(
        model_id=model_id,
        numerator=np.asarray([0.0, 0.25]),
        denominator=np.asarray([1.0, -0.2]),
        sample_rate_hz=100.0,
        input_delay_samples=1,
    )


def _budget() -> dict[str, object]:
    return {"id": "test-design-information", "true_path": "evaluation_only"}


def _parameters(**overrides) -> FairBaselineParameters:
    values = {
        "controller_coefficients": 1,
        "step_size": 0.0,
        "normalization_delta": 1e-4,
        "coefficient_projection_radius": 20.0,
        "actuator_limit": 0.1,
        "adaptation_start_sample": 0,
        "actuation_ramp_samples": 0,
        "controller_regressor_delay_samples": 1,
        "require_no_clipping": True,
        "initial_coefficients": np.asarray([10.0]),
    }
    values.update(overrides)
    return FairBaselineParameters(**values)


def _metric_specification() -> FairMetricSpecification:
    return FairMetricSpecification(
        target_attenuation_db=10.0,
        evaluation_start_sample=0,
        evaluation_stop_sample=60,
        sustain_duration_samples=10,
        metric_step_samples=10,
        tail_evaluation_start_sample=40,
    )


def test_interpolated_paths_are_stable_causal_delayed_and_exact() -> None:
    fir = _fir()
    armax = _armax()
    alpha = 0.4
    model = interpolate_stable_delayed_paths(
        fir, armax, alpha, model_id="S_alpha_0.4"
    )
    omega = np.linspace(0.0, np.pi, 51)
    expected = (1.0 - alpha) * fir.frequency_response(omega)
    expected += alpha * armax.frequency_response(omega)
    np.testing.assert_allclose(model.frequency_response(omega), expected, atol=1e-13)
    assert model.input_delay_samples == 1
    assert model.numerator[0] == 0.0
    assert np.all(np.abs(np.roots(model.denominator)) < 1.0)
    internal = interpolate_stable_delayed_paths(
        fir, armax, 0.6, model_id="Shat_beta_0.6"
    )
    assert internal.input_delay_samples == 1
    assert internal.numerator[0] == 0.0
    assert np.all(np.abs(np.roots(internal.denominator)) < 1.0)
    assert BENCHMARK_FAMILY_QUALIFICATION == (
        "exploratory_model_form_benchmark_not_physical_uncertainty"
    )


def test_design_and_heldout_sets_must_be_strictly_separate() -> None:
    validate_design_heldout_split(
        [0.0, 0.5, 1.0], [0.25, 0.75], [300.0, 420.0], [360.0], (300.0, 420.0)
    )
    with pytest.raises(ValueError, match="alpha sets overlap"):
        validate_design_heldout_split(
            [0.0, 0.5], [0.5, 0.75], [300.0], [360.0], (300.0, 420.0)
        )
    with pytest.raises(ValueError, match="frequency sets overlap"):
        validate_design_heldout_split(
            [0.0], [0.5], [300.0, 360.0], [360.0], (300.0, 420.0)
        )


def test_settled_time_rejects_temporary_crossing() -> None:
    disturbance = np.ones(60)
    run = run_fair_imc_fxlms(
        disturbance,
        _fir("true"),
        _fir("hat"),
        _parameters(initial_coefficients=np.asarray([0.0]), actuator_limit=10.0),
        _budget(),
    )
    run.residual[:] = 1.0
    run.residual[:10] = 0.1
    metrics = compute_fair_metrics(
        disturbance, run, 100.0, _metric_specification(), disturbance_peak_bound=2.0
    )
    assert metrics["time_to_10db_status"] == "reached"
    assert metrics["time_to_10db_semantics"].endswith("not_convergence")
    assert metrics["settled_time_to_10db_status"] == "not_reached"
    assert metrics["settled_time_to_10db_seconds"] is None


def test_loss_of_regulation_and_later_settling_are_counted() -> None:
    disturbance = np.ones(60)
    run = run_fair_imc_fxlms(
        disturbance,
        _fir("true"),
        _fir("hat"),
        _parameters(initial_coefficients=np.asarray([0.0]), actuator_limit=10.0),
        _budget(),
    )
    run.residual[:] = 0.2
    run.residual[:10] = 0.1
    run.residual[10:20] = 1.0
    metrics = compute_fair_metrics(
        disturbance, run, 100.0, _metric_specification(), disturbance_peak_bound=2.0
    )
    assert metrics["time_to_10db_seconds"] == pytest.approx(0.1)
    assert metrics["loss_of_regulation_count"] == 1
    assert metrics["settled_time_to_10db_status"] == "reached"
    assert metrics["settled_time_to_10db_seconds"] == pytest.approx(0.3)
    assert metrics["tail_worst_sustained_attenuation_db"] == pytest.approx(
        20.0 * np.log10(5.0)
    )


def test_freeze_update_on_saturation_uses_previous_clip_state() -> None:
    disturbance = np.ones(40)
    frozen = run_fair_imc_fxlms(
        disturbance,
        _fir("true"),
        _fir("hat"),
        _parameters(freeze_update_on_saturation=True),
        _budget(),
    )
    continuing = run_fair_imc_fxlms(
        disturbance,
        _fir("true"),
        _fir("hat"),
        _parameters(freeze_update_on_saturation=False),
        _budget(),
    )
    assert np.count_nonzero(frozen.clipped) > 0
    assert np.count_nonzero(frozen.coefficient_update_frozen) > 0
    assert np.all(
        frozen.coefficient_update_frozen[1:][frozen.clipped[:-1]]
    )
    assert np.count_nonzero(continuing.coefficient_update_frozen) == 0


def test_instantaneous_actuator_slab_projection_enforces_demand_limit() -> None:
    run = run_fair_imc_fxlms(
        np.ones(40),
        _fir("true"),
        _fir("hat"),
        _parameters(actuator_slab_projection=True),
        _budget(),
    )
    assert np.max(np.abs(run.control_demand)) <= 0.1
    assert np.count_nonzero(run.clipped) == 0
    assert np.count_nonzero(run.actuator_slab_projected) > 0


def _candidate_summary(candidate_id: str, *, feasible: bool, tail: float) -> dict:
    return {
        "candidate_id": candidate_id,
        "feasible": feasible,
        "design_tail_worst_sustained_attenuation_db": tail,
        "design_settled_case_count": 0,
        "design_worst_settled_time_to_10db_seconds": None,
        "design_worst_control_rms": 0.1,
        "design_worst_final_coefficient_norm": 0.1,
    }


def test_infeasible_candidate_cannot_win_selection() -> None:
    winner = select_best_candidate(
        [
            _candidate_summary("infeasible", feasible=False, tail=100.0),
            _candidate_summary("feasible", feasible=True, tail=-20.0),
        ]
    )
    assert winner["candidate_id"] == "feasible"


def test_selection_tie_break_is_deterministic() -> None:
    candidates = [
        _candidate_summary("b", feasible=True, tail=0.0),
        _candidate_summary("a", feasible=True, tail=0.0),
    ]
    assert select_best_candidate(candidates)["candidate_id"] == "a"
    assert select_best_candidate(list(reversed(candidates)))["candidate_id"] == "a"


def _tiny_search_config() -> dict:
    return {
        "constraint_modes": [
            {
                "id": "ball_slab",
                "freeze_update_on_saturation": True,
                "actuator_slab_projection": True,
            }
        ],
        "coarse_grid": {
            "internal_model_beta": [0.0],
            "step_size": [0.0, 0.01],
            "leakage": [0.0],
            "coefficient_projection_radius": [1.0],
            "constraint_mode_ids": ["ball_slab"],
        },
        "fine_grid": {
            "internal_model_beta_offsets": [0.0],
            "step_size_multipliers": [1.0],
            "leakage": [0.0],
            "coefficient_projection_radius_multipliers": [1.0],
            "retain_selected_constraint_mode": True,
        },
        "budgets": {
            "max_coarse_candidates": 2,
            "max_fine_candidates": 1,
            "max_total_candidates": 2,
        },
    }


def _tiny_baseline_config() -> dict:
    return {
        "controller_fir_coefficients": 2,
        "normalization_delta": 1e-4,
        "actuator_limit": 4.0,
        "adaptation_start_sample": 0,
        "actuation_ramp_samples": 0,
        "controller_regressor_delay_samples": 1,
        "actuator_slab_relative_margin": 1e-12,
    }


def _tiny_metric_specification() -> FairMetricSpecification:
    return FairMetricSpecification(10.0, 0, 60, 10, 10, 40)


def _tiny_design_case() -> BenchmarkCase:
    samples = np.arange(60)
    return BenchmarkCase(
        case_id="design",
        split="design",
        alpha=0.0,
        frequency_hz=10.0,
        disturbance=np.sin(2.0 * np.pi * 0.1 * samples),
        true_secondary_path=_fir("design_true"),
    )


def _run_tiny_tuning() -> dict:
    return tune_candidates(
        design_cases=[_tiny_design_case()],
        fir_path=_fir(),
        armax_path=_armax(),
        baseline_config=_tiny_baseline_config(),
        search_config=_tiny_search_config(),
        metric_specification=_tiny_metric_specification(),
        plant_information_budget=_budget(),
        disturbance_peak_bound=2.0,
        stability_tolerance=1e-10,
    )


def test_parameter_selection_is_deterministic() -> None:
    first = _run_tiny_tuning()
    second = _run_tiny_tuning()
    assert first["selected_parameters"] == second["selected_parameters"]
    assert first["selected_summary"] == second["selected_summary"]


def test_heldout_data_cannot_affect_already_selected_parameters() -> None:
    assert "heldout" not in inspect.signature(tune_candidates).parameters
    tuning = _run_tiny_tuning()
    selected = tuning["selected_parameters"]
    before = selected.as_dict()
    for scale in (0.1, 10.0):
        heldout_case = BenchmarkCase(
            case_id=f"heldout_{scale}",
            split="heldout_benchmark",
            alpha=0.5,
            frequency_hz=15.0,
            disturbance=scale * np.ones(60),
            true_secondary_path=interpolate_stable_delayed_paths(
                _fir(), _armax(), 0.5, model_id=f"heldout_path_{scale}"
            ),
        )
        evaluate_frozen_candidate(
            selected,
            [heldout_case],
            _fir(),
            _armax(),
            _tiny_baseline_config(),
            _tiny_metric_specification(),
            _budget(),
            disturbance_peak_bound=20.0,
            stability_tolerance=1e-10,
        )
        assert selected.as_dict() == before
