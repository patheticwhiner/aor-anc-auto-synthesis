# Progress and evidence log

## Current status

- Phase 0 mathematical and numerical audit executed; Phase 0 is blocked at its
  declared stop condition.
- The complete 2 kHz measured FIR secondary-path coefficients, provenance,
  units, and delay convention are frozen in `configs/experiment.yaml`.
- All direct and Youla closed-loop maps agree below the `1e-8` threshold.
- The external IMC-FxLMS source baseline is reproduced, but it violates the
  actuator constraint and has a nonphysical startup/convergence metric.
- No deterministic synthesizer has been implemented.
- The small-gain and safe-bound algebra has been audited, but no theorem or
  robust-stability margin has been numerically certified for a synthesized
  controller.
- No superiority claim has passed its Go/No-Go gate.

## Blocking inputs

1. Physical operating-condition evidence for an uncertainty set. The current
   constant additive weight only covers an exploratory FIR--ARMAX model-form
   discrepancy, and the ARMAX residual whiteness test failed.
2. A corrected IMC-FxLMS implementation with physically valid startup and
   separate true/internal secondary paths. The source-exact mode is retained
   only for U0 reproduction.
3. Physical calibration for the normalized disturbance and actuator units.
4. Declared sensitivity-peak and out-of-band limits.
5. Phase 1 solver choice, Phase 2 `H` rule, and eventual hardware target remain
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
