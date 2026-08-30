"""Exploratory robust tuning utilities for the fair IMC-FxLMS baseline.

The interpolated path family in this module is a finite model-form benchmark.
It is not a physical uncertainty set and carries no robust-stability claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable

import numpy as np

from .fair_baseline import (
    FairBaselineParameters,
    FairMetricSpecification,
    compute_fair_metrics,
    run_fair_imc_fxlms,
)
from .models import DiscreteTransferModel


BENCHMARK_FAMILY_QUALIFICATION = (
    "exploratory_model_form_benchmark_not_physical_uncertainty"
)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    split: str
    alpha: float
    frequency_hz: float | None
    disturbance: np.ndarray
    true_secondary_path: DiscreteTransferModel


@dataclass(frozen=True)
class CandidateParameters:
    beta: float
    step_size: float
    leakage: float
    coefficient_projection_radius: float
    constraint_mode_id: str
    freeze_update_on_saturation: bool
    actuator_slab_projection: bool

    @property
    def candidate_id(self) -> str:
        return (
            f"beta={self.beta:.12g}|mu={self.step_size:.12g}"
            f"|leak={self.leakage:.12g}"
            f"|radius={self.coefficient_projection_radius:.12g}"
            f"|mode={self.constraint_mode_id}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "beta": self.beta,
            "step_size": self.step_size,
            "leakage": self.leakage,
            "coefficient_projection_radius": self.coefficient_projection_radius,
            "constraint_mode_id": self.constraint_mode_id,
            "freeze_update_on_saturation": self.freeze_update_on_saturation,
            "actuator_slab_projection": self.actuator_slab_projection,
        }


def _padded(values: np.ndarray, length: int) -> np.ndarray:
    return np.pad(values, (0, length - values.size))


def _strictly_stable(model: DiscreteTransferModel, tolerance: float) -> bool:
    if model.denominator.size <= 1:
        return True
    poles = np.roots(model.denominator)
    return bool(np.all(np.abs(poles) < 1.0 - tolerance))


def interpolate_stable_delayed_paths(
    fir_path: DiscreteTransferModel,
    armax_path: DiscreteTransferModel,
    mix: float,
    *,
    model_id: str,
    stability_tolerance: float = 1e-10,
) -> DiscreteTransferModel:
    """Construct ``(1-mix) * S_fir + mix * S_armax`` exactly.

    Interior points use a common denominator. Endpoints retain the exact source
    realization. Every returned model is independently checked for the common
    sample rate, declared delay, finite coefficients, and strict pole stability.
    """

    fir_path.validate()
    armax_path.validate()
    if not 0.0 <= mix <= 1.0:
        raise ValueError("path interpolation factor must lie in [0, 1]")
    if fir_path.sample_rate_hz != armax_path.sample_rate_hz:
        raise ValueError("path-family endpoints have different sample rates")
    if fir_path.input_delay_samples != armax_path.input_delay_samples:
        raise ValueError("path-family endpoints have different delays")
    if not _strictly_stable(fir_path, stability_tolerance):
        raise ValueError("FIR endpoint is not strictly stable")
    if not _strictly_stable(armax_path, stability_tolerance):
        raise ValueError("ARMAX endpoint is not strictly stable")

    if mix == 0.0:
        numerator = fir_path.numerator.copy()
        denominator = fir_path.denominator.copy()
    elif mix == 1.0:
        numerator = armax_path.numerator.copy()
        denominator = armax_path.denominator.copy()
    else:
        denominator = np.convolve(fir_path.denominator, armax_path.denominator)
        fir_numerator = np.convolve(fir_path.numerator, armax_path.denominator)
        armax_numerator = np.convolve(
            armax_path.numerator, fir_path.denominator
        )
        length = max(fir_numerator.size, armax_numerator.size)
        numerator = (1.0 - mix) * _padded(fir_numerator, length)
        numerator += mix * _padded(armax_numerator, length)
        numerator /= denominator[0]
        denominator = denominator / denominator[0]

    model = DiscreteTransferModel(
        model_id=model_id,
        numerator=np.asarray(numerator, dtype=float),
        denominator=np.asarray(denominator, dtype=float),
        sample_rate_hz=fir_path.sample_rate_hz,
        input_delay_samples=fir_path.input_delay_samples,
    )
    model.validate()
    if model.input_delay_samples != fir_path.input_delay_samples:
        raise ValueError("interpolation changed the declared path delay")
    if not _strictly_stable(model, stability_tolerance):
        raise ValueError("interpolated path is not strictly stable")
    return model


def validate_design_heldout_split(
    design_alphas: Iterable[float],
    heldout_alphas: Iterable[float],
    design_frequencies_hz: Iterable[float],
    heldout_frequencies_hz: Iterable[float],
    frequency_band_hz: tuple[float, float],
) -> None:
    design_alpha_set = {float(value) for value in design_alphas}
    heldout_alpha_set = {float(value) for value in heldout_alphas}
    design_frequency_set = {float(value) for value in design_frequencies_hz}
    heldout_frequency_set = {float(value) for value in heldout_frequencies_hz}
    if not design_alpha_set or not heldout_alpha_set:
        raise ValueError("design and held-out alpha sets must both be nonempty")
    if not design_frequency_set or not heldout_frequency_set:
        raise ValueError("design and held-out frequency sets must both be nonempty")
    if design_alpha_set & heldout_alpha_set:
        raise ValueError("design and held-out alpha sets overlap")
    if design_frequency_set & heldout_frequency_set:
        raise ValueError("design and held-out frequency sets overlap")
    if any(value < 0.0 or value > 1.0 for value in design_alpha_set | heldout_alpha_set):
        raise ValueError("benchmark alpha lies outside [0, 1]")
    lower, upper = frequency_band_hz
    if any(
        value < lower or value > upper
        for value in design_frequency_set | heldout_frequency_set
    ):
        raise ValueError("benchmark frequency lies outside the declared band")


def make_tone_benchmark_cases(
    *,
    split: str,
    alphas: Iterable[float],
    frequencies_hz: Iterable[float],
    fir_path: DiscreteTransferModel,
    armax_path: DiscreteTransferModel,
    sample_count: int,
    disturbance_rms: float,
    phase_rad: float,
    stability_tolerance: float,
) -> list[BenchmarkCase]:
    if sample_count <= 0 or disturbance_rms <= 0.0:
        raise ValueError("invalid tone benchmark length or RMS")
    cases: list[BenchmarkCase] = []
    sample_index = np.arange(sample_count, dtype=float)
    for alpha, frequency_hz in product(alphas, frequencies_hz):
        alpha_value = float(alpha)
        frequency_value = float(frequency_hz)
        path = interpolate_stable_delayed_paths(
            fir_path,
            armax_path,
            alpha_value,
            model_id=f"S_alpha_{alpha_value:.12g}_{split}",
            stability_tolerance=stability_tolerance,
        )
        disturbance = np.sqrt(2.0) * disturbance_rms * np.sin(
            2.0
            * np.pi
            * frequency_value
            * sample_index
            / fir_path.sample_rate_hz
            + phase_rad
        )
        cases.append(
            BenchmarkCase(
                case_id=(
                    f"{split}_alpha_{alpha_value:.12g}"
                    f"_frequency_{frequency_value:.12g}hz"
                ),
                split=split,
                alpha=alpha_value,
                frequency_hz=frequency_value,
                disturbance=disturbance,
                true_secondary_path=path,
            )
        )
    return cases


def _constraint_modes(search_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    modes = {mode["id"]: mode for mode in search_config["constraint_modes"]}
    if len(modes) != len(search_config["constraint_modes"]):
        raise ValueError("duplicate constraint mode ID")
    return modes


def _candidate(
    beta: float,
    step_size: float,
    leakage: float,
    radius: float,
    mode: dict[str, Any],
) -> CandidateParameters:
    return CandidateParameters(
        beta=float(beta),
        step_size=float(step_size),
        leakage=float(leakage),
        coefficient_projection_radius=float(radius),
        constraint_mode_id=str(mode["id"]),
        freeze_update_on_saturation=bool(mode["freeze_update_on_saturation"]),
        actuator_slab_projection=bool(mode["actuator_slab_projection"]),
    )


def enumerate_coarse_candidates(search_config: dict[str, Any]) -> list[CandidateParameters]:
    coarse = search_config["coarse_grid"]
    modes = _constraint_modes(search_config)
    candidates = [
        _candidate(beta, step, leakage, radius, modes[mode_id])
        for beta, step, leakage, radius, mode_id in product(
            coarse["internal_model_beta"],
            coarse["step_size"],
            coarse["leakage"],
            coarse["coefficient_projection_radius"],
            coarse["constraint_mode_ids"],
        )
    ]
    if len(candidates) > int(search_config["budgets"]["max_coarse_candidates"]):
        raise ValueError("coarse candidate grid exceeds its declared budget")
    return candidates


def enumerate_fine_candidates(
    selected: CandidateParameters, search_config: dict[str, Any]
) -> list[CandidateParameters]:
    fine = search_config["fine_grid"]
    modes = _constraint_modes(search_config)
    mode_ids = (
        [selected.constraint_mode_id]
        if bool(fine["retain_selected_constraint_mode"])
        else list(fine["constraint_mode_ids"])
    )
    betas = sorted(
        {
            min(1.0, max(0.0, selected.beta + float(offset)))
            for offset in fine["internal_model_beta_offsets"]
        }
    )
    steps = sorted(
        {selected.step_size * float(multiplier) for multiplier in fine["step_size_multipliers"]}
    )
    leakages = sorted({float(value) for value in fine["leakage"]})
    radii = sorted(
        {
            selected.coefficient_projection_radius * float(multiplier)
            for multiplier in fine["coefficient_projection_radius_multipliers"]
        }
    )
    candidates = [
        _candidate(beta, step, leakage, radius, modes[mode_id])
        for beta, step, leakage, radius, mode_id in product(
            betas, steps, leakages, radii, mode_ids
        )
    ]
    if len(candidates) > int(search_config["budgets"]["max_fine_candidates"]):
        raise ValueError("fine candidate grid exceeds its declared budget")
    return candidates


def _parameters_for_candidate(
    candidate: CandidateParameters, baseline_config: dict[str, Any]
) -> FairBaselineParameters:
    return FairBaselineParameters(
        controller_coefficients=int(baseline_config["controller_fir_coefficients"]),
        step_size=candidate.step_size,
        normalization_delta=float(baseline_config["normalization_delta"]),
        coefficient_projection_radius=candidate.coefficient_projection_radius,
        actuator_limit=float(baseline_config["actuator_limit"]),
        adaptation_start_sample=int(baseline_config["adaptation_start_sample"]),
        actuation_ramp_samples=int(baseline_config["actuation_ramp_samples"]),
        controller_regressor_delay_samples=int(
            baseline_config["controller_regressor_delay_samples"]
        ),
        require_no_clipping=True,
        leakage=candidate.leakage,
        freeze_update_on_saturation=candidate.freeze_update_on_saturation,
        actuator_slab_projection=candidate.actuator_slab_projection,
        actuator_slab_relative_margin=float(
            baseline_config["actuator_slab_relative_margin"]
        ),
    )


def evaluate_frozen_candidate(
    candidate: CandidateParameters,
    cases: list[BenchmarkCase],
    fir_path: DiscreteTransferModel,
    armax_path: DiscreteTransferModel,
    baseline_config: dict[str, Any],
    metric_specification: FairMetricSpecification,
    plant_information_budget: dict[str, Any],
    disturbance_peak_bound: float | None,
    stability_tolerance: float,
) -> list[dict[str, Any]]:
    internal_path = interpolate_stable_delayed_paths(
        fir_path,
        armax_path,
        candidate.beta,
        model_id=f"Shat_beta_{candidate.beta:.12g}",
        stability_tolerance=stability_tolerance,
    )
    parameters = _parameters_for_candidate(candidate, baseline_config)
    results: list[dict[str, Any]] = []
    for case in cases:
        run = run_fair_imc_fxlms(
            disturbance=case.disturbance,
            true_secondary_path=case.true_secondary_path,
            internal_secondary_path=internal_path,
            parameters=parameters,
            plant_information_budget=plant_information_budget,
        )
        metrics = compute_fair_metrics(
            disturbance=case.disturbance,
            run=run,
            sample_rate_hz=case.true_secondary_path.sample_rate_hz,
            specification=metric_specification,
            disturbance_peak_bound=disturbance_peak_bound,
        )
        metrics.update(
            {
                "case_id": case.case_id,
                "split": case.split,
                "true_path_alpha": case.alpha,
                "frequency_hz": case.frequency_hz,
                "candidate_id": candidate.candidate_id,
                "candidate_parameters": candidate.as_dict(),
                "baseline_configuration_id": baseline_config.get(
                    "id", "unspecified_test_configuration"
                ),
                "benchmark_family_qualification": BENCHMARK_FAMILY_QUALIFICATION,
            }
        )
        results.append(metrics)
    return results


def summarize_candidate(
    candidate: CandidateParameters,
    case_results: list[dict[str, Any]],
    expected_case_count: int,
    actuator_limit: float,
) -> dict[str, Any]:
    numerical_failures = sum(
        int(result["numerical_failure_count"]) for result in case_results
    )
    demand_violation_count = sum(
        int(result["control_demand_limit_violation_count"])
        for result in case_results
    )
    completed = len(case_results) == expected_case_count
    feasible = completed and numerical_failures == 0 and demand_violation_count == 0
    settled_times = [
        float(result["settled_time_to_10db_seconds"])
        for result in case_results
        if result["settled_time_to_10db_status"] == "reached"
    ]
    summary = {
        **candidate.as_dict(),
        "feasible": feasible,
        "evaluated_design_case_count": len(case_results),
        "expected_design_case_count": expected_case_count,
        "numerical_failure_count": numerical_failures,
        "control_demand_limit_violation_count": demand_violation_count,
        "actuator_limit": actuator_limit,
        "design_tail_worst_sustained_attenuation_db": (
            min(
                float(result["tail_worst_sustained_attenuation_db"])
                for result in case_results
            )
            if case_results
            else None
        ),
        "design_settled_case_count": len(settled_times),
        "design_worst_settled_time_to_10db_seconds": (
            max(settled_times) if settled_times else None
        ),
        "design_worst_control_rms": (
            max(float(result["applied_control_rms"]) for result in case_results)
            if case_results
            else None
        ),
        "design_worst_control_demand_peak": (
            max(float(result["control_demand_peak"]) for result in case_results)
            if case_results
            else None
        ),
        "design_worst_final_coefficient_norm": (
            max(float(result["final_coefficient_norm"]) for result in case_results)
            if case_results
            else None
        ),
        "design_saturation_count": sum(
            int(result["saturation_count"]) for result in case_results
        ),
        "design_coefficient_projection_count": sum(
            int(result["coefficient_projection_count_total"])
            for result in case_results
        ),
        "design_actuator_slab_projection_count": sum(
            int(result["actuator_slab_projection_count_total"])
            for result in case_results
        ),
        "design_loss_of_regulation_count": sum(
            int(result["loss_of_regulation_count"]) for result in case_results
        ),
        "rejection_reasons": [],
    }
    if not completed:
        summary["rejection_reasons"].append("incomplete_design_evaluation")
    if numerical_failures:
        summary["rejection_reasons"].append("numerical_failure")
    if demand_violation_count:
        summary["rejection_reasons"].append("requested_control_exceeds_limit")
    return summary


def candidate_selection_key(summary: dict[str, Any]) -> tuple[Any, ...]:
    if not summary["feasible"]:
        raise ValueError("infeasible candidate has no selection key")
    settled_time = summary["design_worst_settled_time_to_10db_seconds"]
    return (
        -float(summary["design_tail_worst_sustained_attenuation_db"]),
        -int(summary["design_settled_case_count"]),
        float("inf") if settled_time is None else float(settled_time),
        float(summary["design_worst_control_rms"]),
        float(summary["design_worst_final_coefficient_norm"]),
        str(summary["candidate_id"]),
    )


def select_best_candidate(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = [summary for summary in summaries if summary["feasible"]]
    if not feasible:
        raise ValueError("no no-clipping candidate exists on the design set")
    return min(feasible, key=candidate_selection_key)


def _evaluate_for_tuning(
    candidate: CandidateParameters,
    design_cases: list[BenchmarkCase],
    fir_path: DiscreteTransferModel,
    armax_path: DiscreteTransferModel,
    baseline_config: dict[str, Any],
    metric_specification: FairMetricSpecification,
    plant_information_budget: dict[str, Any],
    disturbance_peak_bound: float | None,
    stability_tolerance: float,
) -> dict[str, Any]:
    # Candidates that violate the hard demand bound are rejected immediately;
    # unvisited design cases cannot improve or rescue an infeasible candidate.
    results: list[dict[str, Any]] = []
    for case in design_cases:
        case_results = evaluate_frozen_candidate(
            candidate,
            [case],
            fir_path,
            armax_path,
            baseline_config,
            metric_specification,
            plant_information_budget,
            disturbance_peak_bound,
            stability_tolerance,
        )
        result = case_results[0]
        results.append(result)
        if (
            int(result["numerical_failure_count"]) > 0
            or float(result["control_demand_peak"])
            > float(baseline_config["actuator_limit"])
        ):
            break
    return summarize_candidate(
        candidate,
        results,
        expected_case_count=len(design_cases),
        actuator_limit=float(baseline_config["actuator_limit"]),
    )


def tune_candidates(
    *,
    design_cases: list[BenchmarkCase],
    fir_path: DiscreteTransferModel,
    armax_path: DiscreteTransferModel,
    baseline_config: dict[str, Any],
    search_config: dict[str, Any],
    metric_specification: FairMetricSpecification,
    plant_information_budget: dict[str, Any],
    disturbance_peak_bound: float | None,
    stability_tolerance: float,
) -> dict[str, Any]:
    """Tune from design cases only, then return frozen selected parameters."""

    if not design_cases or any(case.split != "design" for case in design_cases):
        raise ValueError("tuning accepts only a nonempty design split")
    coarse_candidates = enumerate_coarse_candidates(search_config)
    summaries: list[dict[str, Any]] = []
    for candidate in coarse_candidates:
        summary = _evaluate_for_tuning(
            candidate,
            design_cases,
            fir_path,
            armax_path,
            baseline_config,
            metric_specification,
            plant_information_budget,
            disturbance_peak_bound,
            stability_tolerance,
        )
        summary["search_stage"] = "coarse"
        summaries.append(summary)

    coarse_selected_summary = select_best_candidate(summaries)
    coarse_lookup = {candidate.candidate_id: candidate for candidate in coarse_candidates}
    coarse_selected = coarse_lookup[coarse_selected_summary["candidate_id"]]
    fine_candidates = enumerate_fine_candidates(coarse_selected, search_config)
    already_evaluated = {summary["candidate_id"] for summary in summaries}
    fine_evaluated = 0
    candidate_lookup = dict(coarse_lookup)
    for candidate in fine_candidates:
        candidate_lookup[candidate.candidate_id] = candidate
        if candidate.candidate_id in already_evaluated:
            continue
        summary = _evaluate_for_tuning(
            candidate,
            design_cases,
            fir_path,
            armax_path,
            baseline_config,
            metric_specification,
            plant_information_budget,
            disturbance_peak_bound,
            stability_tolerance,
        )
        summary["search_stage"] = "fine"
        summaries.append(summary)
        already_evaluated.add(candidate.candidate_id)
        fine_evaluated += 1

    if len(summaries) > int(search_config["budgets"]["max_total_candidates"]):
        raise ValueError("coarse-to-fine search exceeded its declared total budget")
    selected_summary = select_best_candidate(summaries)
    selected = candidate_lookup[selected_summary["candidate_id"]]
    selected_design_results = evaluate_frozen_candidate(
        selected,
        design_cases,
        fir_path,
        armax_path,
        baseline_config,
        metric_specification,
        plant_information_budget,
        disturbance_peak_bound,
        stability_tolerance,
    )
    return {
        "selected_parameters": selected,
        "coarse_selected_summary": coarse_selected_summary,
        "selected_summary": selected_summary,
        "selected_design_results": selected_design_results,
        "candidate_summaries": summaries,
        "coarse_candidate_count": len(coarse_candidates),
        "fine_grid_candidate_count": len(fine_candidates),
        "fine_evaluated_candidate_count": fine_evaluated,
        "total_evaluated_candidate_count": len(summaries),
        "selection_uses_only_split": "design",
    }


def aggregate_frozen_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("cannot aggregate an empty result set")
    settled_times = [
        float(result["settled_time_to_10db_seconds"])
        for result in results
        if result["settled_time_to_10db_status"] == "reached"
    ]
    return {
        "case_count": len(results),
        "feasible_case_count": sum(bool(result["feasible"]) for result in results),
        "all_cases_feasible": all(bool(result["feasible"]) for result in results),
        "tail_worst_sustained_attenuation_db": min(
            float(result["tail_worst_sustained_attenuation_db"])
            for result in results
        ),
        "worst_sustained_attenuation_db": min(
            float(result["worst_sustained_attenuation_db"]) for result in results
        ),
        "settled_case_count": len(settled_times),
        "worst_settled_time_to_10db_seconds": (
            max(settled_times) if settled_times else None
        ),
        "loss_of_regulation_count": sum(
            int(result["loss_of_regulation_count"]) for result in results
        ),
        "worst_control_demand_peak": max(
            float(result["control_demand_peak"]) for result in results
        ),
        "worst_applied_control_rms": max(
            float(result["applied_control_rms"]) for result in results
        ),
        "saturation_count": sum(int(result["saturation_count"]) for result in results),
        "coefficient_projection_count": sum(
            int(result["coefficient_projection_count_total"]) for result in results
        ),
        "actuator_slab_projection_count": sum(
            int(result["actuator_slab_projection_count_total"]) for result in results
        ),
        "coefficient_update_frozen_count": sum(
            int(result["coefficient_update_frozen_count_total"]) for result in results
        ),
    }


def estimate_online_operation_count_per_sample(
    candidate: CandidateParameters,
    internal_path: DiscreteTransferModel,
    controller_coefficients: int,
) -> dict[str, Any]:
    """Count scalar real arithmetic in the steady-state Python algorithm.

    Memory accesses, indexing, comparisons, and evaluation-engine true-path
    filtering are excluded. The worst-case count includes active coefficient
    ball and actuator-slab projections.
    """

    taps = int(internal_path.numerator.size)
    recursive_terms = int(internal_path.denominator.size - 1)
    order = int(controller_coefficients)
    base_multiply = 2 * (taps + recursive_terms)
    base_add_subtract = 2 * (taps + recursive_terms + 1) + 1
    base_divide = 2

    base_multiply += order  # filtered-vector norm
    base_add_subtract += order  # norm accumulation plus delta
    if candidate.leakage:
        base_multiply += order + 1
        base_add_subtract += 1
    base_multiply += order + 2  # gradient and vector scaling
    base_add_subtract += order
    base_divide += 1
    base_multiply += order  # coefficient norm
    base_add_subtract += max(0, order - 1)
    base_multiply += order + order  # ramped regressor and control dot
    base_add_subtract += max(0, order - 1)

    worst_multiply = base_multiply + order  # active ball projection
    worst_add_subtract = base_add_subtract
    worst_divide = base_divide + 1
    worst_sqrt = 1
    if candidate.actuator_slab_projection:
        worst_multiply += 3 * order
        worst_add_subtract += 3 * order - 1
        worst_divide += 1

    return {
        "counting_scope": "controller_only_steady_state_scalar_real_arithmetic",
        "excluded": [
            "memory_access_and_indexing",
            "comparisons",
            "evaluation_engine_true_path_filter",
        ],
        "internal_model_numerator_taps": taps,
        "internal_model_recursive_terms": recursive_terms,
        "controller_coefficients": order,
        "ordinary_sample": {
            "multiplications": base_multiply,
            "additions_subtractions": base_add_subtract,
            "divisions": base_divide,
            "square_roots": 1,
        },
        "worst_case_active_ball_and_slab_projection": {
            "multiplications": worst_multiply,
            "additions_subtractions": worst_add_subtract,
            "divisions": worst_divide,
            "square_roots": worst_sqrt,
        },
    }
