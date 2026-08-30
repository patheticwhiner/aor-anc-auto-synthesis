# Automatic Robust Base-Controller Synthesis for Narrowband Feedback ANC

This repository is a specification-first handoff for developing and validating
an automatic synthesis method for a robust fixed controller \(K_0\), a
minimum-dimensional harmonic Youla direction, and a projected adaptive output
regulator (AOR).

The research question is deliberately narrow:

> Given a complete nominal secondary-path model, a declared uncertainty set,
> a target-frequency band, and hard performance constraints, can an automatic
> synthesis procedure generate a robustly safe center controller whose
> two-real-parameter harmonic adaptation directions reach the required notch
> controllers, and can this construction strictly improve a fair robust
> IMC-FxLMS baseline under the same information and constraints?

No neural network is required for the core method. Learning is considered only
after a deterministic synthesizer, certificate, and fair-baseline comparison
have passed their Go/No-Go gates.

## Start here

Local Codex must read these files in order:

1. [AGENTS.md](AGENTS.md)
2. [docs/RESEARCH_SPEC.md](docs/RESEARCH_SPEC.md)
3. [docs/DECISIONS.md](docs/DECISIONS.md)
4. [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
5. [docs/PROGRESS.md](docs/PROGRESS.md)
6. [configs/experiment.yaml](configs/experiment.yaml)

The repository initially contains no claimed implementation result. Its first
purpose is to prevent theory, sign conventions, baselines, and acceptance
criteria from drifting during coding.

## Initial Codex prompt

```text
Read AGENTS.md and every document it requires.

First perform the Phase 0 consistency audit from
docs/IMPLEMENTATION_PLAN.md. Restate the signal convention, derive every
closed-loop map independently, identify undefined quantities and invalid
claims, and record the result in docs/PROGRESS.md.

Do not implement the neural generator. Do not change RESEARCH_SPEC.md without
asking. Stop if the deterministic formulation or fair baseline is ambiguous.
```

## Repository status

- Specification: Phase 0 algebraically and numerically audited; see
  [docs/PHASE0_AUDIT.md](docs/PHASE0_AUDIT.md).
- Phase 0: still stopped by uncertainty and physical-calibration blockers.
- Phase 0.5A baseline: corrected physical startup and independent true/internal
  secondary paths implemented; see
  [docs/PHASE0_5A_BASELINE_AUDIT.md](docs/PHASE0_5A_BASELINE_AUDIT.md).
- Deterministic synthesizer: not implemented.
- AOR convergence proof: proof obligations listed, not yet discharged.
- IMC-FxLMS separation: unverified Go/No-Go question.
- Neural amortization: disabled.

Reproduce the Phase 0 evidence with:

```bash
uv run --extra test pytest
uv run aor-anc-phase0 --config configs/experiment.yaml
uv run aor-anc-phase0-5a --config configs/experiment.yaml
```
