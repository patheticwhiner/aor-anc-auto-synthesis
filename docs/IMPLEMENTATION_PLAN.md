# Implementation plan and acceptance gates

Only one phase may be implemented at a time. Each phase must update
`docs/PROGRESS.md` and add tests before the next phase begins.

## Phase 0 — Consistency audit and baseline reproduction

Tasks:

1. Re-derive all transfer maps in `RESEARCH_SPEC.md` from the signal equations.
2. Confirm discrete-time conventions, units, delays, and controller signs.
3. Load the complete nominal model and plot poles, zeros, impulse response, and
   0–Nyquist FRF.
4. Reproduce the existing IMC-FxLMS baseline under a recorded configuration.
5. Specify the disturbance-amplitude bound and the uncertainty weight.

Acceptance criteria:

- analytic and numerical closed-loop maps agree to relative error below
  `1e-8` away from poles/zeros;
- the baseline result is reproducible from one command and configuration;
- all unresolved quantities marked `null` in the configuration are either
  filled or explicitly retained as blockers;
- no research claim is made.

Stop condition: sign, model, baseline, or uncertainty ambiguity remains.

## Phase 0.5A — Corrected information-fair IMC-FxLMS baseline

Tasks:

1. Preserve source-exact MATLAB reproduction as a historical regression mode.
2. Implement physical startup and independent true/internal secondary paths.
3. Report pre-clipping demand, applied control, projection, clipping, and
   feasibility under a predeclared information budget.
4. Replace fallback convergence timing with explicit reached/not-reached
   metrics.

Status: completed at commit `5b6d028`; Phase 0 remained blocked.

## Phase 0.5B — Constrained robust fair-baseline optimization

Tasks:

1. Retain first-hit time-to-10-dB only as a diagnostic; add settled time,
   tail-worst sustained attenuation, and loss-of-regulation count.
2. Construct a stable, delayed FIR--ARMAX interpolation family with strictly
   disjoint design and held-out alpha/frequency grids. Label it exploratory
   model-form evidence, not physical uncertainty.
3. Search normalized, leaky, coefficient-ball, freeze-on-saturation, and
   instantaneous actuator-slab variants with robustly centred internal models.
4. Perform deterministic lexicographic coarse-to-fine selection using design
   cases only, rejecting every numerical failure and requested control above 4.
5. Freeze the selected parameters before one-shot held-out and T1/T2
   evaluation. Report arithmetic operation counts and all constraint events.

Acceptance criteria:

- selected demand is at most 4 on every design case without weakening the
  declared limit;
- changing held-out inputs cannot affect parameter selection;
- a temporary target crossing is never described as convergence;
- the strongest feasible finite-search candidate is retained even if it does
  not attain 10 dB;
- no physical-uncertainty, robust-stability, or superiority claim is made.

Stop condition: no no-clipping perfect-model candidate, invalid path
interpolation, inseparable data splits, evaluation-dependent selection, or any
silent actuator-limit relaxation.

## Phase 1 — Deterministic safe-set prototype

Tasks:

1. Implement stable FIR Youla basis evaluation.
2. Implement nominal and uncertain closed-loop maps.
3. Construct frequency-gridded sufficient constraints for
   `Q_safe`.
4. Solve Stage A safety-reserve maximization for each candidate order.
5. Independently verify every returned solution on a denser grid and sampled
   admissible uncertainties.

Acceptance criteria:

- `q=0` is recovered as a known safe sanity case when constraints permit;
- unsafe injected examples are rejected;
- solver status, primal/dual residuals, and independent margins are recorded;
- no grid result is described as a continuous-band proof.

Stop condition: no nontrivial safe set exists under declared constraints.

## Phase 2 — Notch geometry and automatic `K0`

Tasks:

1. Construct `A_omega` and verify rank over 300–420 Hz.
2. Construct the weighted right inverse `B_omega`.
3. Verify `A_omega @ B_omega = I_2` numerically.
4. Solve the lexicographic centre problem for `q0`.
5. Recover and realize `K0` without unstable hidden cancellations.
6. Verify each notch endpoint and the projected safe-coordinate set.

Acceptance criteria:

- right-inverse error below `1e-8` on the design grid;
- every certified endpoint lies in the independently checked safe set;
- target-frequency sensitivity at each frozen endpoint meets the specified
  numerical tolerance;
- recovered `K0` and the intended IMC/Youla realization produce identical
  closed-loop maps;
- controller order and runtime cost are reported.

Stop condition: notch endpoints are infeasible or require unacceptable order or
control effort.

## Phase 3 — Projected two-dimensional AOR

Tasks:

1. Specify the exact known-frequency AOR update first.
2. Prove invariance under projection and rate limiting.
3. Implement a block-complex-envelope reference version.
4. Compare sample-level and averaged dynamics.
5. Add frequency adaptation only after the frozen-frequency theorem and tests
   pass.

Acceptance criteria:

- exactly two real adaptive states per tone;
- all iterates remain inside the certified safe set;
- measured convergence agrees with the derived bound in its stated regime;
- saturation and infeasible target cases terminate safely;
- no frozen-controller stability claim is substituted for time-varying
  stability.

Stop condition: projection destroys convergence or time-scale assumptions fail.

## Phase 4 — Decisive IMC-FxLMS Go/No-Go experiment

Baselines:

1. conventional fixed-model IMC-FxLMS;
2. robustly centred/preconditioned IMC-FxLMS;
3. normalized, leaky, and projected variants as applicable;
4. online secondary-path-model baseline if it receives an explicitly accounted
   probing/data budget;
5. deterministic oracle for the proposed controller class.

Metrics:

- worst-case attenuation;
- time-to-10-dB;
- worst-case contraction estimate;
- peak/RMS control demand;
- robust-stability margin;
- out-of-band amplification;
- order and online operations per sample.

Go criterion:

- strict advantage over the strongest fair IMC-FxLMS baseline on at least one
  predeclared primary metric;
- no regression in hard stability and actuator constraints;
- advantage persists on held-out admissible models and is not caused by unequal
  tuning information.

No-Go criterion:

- advantage disappears when the IMC-FxLMS baseline is robustly optimized;
- the generated `K0` is only a coordinate change available to the baseline;
- the target is physically infeasible under the actuator bound;
- the robust synthesis is too conservative to reach the notch set.

## Phase 5 — Continuous-band certificate and real-time validation

Tasks:

1. Replace or supplement gridding with generalized KYP, interval, or proven
   inter-grid bounds.
2. Validate quantization, finite precision, delay, and sample-rate effects.
3. Port the certified low-order controller and two-dimensional AOR to the target
   real-time environment.
4. Test declared model uncertainty without changing comparison rules.

Acceptance criteria:

- certificate covers the declared continuous band or is explicitly limited to
  a finite set;
- real-time implementation meets its deadline with measured headroom;
- experimental results reproduce the predeclared constrained metric.

## Phase 6 — Optional amortized generator

This phase is forbidden unless Phases 0–4 pass.

Tasks:

1. Generate a dataset of deterministic synthesis tasks and certified solutions.
2. Train a set/frequency-conditioned warm-start network.
3. Project, repair, verify, or reject every candidate.
4. Compare total generation time with deterministic optimization from scratch.

Acceptance criteria:

- at least an order-of-magnitude useful synthesis-time improvement;
- no accepted controller lacks a deterministic certificate;
- near-oracle performance on held-out plant/constraint tasks;
- explicit safe fallback on rejection.
