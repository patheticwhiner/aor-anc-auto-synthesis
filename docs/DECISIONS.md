# Research decisions and rejected directions

This file prevents previously rejected assumptions from re-entering the
project. Changes require explicit user approval.

## Retained decisions

- Use the complete available secondary-path model.
- Treat automatic fixed-controller generation as a synthesis problem, not as
  coefficient regression.
- Use a non-handcrafted zero stabilizing anchor for stable acoustic paths.
- Keep online adaptation at two real parameters per tone.
- Generate `K0` as a robust safe centre with certified notch reachability.
- Require a deterministic certificate independently of any learned generator.
- Compare against a robustly optimized, information-matched IMC-FxLMS baseline.
- Use theorem/counterexample/simulation gates before real-time implementation.

## Rejected as core contributions

- Unknown-frequency AOR by itself.
- Sparse/few-shot path measurement when a complete model is available.
- Blind high-order or overparameterized online adaptive `Q`.
- A manually designed robust `R/S` or central controller for every plant/band.
- “Use a neural network to output a controller” without a deterministic
  feasibility and stability certificate.
- A controller bank or selector without common-safe-region and coverage proofs.
- Treating nonminimum phase as equivalent to impossibility of target-frequency
  regulation.
- Using “large uncertainty” without an explicit quantitative set.
- Claiming universal superiority over IMC-FxLMS.
- Claiming an infeasible-to-feasible sector transformation for a connected
  uncertainty disk containing the origin.
- Evaluating nominal attenuation while ignoring the actuator limit.

## Claims that remain unproven

- A useful nontrivial safe notch-covering centre exists for the supplied plant
  and uncertainty set.
- The generated centre strictly improves the strongest fair IMC-FxLMS baseline.
- A rate-limited projected two-dimensional AOR retains the required convergence
  rate under the full discrete-time dynamics.
- At least 10 dB attenuation is feasible with `u_max = 4` for the declared
  disturbance-amplitude bound.
- A low enough fixed order covers the entire 300–420 Hz band.
- Neural amortization is useful after deterministic optimization cost is known.

