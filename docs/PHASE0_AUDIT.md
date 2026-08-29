# Phase 0 mathematical consistency audit

Date: 2026-08-29

Status: audit executed; Phase 0 stopped with declared blockers. This document
makes no research-performance or robust-stability claim.

## 1. Evidence and scope

The audit uses the normative equations in `docs/RESEARCH_SPEC.md` and the
following external evidence at repository commit
`53ed931bb48d1856cc2b17e87e73341753ad57e0`:

- complete nominal secondary path
  `cylinder1dm_2k_secondary_fir_20260713`, a measured 16-tap LMS FIR model at
  2 kHz;
- exploratory alternative model
  `cylinder1dm_2k_secondary_armax_20260713`, an ARMAX(4,8,2,1) fit from the
  same dated capture family;
- `controller_imc_fxlms.m` and the frozen `cylinder1dm_2k_stage_suite.mat`
  evaluation records.

Their absolute paths, SHA-256 values, coefficient arrays, units, and delay
conventions are frozen in `configs/experiment.yaml`. No neural generator or
deterministic synthesis phase was implemented.

## 2. Independent transfer-map derivation

The declared signal convention is

\[
e=d+Gu,\qquad u=-Ke.
\]

Substitution gives

\[
e=d-GKe,
\qquad (1+GK)e=d.
\]

Hence, wherever the feedback interconnection is well posed,

\[
S_G:=\frac{e}{d}=\frac{1}{1+GK},
\qquad
U_G:=\frac{u}{d}=-\frac{K}{1+GK}.
\]

For the zero-centred parameterization

\[
K(Q)=\frac{Q}{1-\hat GQ}
\]

and additive plant

\[
G=\hat G+W_\Delta\Delta,
\]

the feedback denominator is

\[
\begin{aligned}
1+GK
&=1+(\hat G+W_\Delta\Delta)
       \frac{Q}{1-\hat GQ}\\
&=\frac{1-\hat GQ+\hat GQ+W_\Delta\Delta Q}
        {1-\hat GQ}\\
&=\frac{1+W_\Delta\Delta Q}{1-\hat GQ}.
\end{aligned}
\]

Therefore

\[
S_G=\frac{1-\hat GQ}{1+W_\Delta\Delta Q},
\qquad
U_G=-\frac{Q}{1+W_\Delta\Delta Q}.
\]

Setting `Delta = 0` gives the nominal identities

\[
S_{\hat G}=1-\hat GQ,
\qquad
U_{\hat G}=-Q.
\]

An independent frequency-response implementation evaluates the direct maps
through `K` and the reduced maps through `Q`. Across 4097 points from DC to
Nyquist, the maximum relative errors were:

| Map | Maximum relative error |
|---|---:|
| nominal `e/d` | 2.402e-16 |
| nominal `u/d` | 5.699e-16 |
| uncertain `e/d` | 6.609e-16 |
| uncertain `u/d` | 6.816e-16 |

All are below the Phase 0 threshold `1e-8`. The static sign regression case
`G=0.4`, `K=0.5`, `d=1` independently gives `e=1/1.2` and
`u=-0.5/1.2`.

## 3. Robust-stability and safe-bound consistency

If `Q`, `W_delta`, and `Delta` are stable and proper and

\[
\lVert W_\Delta Q\rVert_\infty\le 1-\varepsilon,
\quad \varepsilon>0,
\]

then

\[
\lVert W_\Delta\Delta Q\rVert_\infty\le1-\varepsilon<1.
\]

The small-gain theorem makes `1 + W_delta Delta Q` stably invertible and

\[
\left\lVert(1+W_\Delta\Delta Q)^{-1}\right\rVert_\infty
\le\frac{1}{\varepsilon}.
\]

Consequently, the two sufficient safe-set constraints in the specification
correctly imply

\[
\lVert W_sS_G\rVert_\infty\le\bar\gamma_s,
\qquad
\lVert W_uU_G\rVert_\infty\le\bar\gamma_u.
\]

This is only an algebraic audit. No `Q`, safe set, or robust-stability margin
was synthesized in Phase 0.

## 4. Notch-map consistency

At a target frequency, the condition

\[
1-\hat G(e^{j\omega})Q(e^{j\omega})=0
\]

sets the numerator of `S_G` to zero. Under the strict small-gain condition,
the denominator cannot be zero, so the same sensitivity zero holds for every
declared additive perturbation. Splitting the complex equality into real and
imaginary parts gives exactly the two rows of `A_omega q = [1,0]^T` in the
specification.

There is an important realization obligation: exact interpolation generally
puts a unit-circle zero in `1 - Ghat Q`, hence a unit-circle pole in the
standalone quotient `K=Q/(1-Ghat Q)`. Phase 2 must use an internally
stabilizing Youla/IMC realization and test all internal maps; it may not rely on
an unstable hidden cancellation. This is not resolved or implemented here.

