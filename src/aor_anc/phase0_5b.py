"""Run Phase 0.5B constrained robust fair-baseline tuning and evaluation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .baseline import load_stage_suite
from .fair_baseline import FairMetricSpecification
from .models import DiscreteTransferModel
from .phase0 import _git_commit, _json_ready, _verify_source
from .phase0_5a import _working_tree_note
from .robust_baseline import (
    BENCHMARK_FAMILY_QUALIFICATION,
    BenchmarkCase,
    CandidateParameters,
    aggregate_frozen_results,
    estimate_online_operation_count_per_sample,
    evaluate_frozen_candidate,
    interpolate_stable_delayed_paths,
    make_tone_benchmark_cases,
    tune_candidates,
    validate_design_heldout_split,
)


def _metric_specification(config: dict[str, Any]) -> FairMetricSpecification:
    return FairMetricSpecification(
        target_attenuation_db=float(config["target_attenuation_db"]),
        evaluation_start_sample=int(config["evaluation_start_sample"]),
        evaluation_stop_sample=int(config["evaluation_stop_sample_exclusive"]),
        sustain_duration_samples=int(config["sustain_duration_samples"]),
        metric_step_samples=int(config["metric_step_samples"]),
        tail_evaluation_start_sample=int(config["tail_evaluation_start_sample"]),
    )


def _path_validation_evidence(model: DiscreteTransferModel) -> dict[str, Any]:
    denominator_poles = (
        np.roots(model.denominator)
        if model.denominator.size > 1
        else np.asarray([], dtype=complex)
    )
    return {
        "model_id": model.model_id,
        "causal_z_inverse_realization": True,
        "proper": True,
        "input_delay_samples": model.input_delay_samples,
        "numerator_coefficients": int(model.numerator.size),
        "denominator_coefficients": int(model.denominator.size),
        "max_denominator_pole_radius": float(
            np.max(np.abs(denominator_poles), initial=0.0)
        ),
        "strictly_stable": bool(np.all(np.abs(denominator_poles) < 1.0)),
    }


def _write_candidate_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    fields = [
        "search_stage",
        "candidate_id",
        "beta",
        "step_size",
        "leakage",
        "coefficient_projection_radius",
        "constraint_mode_id",
        "freeze_update_on_saturation",
        "actuator_slab_projection",
        "feasible",
        "evaluated_design_case_count",
        "expected_design_case_count",
        "design_tail_worst_sustained_attenuation_db",
        "design_settled_case_count",
        "design_worst_settled_time_to_10db_seconds",
        "design_worst_control_rms",
        "design_worst_control_demand_peak",
        "design_worst_final_coefficient_norm",
        "design_saturation_count",
        "design_coefficient_projection_count",
        "design_actuator_slab_projection_count",
        "design_loss_of_regulation_count",
        "rejection_reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for candidate in candidates:
            row = dict(candidate)
            row["rejection_reasons"] = ";".join(candidate["rejection_reasons"])
            writer.writerow(row)


def _write_result_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "split",
        "case_id",
        "true_path_alpha",
        "frequency_hz",
        "true_secondary_path_model_id",
        "internal_secondary_path_model_id",
        "candidate_id",
        "plant_information_budget_id",
        "evaluation_start_sample",
        "evaluation_stop_sample_exclusive",
        "tail_evaluation_start_sample",
        "sustain_duration_samples",
        "time_to_10db_status",
        "time_to_10db_seconds",
        "settled_time_to_10db_status",
        "settled_time_to_10db_seconds",
        "loss_of_regulation_count",
        "evaluation_attenuation_db",
        "worst_sustained_attenuation_db",
        "tail_worst_sustained_attenuation_db",
        "control_demand_peak",
        "control_demand_rms",
        "applied_control_peak",
        "applied_control_rms",
        "saturation_count",
        "coefficient_projection_count_total",
        "actuator_slab_projection_count_total",
        "coefficient_update_frozen_count_total",
        "final_coefficient_norm",
        "feasible",
        "infeasibility_reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            row = dict(result)
            row["infeasibility_reasons"] = ";".join(result["infeasibility_reasons"])
            writer.writerow(row)


def run_phase0_5b(config_path: Path) -> dict[str, Any]:
    repository = config_path.resolve().parents[1]
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    phase_config = config["phase0_5b"]
    family_config = phase_config["benchmark_family"]
    if family_config["qualification"] != BENCHMARK_FAMILY_QUALIFICATION:
        raise ValueError("benchmark family is not labelled as exploratory")

    nominal_config = config["models"]["nominal_secondary_path"]
    alternative_config = config["models"]["alternative_secondary_path"]
    _verify_source(Path(nominal_config["source_path"]), nominal_config["source_sha256"])
    _verify_source(
        Path(alternative_config["source_path"]), alternative_config["source_sha256"]
    )
    fir_path = DiscreteTransferModel.from_config(nominal_config)
    armax_path = DiscreteTransferModel.from_config(alternative_config)
    stability_tolerance = float(phase_config["stability_pole_radius_tolerance"])

    design_alphas = [float(value) for value in family_config["design_alphas"]]
    heldout_alphas = [float(value) for value in family_config["heldout_alphas"]]
    design_frequencies = [
        float(value) for value in family_config["design_frequencies_hz"]
    ]
    heldout_frequencies = [
        float(value) for value in family_config["heldout_frequencies_hz"]
    ]
    validate_design_heldout_split(
        design_alphas,
        heldout_alphas,
        design_frequencies,
        heldout_frequencies,
        tuple(float(value) for value in config["target"]["band_hz"]),
    )

    signal_config = phase_config["synthetic_tone_cases"]
    design_cases = make_tone_benchmark_cases(
        split="design",
        alphas=design_alphas,
        frequencies_hz=design_frequencies,
        fir_path=fir_path,
        armax_path=armax_path,
        sample_count=int(signal_config["sample_count"]),
        disturbance_rms=float(signal_config["disturbance_rms"]),
        phase_rad=float(signal_config["phase_rad"]),
        stability_tolerance=stability_tolerance,
    )

    # This call has no held-out or T1/T2 argument. Selection is complete and
    # frozen before either evaluation split is constructed or loaded below.
    tuning = tune_candidates(
        design_cases=design_cases,
        fir_path=fir_path,
        armax_path=armax_path,
        baseline_config=phase_config["candidate_baseline"],
        search_config=phase_config["search"],
        metric_specification=_metric_specification(
            phase_config["design_evaluation_metrics"]
        ),
        plant_information_budget=phase_config["plant_information_budget"],
        disturbance_peak_bound=float(config["target"]["disturbance_peak_bound"]),
        stability_tolerance=stability_tolerance,
    )
    selected: CandidateParameters = tuning["selected_parameters"]
    design_results = tuning["selected_design_results"]
    design_aggregate = aggregate_frozen_results(design_results)
    if design_aggregate["worst_control_demand_peak"] > float(
        config["target"]["control_peak_limit"]
    ):
        raise ValueError("selected candidate violates the hard design demand limit")

    heldout_cases = make_tone_benchmark_cases(
        split="heldout_benchmark",
        alphas=heldout_alphas,
        frequencies_hz=heldout_frequencies,
        fir_path=fir_path,
        armax_path=armax_path,
        sample_count=int(signal_config["sample_count"]),
        disturbance_rms=float(signal_config["disturbance_rms"]),
        phase_rad=float(signal_config["phase_rad"]),
        stability_tolerance=stability_tolerance,
    )
    heldout_results = evaluate_frozen_candidate(
        selected,
        heldout_cases,
        fir_path,
        armax_path,
        phase_config["candidate_baseline"],
        _metric_specification(phase_config["heldout_evaluation_metrics"]),
        phase_config["plant_information_budget"],
        float(config["target"]["disturbance_peak_bound"]),
        stability_tolerance,
    )
    heldout_aggregate = aggregate_frozen_results(heldout_results)

    record_config = phase_config["evaluation_records"]
    scenario_path = Path(record_config["scenario_data_path"])
    _verify_source(scenario_path, record_config["scenario_data_sha256"])
    signals = load_stage_suite(scenario_path, record_config["split"])
    if int(signals["rng_seed"]) != int(record_config["scenario_seed"]):
        raise ValueError("T1/T2 evaluation scenario seed mismatch")
    if float(signals["norm_value"]) != float(
        record_config["disturbance_rms_normalization"]
    ):
        raise ValueError("T1/T2 evaluation normalization mismatch")
    evaluation_cases: list[BenchmarkCase] = []
    for signal_id in record_config["signal_ids"]:
        signal = signals[signal_id]
        if float(signal["fs"]) != fir_path.sample_rate_hz:
            raise ValueError(f"sample-rate mismatch in {signal_id}")
        evaluation_cases.append(
            BenchmarkCase(
                case_id=f"evaluation_record_{signal_id}",
                split="evaluation_records",
                alpha=0.0,
                frequency_hz=None,
                disturbance=np.asarray(signal["d"], dtype=float).reshape(-1),
                true_secondary_path=fir_path,
            )
        )
    evaluation_results = evaluate_frozen_candidate(
        selected,
        evaluation_cases,
        fir_path,
        armax_path,
        phase_config["candidate_baseline"],
        _metric_specification(record_config["evaluation_metrics"]),
        phase_config["plant_information_budget"],
        float(config["target"]["disturbance_peak_bound"]),
        stability_tolerance,
    )
    for result in evaluation_results:
        result["scenario_seed"] = int(record_config["scenario_seed"])
    evaluation_aggregate = aggregate_frozen_results(evaluation_results)

    selected_internal_path = interpolate_stable_delayed_paths(
        fir_path,
        armax_path,
        selected.beta,
        model_id=f"Shat_beta_{selected.beta:.12g}",
        stability_tolerance=stability_tolerance,
    )
    operation_count = estimate_online_operation_count_per_sample(
        selected,
        selected_internal_path,
        int(phase_config["candidate_baseline"]["controller_fir_coefficients"]),
    )
    evaluated_betas = sorted(
        {
            float(candidate["beta"])
            for candidate in tuning["candidate_summaries"]
        }
    )
    internal_path_validation = [
        {
            "beta": beta,
            **_path_validation_evidence(
                interpolate_stable_delayed_paths(
                    fir_path,
                    armax_path,
                    beta,
                    model_id=f"Shat_beta_{beta:.12g}",
                    stability_tolerance=stability_tolerance,
                )
            ),
        }
        for beta in evaluated_betas
    ]
    true_path_validation = [
        {
            "alpha": alpha,
            **_path_validation_evidence(
                interpolate_stable_delayed_paths(
                    fir_path,
                    armax_path,
                    alpha,
                    model_id=f"S_alpha_{alpha:.12g}",
                    stability_tolerance=stability_tolerance,
                )
            ),
        }
        for alpha in sorted(set(design_alphas + heldout_alphas))
    ]

    output_root = (
        repository
        / config["reporting"]["output_directory"]
        / phase_config["result_directory"]
    )
    output_root.mkdir(parents=True, exist_ok=True)
    all_frozen_results = design_results + heldout_results + evaluation_results
    selected_parameters = selected.as_dict()
    selected_parameters["internal_secondary_path_model_id"] = (
        selected_internal_path.model_id
    )
    summary = {
        "phase": "0.5B",
        "status": config["project"]["status"],
        "phase0_status": "blocked",
        "commit": _git_commit(repository),
        "working_tree_note": _working_tree_note(repository),
        "configuration": str(config_path.resolve()),
        "solver_status": "deterministic_finite_coarse_to_fine_search_completed",
        "solver_tolerances": {
            "stability_pole_radius_tolerance": stability_tolerance,
            "normalization_delta": float(
                phase_config["candidate_baseline"]["normalization_delta"]
            ),
            "actuator_slab_relative_margin": float(
                phase_config["candidate_baseline"][
                    "actuator_slab_relative_margin"
                ]
            ),
            "hard_actuator_limit": float(config["target"]["control_peak_limit"]),
        },
        "model_ids": [fir_path.model_id, armax_path.model_id],
        "uncertainty_set_id": config["models"]["uncertainty"]["id"],
        "random_seed": {
            "synthetic_tones": signal_config["random_seed"],
            "evaluation_records": int(record_config["scenario_seed"]),
        },
        "baseline_configuration_id": phase_config["candidate_baseline"]["id"],
        "benchmark_family": {
            **family_config,
            "design_case_ids": [case.case_id for case in design_cases],
            "heldout_case_ids": [case.case_id for case in heldout_cases],
            "is_physical_uncertainty": False,
            "true_path_validation": true_path_validation,
            "internal_path_validation": internal_path_validation,
        },
        "plant_information_budget": phase_config["plant_information_budget"],
        "search": {
            "grids": phase_config["search"],
            "coarse_candidate_count": tuning["coarse_candidate_count"],
            "fine_grid_candidate_count": tuning["fine_grid_candidate_count"],
            "fine_evaluated_candidate_count": tuning[
                "fine_evaluated_candidate_count"
            ],
            "total_evaluated_candidate_count": tuning[
                "total_evaluated_candidate_count"
            ],
            "selection_order": phase_config["selection_order"],
            "selection_uses_only_split": tuning["selection_uses_only_split"],
            "heldout_or_evaluation_data_used_for_selection": False,
            "coarse_selected_summary": tuning["coarse_selected_summary"],
        },
        "selected_parameters": selected_parameters,
        "selected_design_summary": tuning["selected_summary"],
        "design_performance": {
            "aggregate": design_aggregate,
            "cases": design_results,
        },
        "heldout_benchmark_performance": {
            "aggregate": heldout_aggregate,
            "cases": heldout_results,
            "parameters_frozen_without_retuning": True,
        },
        "evaluation_record_performance": {
            "scenario_seed": int(record_config["scenario_seed"]),
            "aggregate": evaluation_aggregate,
            "cases": evaluation_results,
            "parameters_frozen_without_retuning": True,
        },
        "operation_count_per_sample": operation_count,
        "selected_candidate_design_feasible": design_aggregate[
            "all_cases_feasible"
        ],
        "robust_stability_margin": None,
        "robust_stability_status": "not_certified_for_adaptive_baseline",
        "superiority_claim": False,
        "claim_status": "no_robust_stability_or_superiority_claim_made",
        "remaining_blockers": config["phase0"]["blockers"],
    }

    summary_path = output_root / "phase0_5b_summary.json"
    with summary_path.open("w", encoding="utf-8") as stream:
        json.dump(_json_ready(summary), stream, indent=2, sort_keys=True)
        stream.write("\n")
    _write_candidate_csv(
        output_root / "candidate_search.csv", tuning["candidate_summaries"]
    )
    _write_result_csv(output_root / "frozen_evaluation.csv", all_frozen_results)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiment.yaml")
    )
    args = parser.parse_args()
    summary = run_phase0_5b(args.config)
    print(json.dumps(_json_ready(summary), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
