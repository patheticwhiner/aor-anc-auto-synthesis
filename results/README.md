# Results

Generated results belong here and should normally remain untracked except for
small, explicitly selected evidence tables or figures.

Every result must be reproducible from a committed configuration and must record
the commit hash, model identifier, solver status, tolerances, and fair-baseline
configuration.

Phase 0 evidence is generated with:

```bash
uv run aor-anc-phase0 --config configs/experiment.yaml
```

The ignored `results/phase0/` directory then contains the JSON evidence log,
baseline CSV, and nominal-model diagnostic plot. The Phase 0 baseline is a
source reproduction, not the fair robust Go/No-Go baseline required by Phase 4.
