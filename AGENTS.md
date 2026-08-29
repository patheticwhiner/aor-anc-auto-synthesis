# Mandatory instructions for coding agents

## Required reading

Before editing source code or running experiments, read in this order:

1. `docs/RESEARCH_SPEC.md`
2. `docs/DECISIONS.md`
3. `docs/IMPLEMENTATION_PLAN.md`
4. `docs/PROGRESS.md`
5. `configs/experiment.yaml`

Treat `docs/RESEARCH_SPEC.md` as the normative research specification.

## Non-negotiable rules

- Preserve the feedback sign convention in the specification.
- Derive and unit-test every closed-loop transfer map before optimizing it.
- Use the complete secondary-path model supplied by the experiment; sparse or
  few-shot path data are not a core assumption.
- Do not introduce a manually tuned central controller.
- Do not use a high-dimensional online adaptive Youla parameter.
- Do not implement a neural generator before the deterministic synthesis and
  fair-baseline Go/No-Go gates pass.
- Do not treat frequency gridding as a continuous-band proof.
- Do not claim robust stability from frozen-controller tests alone.
- Do not claim superiority over IMC-FxLMS unless its robustly optimized baseline
  uses the same plant information, actuator limit, controller budget, and
  evaluation set.
- Report infeasibility and contradictions. Never silently relax a constraint or
  alter a theorem statement.

## Change control

- Do not modify `docs/RESEARCH_SPEC.md` or `docs/DECISIONS.md` without explicit
  user approval.
- Record implementation progress, numerical evidence, failures, and open issues
  in `docs/PROGRESS.md`.
- Implement only the requested phase from `docs/IMPLEMENTATION_PLAN.md`.
- Add regression tests for every resolved sign, dimension, and stability bug.
- Preserve unrelated user changes and keep commits phase-scoped.

## Result discipline

Every reported result must include:

- commit hash;
- configuration file;
- model and uncertainty-set identifier;
- random seed, if applicable;
- solver status and tolerances;
- robust-stability margin;
- worst-case attenuation, control magnitude, and convergence metric;
- baseline configuration using the same information and constraints.

