# Phase 0.5B constrained robust IMC-FxLMS baseline audit

Date: 2026-08-30

Status: finite constrained baseline optimization completed. Phase 0 remains
blocked. No Phase 1, `K0`, Youla synthesis, neural generation, robust-stability
claim, or superiority claim is included.

## Metric correction

The original corrected `time_to_10db` is retained only as a first-hit
diagnostic: it ends at the first complete sustained window at or above 10 dB.
It is explicitly labelled `first_sustained_window_hit_diagnostic_not_convergence`.

Three predeclared regulation metrics are added:

- `settled_time_to_10db`: the end of the earliest sustained window from which
  every remaining sustained window stays at or above 10 dB;
- `tail_worst_sustained_attenuation_db`: the minimum sustained attenuation
  among windows wholly inside the final declared evaluation segment;
- `loss_of_regulation_count`: the number of below-target windows after the
  first target hit.

An unreached first-hit or settled target has status `not_reached` and no
fallback time. A transient first hit is never reported as convergence.

## Exploratory benchmark family

The finite benchmark is

\[
S_\alpha=(1-\alpha)S_{\rm FIR}+\alpha S_{\rm ARMAX}.
\]

Interior models are formed as an exact parallel rational sum over a common
denominator. Since both endpoints are stable, their common denominator has the
union of stable endpoint poles. Every enumerated true and internal model is
independently checked for finite coefficients, strict pole stability,
causality, and the declared one-sample delay. The selected
`Shat_beta_0.5` has 21 numerator coefficients, 5 denominator coefficients,
one sample of delay, and maximum denominator-pole radius 0.8063523.

The family is labelled exactly
`exploratory_model_form_benchmark_not_physical_uncertainty`. It interpolates
two model forms from the same capture family and does not represent measured
operating-condition variation.

The exact split is:

| Split | Alpha values | Frequencies | Use |
|---|---|---|---|
| Design | 0, 0.5, 1 | 300, 420 Hz | candidate selection only |
| Held-out | 0.25, 0.75 | 330, 360, 390 Hz | one-shot frozen evaluation only |
| T1/T2 | nominal FIR path | frozen records, seed 142 | one-shot frozen evaluation only |

Design and held-out tones contain 4000 samples at 2 kHz, RMS 0.8, and phase 0.
Design/held-out metrics use `[500,4000)`, 200-sample sustained windows,
100-sample steps, and tail `[3000,4000)`. T1/T2 use `[1000,20000)`,
400-sample windows, 100-sample steps, and tail `[16000,20000)`.

The tuning function accepts only `split=design`. Held-out cases are constructed
and T1/T2 records are loaded only after the selected parameters are frozen.
Regression tests verify that changing held-out data cannot alter selection.

## Information and candidate budget

Every candidate receives information budget
`complete_design_family_shat_no_true_evaluation_path_v0`: complete FIR/ARMAX
endpoints, the interpolation formula, design alpha/frequency grids, and its own
complete internal model. It does not receive held-out alphas/frequencies,
T1/T2 records, the true evaluation path, or true-path state. Online signals are
the error microphone, applied-control history, and selected internal-model
state. The controller budget is 64 real FIR coefficients.

All candidates use normalized FxLMS and an L2 coefficient ball. The coarse grid
is the Cartesian product:

- beta: `[0, 0.5, 1]`;
- step size: `[0.002, 0.01, 0.05]`;
- leakage: `[0, 0.1]`;
- coefficient radius: `[0.5, 2]`;
- constraint modes: ball/continue, ball/freeze-on-saturation, and
  ball/instantaneous-slab/freeze-on-saturation.

This gives 108 coarse candidates. Fine search retains the selected constraint
mode and uses beta offsets `[-0.25,0,0.25]`, step multipliers `[0.5,1,2]`,
leakage `[0,0.1]`, and radius multipliers `[0.5,1,2]`. Its declared maximum is
54; 52 unique new candidates were evaluated after removing two duplicates.
The total was 160 unique candidates, below the declared budget of 162.

