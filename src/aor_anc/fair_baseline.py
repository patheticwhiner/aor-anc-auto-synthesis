"""Corrected, information-fair feedback IMC-FxLMS baseline.

This module is deliberately separate from :mod:`aor_anc.baseline`, whose
``run_source_exact`` function preserves the historical MATLAB behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import DiscreteTransferModel


@dataclass(frozen=True)
class FairBaselineParameters:
    controller_coefficients: int
    step_size: float
    normalization_delta: float
    coefficient_projection_radius: float
    actuator_limit: float
    adaptation_start_sample: int
    actuation_ramp_samples: int
    controller_regressor_delay_samples: int
    require_no_clipping: bool
    initial_coefficients: np.ndarray | None = None
    leakage: float = 0.0
    freeze_update_on_saturation: bool = False
    actuator_slab_projection: bool = False
    actuator_slab_relative_margin: float = 1e-12

    def validate(self) -> None:
        if self.controller_coefficients <= 0:
            raise ValueError("controller coefficient count must be positive")
        if self.step_size < 0.0:
            raise ValueError("normalized FxLMS step size must be nonnegative")
        if self.leakage < 0.0:
            raise ValueError("leakage must be nonnegative")
        if self.step_size * self.leakage > 1.0:
            raise ValueError("step size times leakage must not exceed one")
        if self.normalization_delta <= 0.0:
            raise ValueError("normalization delta must be positive")
        if self.coefficient_projection_radius <= 0.0:
            raise ValueError("coefficient projection radius must be positive")
        if self.actuator_limit <= 0.0:
            raise ValueError("actuator limit must be positive")
        if self.adaptation_start_sample < 0:
            raise ValueError("adaptation start sample must be nonnegative")
        if self.actuation_ramp_samples < 0:
            raise ValueError("actuation ramp samples must be nonnegative")
        if self.controller_regressor_delay_samples < 1:
            raise ValueError("controller regressor needs at least one sample delay")
        if not 0.0 <= self.actuator_slab_relative_margin < 1.0:
            raise ValueError("actuator slab relative margin must lie in [0, 1)")
        if self.initial_coefficients is not None:
            initial = np.asarray(self.initial_coefficients, dtype=float).reshape(-1)
            if initial.size != self.controller_coefficients:
                raise ValueError("initial coefficient dimension mismatch")
            if not np.all(np.isfinite(initial)):
                raise ValueError("initial coefficients must be finite")


@dataclass
class FairBaselineRun:
    residual: np.ndarray
    applied_control: np.ndarray
    control_demand: np.ndarray
    clipped: np.ndarray
    true_secondary_output: np.ndarray
    predicted_secondary_output: np.ndarray
    reconstructed_disturbance: np.ndarray
    filtered_x: np.ndarray
    coefficient_projected: np.ndarray
    actuator_slab_projected: np.ndarray
    coefficient_update_frozen: np.ndarray
    numerical_failure: np.ndarray
    coefficients: np.ndarray
    adaptation_start_sample: int
    require_no_clipping: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class FairMetricSpecification:
    target_attenuation_db: float
    evaluation_start_sample: int
    evaluation_stop_sample: int | None
    sustain_duration_samples: int
    metric_step_samples: int
    tail_evaluation_start_sample: int | None = None

    def validate(self, sample_count: int, adaptation_start_sample: int) -> None:
        stop = sample_count if self.evaluation_stop_sample is None else self.evaluation_stop_sample
        if self.target_attenuation_db <= 0.0:
            raise ValueError("attenuation target must be positive")
        if self.evaluation_start_sample < adaptation_start_sample:
            raise ValueError("evaluation starts before adaptation")
        if not 0 <= self.evaluation_start_sample < stop <= sample_count:
            raise ValueError("invalid evaluation window")
        if self.sustain_duration_samples <= 0:
            raise ValueError("sustain duration must be positive")
        if self.metric_step_samples <= 0:
            raise ValueError("metric step must be positive")
        if stop - self.evaluation_start_sample < self.sustain_duration_samples:
            raise ValueError("evaluation window is shorter than sustain duration")
        tail_start = (
            self.evaluation_start_sample
            if self.tail_evaluation_start_sample is None
            else self.tail_evaluation_start_sample
        )
        if not self.evaluation_start_sample <= tail_start < stop:
            raise ValueError("tail evaluation starts outside the evaluation window")
        if stop - tail_start < self.sustain_duration_samples:
            raise ValueError("tail evaluation segment is shorter than sustain duration")


def _filter_sample(
    numerator: np.ndarray,
    denominator: np.ndarray,
    input_signal: np.ndarray,
    output_signal: np.ndarray,
    index: int,
) -> float:
    """Evaluate one causal B(z^-1)/A(z^-1) sample with explicit histories."""

    feedforward = 0.0
    for tap, coefficient in enumerate(numerator):
        source_index = index - tap
        if source_index < 0:
            break
        feedforward += float(coefficient * input_signal[source_index])
    feedback = 0.0
    for tap, coefficient in enumerate(denominator[1:], start=1):
        source_index = index - tap
        if source_index < 0:
            break
        feedback += float(coefficient * output_signal[source_index])
    return (feedforward - feedback) / float(denominator[0])


def _delayed_vector(
    signal: np.ndarray, index: int, delay_samples: int, length: int
) -> np.ndarray:
    vector = np.zeros(length, dtype=float)
    newest = index - delay_samples
    if newest >= 0:
        oldest = max(0, newest - length + 1)
        values = signal[oldest : newest + 1][::-1]
        vector[: values.size] = values
    return vector


def _path_arrays(model: DiscreteTransferModel) -> tuple[np.ndarray, np.ndarray]:
    model.validate()
    if model.input_delay_samples < 1 or model.numerator[0] != 0.0:
        raise ValueError(
            f"fair feedback mode requires an explicit delayed path: {model.model_id}"
        )
    return model.numerator, model.denominator


def run_fair_imc_fxlms(
    disturbance: np.ndarray,
    true_secondary_path: DiscreteTransferModel,
    internal_secondary_path: DiscreteTransferModel,
    parameters: FairBaselineParameters,
    plant_information_budget: dict[str, Any],
) -> FairBaselineRun:
    """Run corrected feedback IMC-FxLMS with independent ``S`` and ``Shat``.

    The true path is used only by the evaluation plant to form
    ``e[k] = d[k] + S(q)u[k]``. Reconstruction and filtered-x processing use
    only the independently configured internal model ``Shat``.
    """

    parameters.validate()
    true_b, true_a = _path_arrays(true_secondary_path)
    internal_b, internal_a = _path_arrays(internal_secondary_path)
    if true_secondary_path.sample_rate_hz != internal_secondary_path.sample_rate_hz:
        raise ValueError("true and internal secondary paths have different sample rates")

    d_sig = np.asarray(disturbance, dtype=float).reshape(-1)
    if not d_sig.size or not np.all(np.isfinite(d_sig)):
        raise ValueError("disturbance must be a nonempty finite vector")

    sample_count = d_sig.size
    residual = np.zeros(sample_count, dtype=float)
    applied_control = np.zeros(sample_count, dtype=float)
    control_demand = np.zeros(sample_count, dtype=float)
    clipped = np.zeros(sample_count, dtype=bool)
    true_output = np.zeros(sample_count, dtype=float)
    predicted_output = np.zeros(sample_count, dtype=float)
    reconstructed = np.zeros(sample_count, dtype=float)
    filtered_x = np.zeros(sample_count, dtype=float)
    projected = np.zeros(sample_count, dtype=bool)
    slab_projected = np.zeros(sample_count, dtype=bool)
    update_frozen = np.zeros(sample_count, dtype=bool)
    numerical_failure = np.zeros(sample_count, dtype=bool)

    if parameters.initial_coefficients is None:
        coefficients = np.zeros(parameters.controller_coefficients, dtype=float)
    else:
        coefficients = np.asarray(
            parameters.initial_coefficients, dtype=float
        ).reshape(-1).copy()

    initial_norm = float(np.linalg.norm(coefficients))
    if initial_norm > parameters.coefficient_projection_radius:
        coefficients *= parameters.coefficient_projection_radius / initial_norm
        projected[0] = True

    for index in range(sample_count):
        # S and Shat have separate output states and use the applied command.
        # Their explicit delays make applied_control[index] irrelevant here,
        # avoiding an algebraic loop with the command computed later below.
        true_output[index] = _filter_sample(
            true_b, true_a, applied_control, true_output, index
        )
        predicted_output[index] = _filter_sample(
            internal_b, internal_a, applied_control, predicted_output, index
        )

        residual[index] = d_sig[index] + true_output[index]
        reconstructed[index] = residual[index] - predicted_output[index]
        filtered_x[index] = _filter_sample(
            internal_b, internal_a, reconstructed, filtered_x, index
        )

        if index < parameters.adaptation_start_sample:
            continue

        filtered_vector = _delayed_vector(
            filtered_x,
            index,
            parameters.controller_regressor_delay_samples,
            parameters.controller_coefficients,
        )
        disturbance_vector = _delayed_vector(
            reconstructed,
            index,
            parameters.controller_regressor_delay_samples,
            parameters.controller_coefficients,
        )

        if parameters.actuation_ramp_samples:
            ramp = min(
                1.0,
                max(
                    0.0,
                    (index - parameters.adaptation_start_sample)
                    / parameters.actuation_ramp_samples,
                ),
            )
        else:
            ramp = 1.0

        freeze_update = (
            parameters.freeze_update_on_saturation
            and index > parameters.adaptation_start_sample
            and clipped[index - 1]
        )
        if freeze_update:
            update_frozen[index] = True
        else:
            normalization = float(filtered_vector @ filtered_vector)
            normalization += parameters.normalization_delta
            if parameters.leakage:
                coefficients *= 1.0 - parameters.step_size * parameters.leakage
            coefficients += (
                parameters.step_size
                * residual[index]
                * filtered_vector
                / normalization
            )

            coefficient_norm = float(np.linalg.norm(coefficients))
            if coefficient_norm > parameters.coefficient_projection_radius:
                coefficients *= (
                    parameters.coefficient_projection_radius / coefficient_norm
                )
                projected[index] = True

        effective_control_vector = ramp * disturbance_vector
        signed_demand = float(coefficients @ effective_control_vector)
        if parameters.actuator_slab_projection and effective_control_vector.any():
            slab_limit = parameters.actuator_limit * (
                1.0 - parameters.actuator_slab_relative_margin
            )
            if abs(signed_demand) > slab_limit:
                vector_norm_squared = float(
                    effective_control_vector @ effective_control_vector
                )
                if vector_norm_squared > 0.0:
                    slab_target = float(
                        np.clip(signed_demand, -slab_limit, slab_limit)
                    )
                    coefficients -= (
                        (signed_demand - slab_target)
                        / vector_norm_squared
                        * effective_control_vector
                    )
                    slab_projected[index] = True
                    signed_demand = float(
                        coefficients @ effective_control_vector
                    )

        request = -signed_demand
        if not np.isfinite(request):
            numerical_failure[index] = True
            request = 0.0

        control_demand[index] = request
        applied_control[index] = float(
            np.clip(request, -parameters.actuator_limit, parameters.actuator_limit)
        )
        clipped[index] = abs(request) > parameters.actuator_limit

    metadata = {
        "implementation_mode": "corrected_information_fair",
        "sample_indexing": "zero_based",
        "feedback_sign": "e=d+S*u; u=-Q*d_hat",
        "true_secondary_path_model_id": true_secondary_path.model_id,
        "internal_secondary_path_model_id": internal_secondary_path.model_id,
        "true_secondary_path_delay_samples": true_secondary_path.input_delay_samples,
        "internal_secondary_path_delay_samples": internal_secondary_path.input_delay_samples,
        "controller_regressor_delay_samples": parameters.controller_regressor_delay_samples,
        "adaptation_start_sample": parameters.adaptation_start_sample,
        "actuation_ramp_samples": parameters.actuation_ramp_samples,
        "coefficient_projection": {
            "type": "l2_ball",
            "radius": parameters.coefficient_projection_radius,
        },
        "leakage": parameters.leakage,
        "anti_windup_mode": (
            "freeze_update_on_previous_saturation"
            if parameters.freeze_update_on_saturation
            else "continue_update"
        ),
        "actuator_slab_projection": parameters.actuator_slab_projection,
        "actuator_slab_relative_margin": parameters.actuator_slab_relative_margin,
        "actuator_saturation": {
            "type": "symmetric_hard_clip",
            "limit": parameters.actuator_limit,
        },
        "require_no_clipping": parameters.require_no_clipping,
        "adaptation_during_saturation": (
            "freeze_update_after_saturation_using_applied_control_history"
            if parameters.freeze_update_on_saturation
            else "continue_using_applied_control_history"
        ),
        "plant_information_budget": plant_information_budget,
    }
    return FairBaselineRun(
        residual=residual,
        applied_control=applied_control,
        control_demand=control_demand,
        clipped=clipped,
        true_secondary_output=true_output,
        predicted_secondary_output=predicted_output,
        reconstructed_disturbance=reconstructed,
        filtered_x=filtered_x,
        coefficient_projected=projected,
        actuator_slab_projected=slab_projected,
        coefficient_update_frozen=update_frozen,
        numerical_failure=numerical_failure,
        coefficients=coefficients,
        adaptation_start_sample=parameters.adaptation_start_sample,
        require_no_clipping=parameters.require_no_clipping,
        metadata=metadata,
    )


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def _attenuation_db(disturbance: np.ndarray, residual: np.ndarray) -> float:
    return float(
        20.0
        * np.log10(max(_rms(disturbance), 1e-15) / max(_rms(residual), 1e-15))
    )


def compute_fair_metrics(
    disturbance: np.ndarray,
    run: FairBaselineRun,
    sample_rate_hz: float,
    specification: FairMetricSpecification,
    disturbance_peak_bound: float | None,
) -> dict[str, Any]:
    """Compute predeclared post-start metrics without fallback convergence."""

    d_sig = np.asarray(disturbance, dtype=float).reshape(-1)
    if d_sig.size != run.residual.size:
        raise ValueError("disturbance and fair-baseline run lengths differ")
    specification.validate(d_sig.size, run.adaptation_start_sample)
    evaluation_stop = (
        d_sig.size
        if specification.evaluation_stop_sample is None
        else specification.evaluation_stop_sample
    )
    evaluation_slice = slice(specification.evaluation_start_sample, evaluation_stop)
    tail_start = (
        specification.evaluation_start_sample
        if specification.tail_evaluation_start_sample is None
        else specification.tail_evaluation_start_sample
    )

    window_starts = np.arange(
        specification.evaluation_start_sample,
        evaluation_stop - specification.sustain_duration_samples + 1,
        specification.metric_step_samples,
        dtype=int,
    )
    sustained_attenuation = np.asarray(
        [
            _attenuation_db(
                d_sig[start : start + specification.sustain_duration_samples],
                run.residual[start : start + specification.sustain_duration_samples],
            )
            for start in window_starts
        ],
        dtype=float,
    )

    reached_indices = np.flatnonzero(
        sustained_attenuation >= specification.target_attenuation_db
    )
    if reached_indices.size:
        first_window_start = int(window_starts[int(reached_indices[0])])
        confirmation_sample = (
            first_window_start + specification.sustain_duration_samples - 1
        )
        elapsed_samples = (
            confirmation_sample + 1 - run.adaptation_start_sample
        )
        time_to_status = "reached"
        time_to_samples: int | None = elapsed_samples
        time_to_seconds: float | None = elapsed_samples / sample_rate_hz
        reached_sample: int | None = confirmation_sample
    else:
        time_to_status = "not_reached"
        time_to_samples = None
        time_to_seconds = None
        reached_sample = None

    settled_indices = np.asarray(
        [
            index
            for index in reached_indices
            if np.all(
                sustained_attenuation[index:]
                >= specification.target_attenuation_db
            )
        ],
        dtype=int,
    )
    if settled_indices.size:
        settled_window_start = int(window_starts[int(settled_indices[0])])
        settled_confirmation_sample = (
            settled_window_start + specification.sustain_duration_samples - 1
        )
        settled_elapsed_samples = (
            settled_confirmation_sample + 1 - run.adaptation_start_sample
        )
        settled_status = "reached"
        settled_samples: int | None = settled_elapsed_samples
        settled_seconds: float | None = settled_elapsed_samples / sample_rate_hz
        settled_sample: int | None = settled_confirmation_sample
    else:
        settled_status = "not_reached"
        settled_samples = None
        settled_seconds = None
        settled_sample = None

    loss_of_regulation_count = (
        0
        if not reached_indices.size
        else int(
            np.count_nonzero(
                sustained_attenuation[int(reached_indices[0]) + 1 :]
                < specification.target_attenuation_db
            )
        )
    )
    tail_windows = sustained_attenuation[window_starts >= tail_start]
    if not tail_windows.size:
        raise ValueError("no sustained window lies inside the tail evaluation segment")

    demand = run.control_demand[evaluation_slice]
    applied = run.applied_control[evaluation_slice]
    clipped = run.clipped[evaluation_slice]
    numerical_failures = int(np.count_nonzero(run.numerical_failure[evaluation_slice]))
    saturation_count = int(np.count_nonzero(clipped))
    demand_limit = float(run.metadata["actuator_saturation"]["limit"])
    demand_violation_count = int(np.count_nonzero(np.abs(demand) > demand_limit))
    evaluation_samples = int(demand.size)
    disturbance_peak = float(np.max(np.abs(d_sig[evaluation_slice])))
    bound_satisfied = (
        None
        if disturbance_peak_bound is None
        else disturbance_peak <= disturbance_peak_bound
    )

    infeasibility_reasons: list[str] = []
    if numerical_failures:
        infeasibility_reasons.append("nonfinite_numeric_state_or_control")
    if run.require_no_clipping and saturation_count:
        infeasibility_reasons.append("actuator_clipping_forbidden")
    if bound_satisfied is False:
        infeasibility_reasons.append("disturbance_peak_bound_exceeded")

    metrics: dict[str, Any] = {
        **run.metadata,
        "evaluation_window": {
            "start_sample": specification.evaluation_start_sample,
            "stop_sample_exclusive": evaluation_stop,
            "sample_count": evaluation_samples,
        },
        "evaluation_start_sample": specification.evaluation_start_sample,
        "evaluation_stop_sample_exclusive": evaluation_stop,
        "tail_evaluation_start_sample": tail_start,
        "plant_information_budget_id": run.metadata["plant_information_budget"][
            "id"
        ],
        "sustain_duration_samples": specification.sustain_duration_samples,
        "sustain_duration_seconds": (
            specification.sustain_duration_samples / sample_rate_hz
        ),
        "metric_step_samples": specification.metric_step_samples,
        "target_attenuation_db": specification.target_attenuation_db,
        "time_to_10db_status": time_to_status,
        "time_to_10db_samples": time_to_samples,
        "time_to_10db_seconds": time_to_seconds,
        "time_to_10db_reached_sample": reached_sample,
        "time_to_10db_semantics": (
            "first_sustained_window_hit_diagnostic_not_convergence"
        ),
        "settled_time_to_10db_status": settled_status,
        "settled_time_to_10db_samples": settled_samples,
        "settled_time_to_10db_seconds": settled_seconds,
        "settled_time_to_10db_reached_sample": settled_sample,
        "settled_time_to_10db_semantics": (
            "earliest_window_after_which_all_remaining_windows_meet_target"
        ),
        "loss_of_regulation_count": loss_of_regulation_count,
        "worst_sustained_attenuation_db": float(np.min(sustained_attenuation)),
        "tail_worst_sustained_attenuation_db": float(np.min(tail_windows)),
        "best_sustained_attenuation_db": float(np.max(sustained_attenuation)),
        "evaluation_attenuation_db": _attenuation_db(
            d_sig[evaluation_slice], run.residual[evaluation_slice]
        ),
        "control_demand_peak": float(np.max(np.abs(demand))),
        "control_demand_rms": _rms(demand),
        "applied_control_peak": float(np.max(np.abs(applied))),
        "applied_control_rms": _rms(applied),
        "saturation_count": saturation_count,
        "saturation_fraction": saturation_count / evaluation_samples,
        "control_demand_limit_violation_count": demand_violation_count,
        "coefficient_projection_count": int(
            np.count_nonzero(run.coefficient_projected[evaluation_slice])
        ),
        "coefficient_projection_count_total": int(
            np.count_nonzero(run.coefficient_projected)
        ),
        "actuator_slab_projection_count": int(
            np.count_nonzero(run.actuator_slab_projected[evaluation_slice])
        ),
        "actuator_slab_projection_count_total": int(
            np.count_nonzero(run.actuator_slab_projected)
        ),
        "coefficient_update_frozen_count": int(
            np.count_nonzero(run.coefficient_update_frozen[evaluation_slice])
        ),
        "coefficient_update_frozen_count_total": int(
            np.count_nonzero(run.coefficient_update_frozen)
        ),
        "final_coefficient_norm": float(np.linalg.norm(run.coefficients)),
        "numerical_failure_count": numerical_failures,
        "disturbance_peak": disturbance_peak,
        "disturbance_peak_bound": disturbance_peak_bound,
        "disturbance_peak_bound_satisfied": bound_satisfied,
        "feasible": not infeasibility_reasons,
        "infeasibility_reasons": infeasibility_reasons,
        "robust_stability_margin": None,
        "robust_stability_status": "not_certified_for_adaptive_baseline",
    }
    return metrics
