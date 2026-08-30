"""One-command Phase 0.5A corrected IMC-FxLMS baseline audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .baseline import load_stage_suite, run_source_exact
from .fair_baseline import (
    FairBaselineParameters,
    FairMetricSpecification,
    compute_fair_metrics,
    run_fair_imc_fxlms,
)
from .models import DiscreteTransferModel
from .phase0 import _git_commit, _json_ready, _verify_source, run_phase0


def _resolve_models(config: dict[str, Any]) -> dict[str, DiscreteTransferModel]:
    model_configs = (
        config["models"]["nominal_secondary_path"],
        config["models"]["alternative_secondary_path"],
    )
    models = {
        model_config["id"]: DiscreteTransferModel.from_config(model_config)
        for model_config in model_configs
    }
    if len(models) != len(model_configs):
        raise ValueError("duplicate secondary-path model ID")
    return models


def _source_exact_digest() -> str:
    return hashlib.sha256(inspect.getsource(run_source_exact).encode()).hexdigest()


def _working_tree_note(repository: Path) -> str:
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repository, text=True
    )
    if status:
        return "results correspond to the recorded commit plus working-tree changes"
    return "results correspond to the recorded commit with a clean working tree"


def run_phase0_5a(config_path: Path) -> dict[str, Any]:
    repository = config_path.resolve().parents[1]
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    # Re-run Phase 0 historical regression first. This path remains distinct
    # from, and is not used as, the corrected fair baseline.
    historical_summary = run_phase0(config_path)
    expected_source_digest = config["phase0_5a"]["source_exact_function_sha256"]
    actual_source_digest = _source_exact_digest()
    if actual_source_digest != expected_source_digest:
        raise ValueError("historical run_source_exact implementation changed")
    historical_passed = all(
        result["source_reproduction_passed"]
        for result in historical_summary["baseline_results"]
    )
    if not historical_passed:
        raise ValueError("historical MATLAB golden reproduction failed")

    fair_config = config["models"]["fair_imc_fxlms_baseline"]
    scenario_path = Path(fair_config["scenario_data_path"])
    _verify_source(scenario_path, fair_config["scenario_data_sha256"])
    signals = load_stage_suite(scenario_path, fair_config["split"])
    if int(signals["rng_seed"]) != int(fair_config["scenario_seed"]):
        raise ValueError("fair-baseline scenario seed mismatch")
    if float(signals["norm_value"]) != float(
        fair_config["disturbance_rms_normalization"]
    ):
        raise ValueError("fair-baseline disturbance normalization mismatch")

    models = _resolve_models(config)
    metric_config = fair_config["evaluation_metrics"]
    metric_specification = FairMetricSpecification(
        target_attenuation_db=float(metric_config["target_attenuation_db"]),
        evaluation_start_sample=int(metric_config["evaluation_start_sample"]),
        evaluation_stop_sample=int(
            metric_config["evaluation_stop_sample_exclusive"]
        ),
        sustain_duration_samples=int(metric_config["sustain_duration_samples"]),
        metric_step_samples=int(metric_config["metric_step_samples"]),
        tail_evaluation_start_sample=int(
            metric_config["tail_evaluation_start_sample"]
        ),
    )

    fair_results: list[dict[str, Any]] = []
    for case in fair_config["cases"]:
        signal = signals[case["signal_id"]]
        true_model = models[case["true_secondary_path_model_id"]]
        internal_model = models[case["internal_secondary_path_model_id"]]
        signal_sample_rate = float(signal["fs"])
        if true_model.sample_rate_hz != signal_sample_rate:
            raise ValueError(f"true-path sample-rate mismatch in {case['id']}")
        if internal_model.sample_rate_hz != signal_sample_rate:
            raise ValueError(f"internal-path sample-rate mismatch in {case['id']}")

        parameters = FairBaselineParameters(
            controller_coefficients=int(fair_config["controller_fir_coefficients"]),
            step_size=float(case["step_size"]),
            normalization_delta=float(fair_config["normalization_delta"]),
            coefficient_projection_radius=float(
                fair_config["coefficient_projection"]["radius"]
            ),
            actuator_limit=float(fair_config["actuator_saturation"]["limit"]),
            adaptation_start_sample=int(fair_config["adaptation_start_sample"]),
            actuation_ramp_samples=int(fair_config["actuation_ramp_samples"]),
            controller_regressor_delay_samples=int(
                fair_config["controller_regressor_delay_samples"]
            ),
            require_no_clipping=bool(fair_config["require_no_clipping"]),
        )
        disturbance = np.asarray(signal["d"], dtype=float).reshape(-1)
        run = run_fair_imc_fxlms(
            disturbance=disturbance,
            true_secondary_path=true_model,
            internal_secondary_path=internal_model,
            parameters=parameters,
            plant_information_budget=fair_config["plant_information_budget"],
        )
        result = compute_fair_metrics(
            disturbance=disturbance,
            run=run,
            sample_rate_hz=signal_sample_rate,
            specification=metric_specification,
            disturbance_peak_bound=float(config["target"]["disturbance_peak_bound"]),
        )
        prestart_stop = parameters.adaptation_start_sample
        prestart_error = float(
            np.max(
                np.abs(run.residual[:prestart_stop] - disturbance[:prestart_stop]),
                initial=0.0,
            )
        )
        reconstruction_identity_error = float(
            np.max(
                np.abs(
                    run.reconstructed_disturbance
                    - (
                        disturbance
                        + run.true_secondary_output
                        - run.predicted_secondary_output
                    )
                ),
                initial=0.0,
            )
        )
        result.update(
            {
                "case_id": case["id"],
                "signal_id": case["signal_id"],
                "scenario_seed": int(fair_config["scenario_seed"]),
                "step_size": parameters.step_size,
                "controller_coefficients": parameters.controller_coefficients,
                "baseline_configuration_id": fair_config["id"],
                "uncertainty_set_id": config["models"]["uncertainty"]["id"],
                "solver_status": "not_applicable_no_optimization_in_phase0_5a",
                "qualification": fair_config["qualification"],
                "prestart_residual_max_abs_error": prestart_error,
                "reconstruction_identity_max_abs_error": (
                    reconstruction_identity_error
                ),
            }
        )
        fair_results.append(result)

    output_root = (
        repository
        / config["reporting"]["output_directory"]
        / config["phase0_5a"]["corrected_baseline_result_directory"]
    )
    output_root.mkdir(parents=True, exist_ok=True)
    summary = {
        "phase": "0.5A",
        "status": config["project"]["status"],
        "phase0_status": "blocked",
        "commit": _git_commit(repository),
        "working_tree_note": _working_tree_note(repository),
        "configuration": str(config_path.resolve()),
        "model_ids": sorted(models),
        "uncertainty_set_id": config["models"]["uncertainty"]["id"],
        "scenario_seed": int(fair_config["scenario_seed"]),
        "solver_status": "not_applicable_no_optimization_in_phase0_5a",
        "solver_tolerances": {
            "normalization_delta": float(fair_config["normalization_delta"]),
            "source_golden_relative_tolerance": float(
                config["phase0"]["baseline_golden_relative_tolerance"]
            ),
        },
        "historical_source_reproduction": {
            "configuration_id": historical_summary["baseline_configuration_id"],
            "run_source_exact_sha256": actual_source_digest,
            "unchanged": True,
            "golden_reproduction_passed": historical_passed,
            "results": historical_summary["baseline_results"],
            "use_for_fair_comparison": False,
        },
        "fair_baseline_configuration_id": fair_config["id"],
        "plant_information_budget": fair_config["plant_information_budget"],
        "fair_results": fair_results,
        "all_runs_feasible": all(result["feasible"] for result in fair_results),
        "worst_sustained_attenuation_db": min(
            float(result["worst_sustained_attenuation_db"])
            for result in fair_results
        ),
        "worst_control_demand_peak": max(
            float(result["control_demand_peak"]) for result in fair_results
        ),
        "time_to_10db": {
            result["case_id"]: {
                "status": result["time_to_10db_status"],
                "seconds": result["time_to_10db_seconds"],
            }
            for result in fair_results
        },
        "time_to_10db_semantics": "first_hit_diagnostic_not_convergence",
        "settled_time_to_10db": {
            result["case_id"]: {
                "status": result["settled_time_to_10db_status"],
                "seconds": result["settled_time_to_10db_seconds"],
            }
            for result in fair_results
        },
        "robust_stability_margin": None,
        "robust_stability_status": "not_certified_in_phase0_5a",
        "remaining_blockers": config["phase0"]["blockers"],
        "claim_status": "no_superiority_or_robust_stability_claim_made",
    }

    summary_path = output_root / "phase0_5a_summary.json"
    with summary_path.open("w", encoding="utf-8") as stream:
        json.dump(_json_ready(summary), stream, indent=2, sort_keys=True)
        stream.write("\n")

    csv_path = output_root / "fair_baseline_results.csv"
    fields = [
        "case_id",
        "signal_id",
        "scenario_seed",
        "true_secondary_path_model_id",
        "internal_secondary_path_model_id",
        "plant_information_budget_id",
        "adaptation_start_sample",
        "evaluation_start_sample",
        "evaluation_stop_sample_exclusive",
        "tail_evaluation_start_sample",
        "sustain_duration_samples",
        "step_size",
        "evaluation_attenuation_db",
        "worst_sustained_attenuation_db",
        "best_sustained_attenuation_db",
        "time_to_10db_status",
        "time_to_10db_seconds",
        "settled_time_to_10db_status",
        "settled_time_to_10db_seconds",
        "loss_of_regulation_count",
        "control_demand_peak",
        "control_demand_rms",
        "applied_control_peak",
        "applied_control_rms",
        "saturation_count",
        "saturation_fraction",
        "coefficient_projection_count",
        "actuator_slab_projection_count",
        "final_coefficient_norm",
        "feasible",
        "infeasibility_reasons",
        "plant_information_budget",
        "robust_stability_status",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for result in fair_results:
            row = dict(result)
            row["infeasibility_reasons"] = ";".join(result["infeasibility_reasons"])
            row["plant_information_budget"] = result["plant_information_budget"]["id"]
            writer.writerow(row)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiment.yaml")
    )
    args = parser.parse_args()
    summary = run_phase0_5a(args.config)
    print(json.dumps(_json_ready(summary), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
