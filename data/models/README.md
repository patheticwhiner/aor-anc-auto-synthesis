# Model data

Place complete secondary-path models here or reference their external paths in
`configs/experiment.yaml`.

Phase 0 uses the latter option. The complete coefficient arrays and SHA-256
provenance for the 2026-07-13 2 kHz nominal FIR and exploratory ARMAX model are
frozen directly in `configs/experiment.yaml`; the source MAT files remain in
`/home/dcol/Projects/MATLAB/ANC-Classic-Control-Simulations/`.

Every model must document:

- sample rate;
- input/output sign and units;
- delay convention;
- FIR/IIR/state-space representation;
- identification or construction method;
- operating condition;
- whether it is nominal, admissible uncertainty, or held-out evaluation data.

Do not commit confidential or very large raw recordings without an explicit
data-management decision.
