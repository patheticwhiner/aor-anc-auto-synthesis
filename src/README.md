# Source directory

The `aor_anc` package currently implements Phase 0 only:

- discrete-time model loading and diagnostics;
- the independently derived direct and Youla closed-loop maps;
- a source-exact reproduction of the declared external IMC-FxLMS baseline;
- the one-command Phase 0 evidence runner.

Run it from the repository root with:

```bash
uv run --extra test aor-anc-phase0 --config configs/experiment.yaml
```

Later phases may add:

- model and uncertainty loading;
- closed-loop map evaluation;
- stable Youla basis construction;
- robust safe-set constraints;
- notch-plane and weighted-right-inverse construction;
- deterministic centre synthesis;
- projected two-dimensional AOR;
- robustly optimized IMC-FxLMS baselines;
- certificate and reporting utilities.
