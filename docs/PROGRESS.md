# Progress and evidence log

## Current status

- Phase 0 mathematical and numerical audit executed; Phase 0 is blocked at its
  declared stop condition.
- The complete 2 kHz measured FIR secondary-path coefficients, provenance,
  units, and delay convention are frozen in `configs/experiment.yaml`.
- All direct and Youla closed-loop maps agree below the `1e-8` threshold.
- The external IMC-FxLMS source baseline remains an unchanged historical
  reproduction, including its nonphysical startup/convergence behavior.
- Phase 0.5A adds a separate corrected fair baseline with physical startup,
  independent true/internal paths, predeclared convergence metrics, and
  explicit demand, clipping, projection, feasibility, and information-budget
  reporting. All four frozen runs clip and are infeasible under the declared
  no-clipping rule.
- No deterministic synthesizer has been implemented.
- The small-gain and safe-bound algebra has been audited, but no theorem or
  robust-stability margin has been numerically certified for a synthesized
  controller.
- No superiority claim has passed its Go/No-Go gate.

## Blocking inputs

1. Physical operating-condition evidence for an uncertainty set. The current
   constant additive weight only covers an exploratory FIR--ARMAX model-form
   discrepancy, and the ARMAX residual whiteness test failed.
2. Physical calibration for the normalized disturbance and actuator units.
3. Declared sensitivity-peak and out-of-band limits.
4. Phase 1 solver choice, Phase 2 `H` rule, and eventual hardware target remain
   explicitly deferred `null` values.

## Required entry template

```md
### YYYY-MM-DD — Phase and task

- Commit:
- Configuration:
- Model/uncertainty ID:
- Command:
- Solver and tolerances:
- Result:
- Independent checks:
- Baseline comparison:
- Failed assumptions or contradictions:
- Decision: continue / revise / no-go
```

## Change log

### 2026-08-29 — Specification handoff

- Created the specification-first repository.
- Recorded the zero-centred Youla formulation, notch geometry, deterministic
  `K0` synthesis concept, implementation gates, and rejected directions.
- Decision: begin with Phase 0 only after the blocking inputs are supplied.

### 2026-08-29 — Phase 0 consistency audit and baseline reproduction

- Commit: `355dd06ebf6dcde0169e0650f3ef923c67994f7e` plus uncommitted
  Phase 0 working-tree changes.
- Configuration: `configs/experiment.yaml`.
- Model/uncertainty ID:
  `cylinder1dm_2k_secondary_fir_20260713` /
  `cylinder1dm_model_form_constant_additive_v0`.
- Command: `uv run aor-anc-phase0 --config configs/experiment.yaml`.
- Solver and tolerances: no optimization solver; transfer-map relative
  tolerance `1e-8`; MATLAB infinity-norm relative tolerance `1e-10`;
  baseline golden relative tolerance `1e-10`.
- Result: four direct/Youla maps agree with maximum relative error
  `6.82e-16`. The source-exact baseline matches MATLAB golden metrics below
  `1.2e-15` relative error.
- Independent checks: nominal FIR is stable with one explicit sample delay;
  complete pole/zero, impulse, and 0--Nyquist FRF diagnostics generated. The
  additive weight 2.19 contains the observed FIR--ARMAX difference; dense
  frequency checking is explicitly not treated as a continuous proof.
- Robust-stability margin: not certified in Phase 0.
- Worst-case constrained metrics: attenuation `-3.2276 dB`; unclipped control
  peak `45.4871`; convergence metric invalid because the source baseline
  zeroes the pre-start residual.
- Baseline comparison: source-exact 64-coefficient pure-feedback IMC-FxLMS,
  perfect secondary model, evaluation seed 142, disturbance RMS 0.8, T1
  `mu=0.01`, T2 `mu=0.02`, actuator limit 4. T1 clips 8676 samples and T2
  clips 186 samples, so neither is a feasible constrained baseline result.
- Failed assumptions or contradictions: source baseline startup is
  nonphysical; it cannot evaluate secondary-model mismatch; exploratory
  uncertainty lacks physical coverage; normalized I/O lacks hardware
  calibration.
- Decision: **no-go / remain in Phase 0** until the stop-condition blockers are
  resolved. No research claim is made.

### 2026-08-30 — Phase 0.5A corrected fair IMC-FxLMS baseline

- Commit: based on `886c90935be2f0c6696644e0da5ddda079f69134`; final Phase
  0.5A commit recorded after this entry.
- Configuration: `configs/experiment.yaml`;
  `corrected_information_fair_imc_fxlms_v0`.
- Model/uncertainty ID:
  `cylinder1dm_2k_secondary_fir_20260713` and exploratory
  `cylinder1dm_2k_secondary_armax_20260713` /
  `cylinder1dm_model_form_constant_additive_v0`.
- Command: `uv run --extra test pytest`; `uv run aor-anc-phase0-5a
  --config configs/experiment.yaml`.
- Solver and tolerances: no optimization solver; normalized FxLMS denominator
  delta `1e-4`; coefficient L2 radius 10; source golden relative tolerance
  `1e-10`.
- Result: all 20 tests pass. Source-exact digest
  `160ffe992c9d23ea896fdda8c2038a4ee9e804ea2fe9931395d7140faf9552ed`
  and MATLAB golden results are unchanged. Every corrected run has zero
  pre-start residual error and zero reconstruction-identity error.
- Corrected U0 T1/T2 metrics: evaluation attenuation 18.0239/18.4806 dB;
  worst sustained attenuation 1.9060/3.2407 dB; time-to-10-dB 0.350/0.350 s;
  pre-clip demand peaks 4.2717/4.4498; clips 56/105. Both are infeasible.
- Mismatch evidence: T1/T2 evaluation attenuation -12.4406/-10.0740 dB;
  worst sustained -13.2111/-11.9663 dB; T1 first reaches a sustained 10-dB
  window at 0.400 s but later degrades, while T2 reports `not_reached` with no
  fallback time. Demand peaks are 318.0290/371.7482 and clipping fractions are
  87.7789%/92.2053%; both are infeasible.
- Robust-stability margin: not certified. Plant-information budget:
  `complete_shat_error_mic_no_true_path_v0`, with true path available only to
  the evaluation engine.
- Independent checks: regression tests cover startup, path independence and
  mismatch, `Shat` reconstruction/filtering, sign/delay, convergence semantics,
  clipping infeasibility, projection, metadata, and historical golden output.
- Baseline comparison: no superiority comparison is made. Phase 0.5A validates
  corrected structure and reporting; parameters are inherited rather than
  robustly optimized.
- Failed assumptions or contradictions: all configured fair runs violate the
  no-clipping constraint; the mismatch model is not a physically validated
  uncertainty set; calibration, `Ms`, and out-of-band limits remain absent.
- Decision: Phase 0.5A implementation complete; **no-go / remain in Phase 0**.
  Do not begin Phase 1 or `K0` synthesis.
