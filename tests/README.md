# Test directory

Phase 0 tests currently cover:

- the feedback sign and every direct/Youla closed-loop transfer identity;
- nominal reduction at `Delta = 0`;
- explicit one-sample delay preservation;
- source-exact IMC-FxLMS reproduction against MATLAB golden metrics;
- rejection of the source baseline's nonphysical convergence metric.

Run them with:

```bash
uv run --extra test pytest
```

Later phases must add:

- robust-stability known-safe and known-unsafe examples;
- dimensions and rank of `A_omega`;
- `A_omega @ B_omega = I_2`;
- notch interpolation residual;
- independent verification of safe endpoints;
- projection invariance;
- equal-information robust-baseline configuration.
