"""One-command Phase 0 audit and source-baseline reproduction."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .baseline import (
    BaselineParameters,
    compute_source_metrics,
    load_stage_suite,
    run_source_exact,
)
from .closed_loop import numerical_transfer_map_audit
from .models import DiscreteTransferModel, plot_model_diagnostics


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repository: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()


def _verify_source(path: Path, expected_sha256: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"required Phase 0 source is missing: {path}")
    actual = _sha256(path)
    if actual != expected_sha256:
        raise ValueError(f"source checksum mismatch for {path}: {actual}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def run_phase0(config_path: Path) -> dict[str, Any]:
    repository = config_path.resolve().parents[1]
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    output_root = repository / config["reporting"]["output_directory"] / "phase0"
    output_root.mkdir(parents=True, exist_ok=True)

    nominal_config = config["models"]["nominal_secondary_path"]
    alternative_config = config["models"]["alternative_secondary_path"]
    nominal = DiscreteTransferModel.from_config(nominal_config)
    alternative = DiscreteTransferModel.from_config(alternative_config)
    if nominal.sample_rate_hz != float(config["signals"]["sample_rate_hz"]):
        raise ValueError("model and signal sample rates differ")

    for model_config in (nominal_config, alternative_config):
        _verify_source(
            Path(model_config["source_path"]), model_config["source_sha256"]
        )

    frequency_points = int(config["phase0"]["model_diagnostic_frequency_points"])
    plot_path = output_root / "nominal_model_diagnostics.png"
    plot_model_diagnostics(nominal, plot_path, frequency_points)
    model_summary = nominal.diagnostic_summary()

    audit_points = int(config["phase0"]["transfer_map_audit_grid_points"])
    omega = np.linspace(0.0, np.pi, audit_points)
    nominal_response = nominal.frequency_response(omega)
    transfer_audit = numerical_transfer_map_audit(nominal_response, omega)
    tolerance = float(config["numerics"]["frequency_response_relative_tolerance"])
    transfer_audit["tolerance"] = tolerance
    transfer_audit["passed"] = max(
        value for key, value in transfer_audit.items() if key.endswith("relative_error")
    ) < tolerance

    uncertainty = config["models"]["uncertainty"]
    dense_omega = np.linspace(0.0, np.pi, 262145)
    difference = alternative.frequency_response(dense_omega) - nominal.frequency_response(
        dense_omega
    )
    dense_peak_index = int(np.argmax(np.abs(difference)))
    weight_gain = float(uncertainty["weight_model"]["gain"])
    uncertainty_check = {
        "weight_id": uncertainty["id"],
        "weight_gain": weight_gain,
        "dense_grid_points": int(dense_omega.size),
        "dense_grid_peak": float(np.abs(difference[dense_peak_index])),
        "dense_grid_peak_frequency_hz": float(
            dense_omega[dense_peak_index]
            * nominal.sample_rate_hz
            / (2.0 * np.pi)
        ),
        "dense_grid_normalized_peak": float(
            np.abs(difference[dense_peak_index]) / weight_gain
        ),
        "continuous_reference_hinf_norm": float(
            uncertainty["weight_model"]["reference_hinf_norm"]
        ),
        "continuous_reference_hinf_relative_tolerance": float(
            uncertainty["weight_model"]["reference_hinf_relative_tolerance"]
        ),
        "continuous_reference_method": uncertainty["weight_model"][
            "construction_method"
        ],
        "coverage_status": uncertainty["weight_model"]["status"],
        "dense_grid_is_continuous_proof": False,
    }

    baseline_config = config["models"]["existing_imc_fxlms_baseline"]
    source_path = Path(baseline_config["source_path"])
    scenario_path = Path(baseline_config["scenario_data_path"])
    _verify_source(source_path, baseline_config["source_sha256"])
    _verify_source(scenario_path, baseline_config["scenario_data_sha256"])
    signals = load_stage_suite(scenario_path, baseline_config["split"])
    if int(signals["rng_seed"]) != int(baseline_config["scenario_seed"]):
        raise ValueError("scenario seed does not equal configured baseline seed")
    if float(signals["norm_value"]) != float(
        baseline_config["disturbance_rms_normalization"]
    ):
        raise ValueError("scenario normalization does not equal configured value")
    model_data = signals["model_data"]
    numerator = np.asarray(model_data["B"], dtype=float).reshape(-1)
    denominator = np.asarray(model_data["A"], dtype=float).reshape(-1)
    if not np.array_equal(numerator, nominal.numerator) or not np.array_equal(
        denominator, nominal.denominator
    ):
        raise ValueError("scenario model does not exactly equal configured nominal model")

    baseline_results: list[dict[str, Any]] = []
    golden_tolerance = float(config["phase0"]["baseline_golden_relative_tolerance"])
    for case in baseline_config["cases"]:
        case_id = case["id"]
        test_signal = signals[case_id]
        parameters = BaselineParameters(
            controller_coefficients=int(
                baseline_config["controller_fir_coefficients"]
            ),
            step_size=float(case["step_size"]),
            delta=float(baseline_config["delta"]),
            ramp_seconds=float(baseline_config["ramp_seconds"]),
            coefficient_norm_limit=float(
                baseline_config["coefficient_norm_limit"]
            ),
            actuator_limit=float(baseline_config["actuator_limit"]),
        )
        disturbance = np.asarray(test_signal["d"], dtype=float).reshape(-1)
        disturbance_peak = float(np.max(np.abs(disturbance)))
        run = run_source_exact(
            disturbance,
            float(test_signal["fs"]),
            numerator,
            denominator,
            parameters,
        )
        metrics = compute_source_metrics(
            disturbance,
            run,
            float(test_signal["fs"]),
            float(test_signal["Tsim"]),
        )
        golden = case["golden_source_metrics"]
        golden_errors: dict[str, float] = {}
        for key, expected in golden.items():
            actual = float(metrics[key])
            scale = max(abs(actual), abs(float(expected)), 1e-14)
            golden_errors[key] = abs(actual - float(expected)) / scale
        metrics.update(
            {
                "case_id": case_id,
                "scenario_seed": int(baseline_config["scenario_seed"]),
                "step_size": parameters.step_size,
                "disturbance_peak": disturbance_peak,
                "disturbance_bound": float(
                    config["target"]["disturbance_peak_bound"]
                ),
                "disturbance_bound_satisfied": disturbance_peak
                <= float(config["target"]["disturbance_peak_bound"]),
                "golden_max_relative_error": max(golden_errors.values()),
                "golden_tolerance": golden_tolerance,
                "source_reproduction_passed": max(golden_errors.values())
                < golden_tolerance,
                "actuator_constraint_satisfied": bool(
                    metrics["unclipped_control_peak"]
                    <= float(config["target"]["control_peak_limit"])
                    and metrics["saturation_count"] == 0
                ),
                "robust_stability_margin": None,
                "robust_stability_status": "not_certified_for_adaptive_baseline",
            }
        )
        baseline_results.append(metrics)

    summary = {
        "phase": 0,
        "status": config["project"]["status"],
        "commit": _git_commit(repository),
        "working_tree_note": "results correspond to this commit plus uncommitted Phase 0 changes",
        "configuration": str(config_path.resolve()),
        "model_id": nominal.model_id,
        "uncertainty_id": uncertainty["id"],
        "random_seed": int(config["numerics"]["random_seed"]),
        "solver_status": "not_applicable_no_optimization_in_phase0",
        "solver_tolerances": {
            "frequency_response_relative_tolerance": tolerance,
            "baseline_golden_relative_tolerance": golden_tolerance,
        },
        "model_diagnostics": model_summary,
        "model_plot": str(plot_path.resolve()),
        "transfer_map_audit": transfer_audit,
        "uncertainty_check": uncertainty_check,
        "baseline_configuration_id": baseline_config["id"],
        "baseline_results": baseline_results,
        "worst_case_attenuation_db": min(
            float(result["attenuation_db"]) for result in baseline_results
        ),
        "worst_case_control_peak": max(
            float(result["unclipped_control_peak"]) for result in baseline_results
        ),
        "convergence_metric_status": "invalid_for_source_baseline_due_to_prestart_zero_residual",
        "robust_stability_margin": None,
        "robust_stability_status": "not_certified_in_phase0",
        "blockers": config["phase0"]["blockers"],
        "claim_status": "no_research_claim_made",
    }

    summary_path = output_root / "phase0_summary.json"
    with summary_path.open("w", encoding="utf-8") as stream:
        json.dump(_json_ready(summary), stream, indent=2, sort_keys=True)
        stream.write("\n")

    csv_path = output_root / "baseline_reproduction.csv"
    fields = [
        "case_id",
        "scenario_seed",
        "step_size",
        "attenuation_db",
        "control_peak",
        "unclipped_control_peak",
        "control_rms",
        "saturation_count",
        "coefficient_norm",
        "convergence_time_s",
        "convergence_metric_valid",
        "disturbance_peak",
        "disturbance_bound_satisfied",
        "source_reproduction_passed",
        "actuator_constraint_satisfied",
        "robust_stability_status",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(baseline_results)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiment.yaml")
    )
    args = parser.parse_args()
    summary = run_phase0(args.config)
    print(json.dumps(_json_ready(summary), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