## 5. Discrete-time convention, units, and delay

- Sample rate: 2000 Hz; Nyquist frequency: 1000 Hz.
- The target 300--420 Hz band is
  `omega = 2*pi*f/fs = 0.9424778--1.3194689 rad/sample`.
  Every implementation interprets the `omega` in `exp(j*omega)` as
  radians/sample, not hertz or radians/second.
- Transfer arrays are in ascending powers of `z^-1`.
- The nominal path is
  `Ghat(z) = z^-1 * sum(h[k] z^-k, k=0..15)`.
  The leading numerator zero is the one-sample computation/input delay; it is
  not added a second time.
- `e=d+Gu` and `u=-Ke` use the specification sign. The reproduced baseline
  implements the same convention through `e=d+g` and a negative FIR control
  request.
- Input, output, disturbance, and actuator bounds are normalized simulation
  units. No volts, pascals, microphone sensitivity, or loudspeaker calibration
  is available.

The nominal FIR is stable. Expressing the complete delayed FIR as a rational
function of `z` gives 16 poles at the origin, 15 finite zeros, and four
nonminimum-phase zeros. The generated diagnostic includes poles, zeros, the
impulse response, and the complete 0--Nyquist magnitude and phase response.

## 6. Disturbance bound and exploratory uncertainty weight

The finite Phase 0 T1/T2 evaluation records are assigned the explicit bound

\[
\max_k |d[k]|\le1.25
\]

in normalized error-sensor units. Their observed peaks are 1.16350 and
1.21979. This resolves the configuration `null` for these records only; it is
not a physical acoustic-amplitude guarantee and does not cover the T3 random
record, whose observed peak exceeds 3.

The exploratory additive uncertainty is a constant stable weight

\[
W_\Delta(z)=2.19.
\]

It is obtained by outward rounding the full-band infinity norm of the
ARMAX-minus-FIR model-form difference. MATLAB `norm(sys,inf,1e-10)` returned
2.187728708338571 at 877.69508 Hz. An independent 262145-point grid found
2.187728707891886, or 0.998963 of the declared weight. The grid is a numerical
check, not a continuous-band proof.

The ARMAX residual whiteness test failed, and the two models do not establish
variation across physical operating conditions. Thus this disk is explicitly
exploratory and cannot yet support a physical robust-stability claim.

## 7. Existing IMC-FxLMS reproduction

The Python `source_exact` mode reproduces the external MATLAB loop, including
its indexing and startup behavior. Against MATLAB golden output, every frozen
metric agrees to relative error below 1.2e-15. The frozen evaluation artifact
uses random seed 142 and normalizes each disturbance record to RMS 0.8.

| Case | Step | Attenuation | Unclipped peak `u` | Clips | Coefficient norm |
|---|---:|---:|---:|---:|---:|
| T1, 357 Hz | 0.01 | -3.2276 dB | 45.4871 | 8676 | 7.1058 |
| T2, 420--300 Hz | 0.02 | 24.9839 dB | 4.7903 | 186 | 0.8063 |

Both cases violate the declared no-clipping actuator constraint. The worst
attenuation is -3.2276 dB and the worst unclipped control demand is 45.4871.

The source loop leaves the residual array equal to zero for samples 1--1009
while the disturbance is nonzero. It also does not propagate the IMC and
filtered-x states during that interval. Consequently, the reported 0.1005 s
convergence time is nonphysical and is marked invalid by the Phase 0 runner.
The source also uses one coefficient set for both `S` and `Shat`; it is a U0
perfect-model regression only.

This reproduction is not the robustly optimized, information-matched baseline
required by Phase 4. No comparative superiority claim is permitted.

## 8. Phase 0 decision

Phase 0 is **blocked at its stop condition**, despite passing the transfer-map
and source-reproduction numerical checks, because:

1. the uncertainty disk lacks physical coverage evidence;
2. the existing baseline has a nonphysical startup/convergence metric and no
   independent true/internal secondary-path models;
3. the normalized disturbance and actuator units lack hardware calibration;
4. the sensitivity and out-of-band limits remain undeclared.

Phase 1 must not begin until the Phase 0 stop condition is explicitly resolved
or the research plan is revised with user approval.

## 9. Reproduction

```bash
uv run --extra test pytest
uv run aor-anc-phase0 --config configs/experiment.yaml
```

Generated evidence:

- `results/phase0/phase0_summary.json`
- `results/phase0/baseline_reproduction.csv`
- `results/phase0/nominal_model_diagnostics.png`

The result commit field is `355dd06ebf6dcde0169e0650f3ef923c67994f7e`
plus the uncommitted Phase 0 working-tree changes. Solver status is
`not_applicable_no_optimization_in_phase0`; no robust-stability margin was
certified. The baseline artifact seed is 142; the configured numerical-audit
seed is 0 (the current transfer-map audit itself is deterministic).
