# Progress and evidence log

## Current status

- Repository initialized from the research discussion.
- No numerical model has been added.
- No deterministic synthesizer has been implemented.
- No theorem has been independently verified.
- No superiority claim has passed its Go/No-Go gate.

## Blocking inputs

1. Complete nominal secondary-path model file.
2. Declared uncertainty model or uncertainty-weight construction rule.
3. Disturbance-amplitude bound required for the `u_max = 4` guarantee.
4. Exact existing IMC-FxLMS implementation/configuration to reproduce.
5. Preferred prototype environment if Python is not acceptable.

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

