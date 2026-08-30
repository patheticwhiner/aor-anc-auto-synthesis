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

Phase 0.5A evidence is generated separately with:

```bash
uv run aor-anc-phase0-5a --config configs/experiment.yaml
```

The ignored `results/phase0_5a/` directory contains the corrected fair-baseline
JSON evidence log and CSV table. The runner first verifies that the historical
`source_exact` implementation and MATLAB golden reproduction are unchanged.
Phase 0.5A validates baseline structure and reporting only; it is not a robust
optimization or a superiority result.

Phase 0.5B evidence is generated with:

```bash
uv run aor-anc-phase0-5b --config configs/experiment.yaml
```

The ignored `results/phase0_5b/` directory contains the complete candidate
search table, frozen design/held-out/T1/T2 result table, and JSON evidence log.
The interpolated family is an exploratory model-form benchmark, not a physical
uncertainty set or robust-stability certificate.
