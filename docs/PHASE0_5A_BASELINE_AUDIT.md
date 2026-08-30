# Phase 0.5A corrected IMC-FxLMS baseline audit

Date: 2026-08-30

Status: the corrected, information-fair baseline structure and reporting are
implemented. Phase 0 remains blocked. This audit makes no superiority or
robust-stability claim, and Phase 1 and `K0` synthesis have not begun.

## Scope and evidence

The run uses `configs/experiment.yaml`, evaluation seed 142, the frozen T1/T2
records normalized to RMS 0.8, and the complete configured path models. The
nominal model is `cylinder1dm_2k_secondary_fir_20260713`; the exploratory
mismatch model is `cylinder1dm_2k_secondary_armax_20260713`. Their provenance,
coefficients, hashes, signs, units, and delays remain those audited in
`docs/PHASE0_AUDIT.md`.

The implementation qualification is
`phase0_5a_structure_only_not_robustly_optimized`. The inherited T1/T2 step
sizes were not retuned on the evaluation records.

## Historical source reproduction

`aor_anc.baseline.run_source_exact` remains a separate historical MATLAB
regression mode. Its source digest is
`160ffe992c9d23ea896fdda8c2038a4ee9e804ea2fe9931395d7140faf9552ed`, and all
MATLAB golden comparisons still pass. Its pre-start zero residual and original
fallback convergence metric are intentionally preserved for reproduction; its
outputs are not used as the corrected fair comparison.

## Corrected fair baseline

The new mode implements the zero-based physical loop

\[
e[k]=d[k]+S(q)u[k],\qquad
\hat d[k]=e[k]-\hat S(q)u[k],\qquad
u_{\rm demand}[k]=-\theta[k]^T\hat d_k.
\]

`S` and `Shat` are independently instantiated causal filters. Their configured
leading numerator zeros encode their delays exactly once. Both audited models
have a one-sample delay, so the current command cannot affect the current
residual and there is no algebraic loop. The plant uses `S` only to form the
physical error. Disturbance reconstruction and filtered-x processing use only
`Shat`; the controller observes the physical error and applied-control history,
not the true model or true-path state.

The residual is computed from sample zero. Before the declared adaptation start
(sample 1000), applied control is zero and `e[k]=d[k]`; the reproduced maximum
pre-start error is exactly zero in every case. The normalized update is

\[
\theta[k+1]=\Pi_{\lVert\theta\rVert_2\le10}
\left(\theta[k]+\mu\frac{e[k]x_f[k]}
{x_f[k]^Tx_f[k]+10^{-4}}\right).
\]

The implementation records projection events, the requested control before
clipping, the applied control after the symmetric limit of 4, and every
clipping event. With `require_no_clipping=true`, any clipping makes the run
infeasible.

The information budget
`complete_shat_error_mic_no_true_path_v0` gives the controller the complete
internal `Shat`, error microphone, and applied-control history. The true `S`
and evaluation disturbances are evaluation-engine-only and unavailable for
parameter selection. The controller budget is 64 real FIR coefficients.

## Predeclared metrics

Metrics use samples `[1000, 20000)`, a 400-sample (0.2 s) sustained RMS window,
and a 100-sample step. Time-to-10-dB is elapsed time from adaptation start to
the end of the first complete sustained window at or above 10 dB. It therefore
cannot precede adaptation or window confirmation. If no window reaches the
target, the status is `not_reached` and no fallback time is emitted.

Each result also reports the minimum (worst) and maximum sustained attenuation,
whole-window attenuation, peak/RMS demand before clipping, peak/RMS applied
control, clipping count/fraction, projection count, feasibility, both path IDs,
information-budget ID, adaptation start, evaluation window, and sustain
duration.

## Reproduced Phase 0.5A results

All numbers below are deterministic for seed 142 and the committed
configuration. `U0` means the independent true and internal filters have equal
coefficients; it does not mean that the implementation shares their state.

| Case | Eval. attn. (dB) | Worst sustained (dB) | Time to 10 dB | Demand peak / RMS | Applied peak / RMS | Clips (fraction) | Feasible |
|---|---:|---:|---:|---:|---:|---:|---|
| T1 U0 | 18.0239 | 1.9060 | 0.350 s | 4.2717 / 2.3119 | 4.0000 / 2.3112 | 56 (0.2947%) | no |
| T2 U0 | 18.4806 | 3.2407 | 0.350 s | 4.4498 / 2.4446 | 4.0000 / 2.4426 | 105 (0.5526%) | no |
| T1 mismatch | -12.4406 | -13.2111 | 0.400 s | 318.0290 / 124.0099 | 4.0000 / 3.8306 | 16678 (87.7789%) | no |
| T2 mismatch | -10.0740 | -11.9663 | `not_reached` | 371.7482 / 166.7114 | 4.0000 / 3.8924 | 17519 (92.2053%) | no |

The early 10-dB window in T1 mismatch is not a claim of convergence: later
behavior is poor, as shown by its negative whole-window and worst sustained
attenuation. Every run is infeasible because clipping is forbidden. T2 mismatch
also reaches the coefficient projection radius, with 2646 projection events.
No robust-stability margin was computed.

## Regression evidence

The tests cover physical pre-start residuals, independently instantiated
perfect and mismatched paths, `Shat`-only reconstruction/filtered-x processing,
the one-sample delay and negative controller sign, post-start time-to-10-dB,
`not_reached`, clipping infeasibility, coefficient projection, result metadata,
and the unchanged MATLAB golden reproduction.

Reproduce with:

```bash
uv run --extra test pytest
uv run aor-anc-phase0-5a --config configs/experiment.yaml
```

The generated evidence is written to `results/phase0_5a/` and intentionally
ignored by Git.

## Unresolved user-supplied physical inputs

Phase 0 remains blocked by inputs that this implementation does not invent:

1. a physically justified operating-condition path set and uncertainty
   coverage; the FIR--ARMAX mismatch is exploratory and the ARMAX residual
   whiteness test failed;
2. physical calibration linking normalized disturbance and actuator units to
   the target hardware;
3. declared sensitivity-peak (`Ms`) and out-of-band limits;
4. later-phase solver, `H`-selection, and hardware choices already retained as
   deferred `null` values.

The supplied external files are sufficient to reproduce this structural
Phase 0.5A evaluation, but not to construct or validate the physically robust,
optimized fair baseline required for a superiority comparison. The decision is
therefore: Phase 0.5A implementation complete; Phase 0 remains no-go.