Selection is lexicographic: reject numerical failures and any request above 4;
maximize design tail-worst attenuation; maximize settled design cases;
minimize worst settled time; minimize worst control RMS; minimize worst final
coefficient norm; then use candidate ID only as a deterministic exact-tie
break. Held-out and T1/T2 results do not enter this ordering.

## Selected finite-search baseline

The selected parameters are:

| Parameter | Value |
|---|---:|
| Internal-model beta | 0.5 |
| Normalized step size | 0.1 |
| Leakage | 0 |
| L2 coefficient radius | 1 |
| Anti-windup | freeze update after previous saturation |
| Instantaneous actuator slab | enabled |
| Hard actuator limit | 4 |

The slab is the Euclidean projection of the current coefficient vector onto
`|theta^T x| <= 4` for the instantaneous ramped control regressor. A relative
interior margin of `1e-12` handles floating-point roundoff; it tightens rather
than relaxes the hard limit. Symmetric hard clipping remains active as an
independent check. The selected candidate requested at most
3.999999999996002 on the design set and had zero clipping events.

## Frozen results

Aggregate results are:

| Split | Cases settled | Tail-worst attenuation | Full-window worst sustained | Worst settled time | Worst demand peak | Worst applied RMS | Ball / slab events | Clips |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Design | 6/6 | 15.6901 dB | 2.1879 dB | 0.200 s | 4.0000 | 2.8213 | 1859 / 1781 | 0 |
| Held-out benchmark | 6/6 | 25.7166 dB | 2.5646 dB | 0.200 s | 4.0000 | 2.8203 | 1773 / 1462 | 0 |
| T1/T2 records | 2/2 | 34.7528 dB | 24.1811 dB | 0.450 s | 3.6330 | 2.4460 | 1809 / 0 | 0 |

Every split has zero loss-of-regulation windows for this finite run. The low
full-window worst values on synthetic tones occur during startup and show why
the tail metric is reported separately. Near-248 dB tail values in several
individual pure-tone cases are numerical-floor cancellation results, not
physical attenuation claims.

Frozen record details are:

| Record | Evaluation attenuation | Tail worst | Settled time | Demand peak / RMS | Ball / slab events | Feasible |
|---|---:|---:|---:|---:|---:|---|
| T1 | 38.7731 dB | 38.1909 dB | 0.450 s | 3.3465 / 2.3174 | 287 / 0 | yes |
| T2 | 33.3397 dB | 34.7528 dB | 0.450 s | 3.6330 / 2.4460 | 1522 / 0 | yes |

These T1/T2 values were obtained after parameter freezing and were not used to
select beta, step size, leakage, radius, or constraint mode.

## Operation count and qualification

For the selected 64-coefficient controller and 21/5 internal model, the
steady-state controller-only count is 372 multiplications, 307
additions/subtractions, 3 divisions, and 1 square root per sample. A sample
with active coefficient-ball and actuator-slab projections requires at most
628 multiplications, 498 additions/subtractions, 5 divisions, and 1 square
root. Counts exclude memory/indexing, comparisons, and the evaluation engine's
true-path filter; they are algorithmic scalar-real counts, not measured target
cycles.

The selected candidate is feasible on every declared design, held-out, and
T1/T2 case. This is finite benchmark evidence only. Frozen adaptive tests do
not provide a robust-stability margin, continuous-family certificate, physical
uncertainty coverage, or superiority over a future synthesized controller.

## Reproduction and remaining blockers

Configuration: `configs/experiment.yaml`. Starting commit:
`5b6d028be2fa533059a4d0434dd1e2ae12f0fecf` plus the Phase 0.5B working-tree
changes. Solver status is
`deterministic_finite_coarse_to_fine_search_completed`; no numerical
optimization solver is used. Reproduce with:

```bash
uv run --extra test pytest
uv run aor-anc-phase0-5b --config configs/experiment.yaml
```

Generated evidence is ignored under `results/phase0_5b/`. Remaining blockers
are unchanged: a physically justified operating-condition path set and
uncertainty coverage, normalized I/O calibration, declared `Ms` and out-of-band
limits, and later-phase solver/`H`/hardware choices. Phase 0 therefore remains
no-go. Phase 1 and `K0` synthesis must not begin.
