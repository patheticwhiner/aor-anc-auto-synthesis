# Research specification

Status: working specification requiring independent derivation and numerical
validation. Statements labelled **proof obligation** are not established
results.

## 1. Scope and intended contribution

The project studies automatic synthesis of:

1. a complete fixed feedback controller \(K_0\);
2. a two-real-dimensional harmonic Youla direction for each target frequency;
3. a rate-limited projected AOR law;
4. deterministic certificates for robust stability, actuator constraints, and
   target-frequency regulation.

The fixed controller is not designed to approximate a plant inverse over a
frequency neighbourhood. Harmonic adaptation only needs to reach a controller
that places a sensitivity zero at each target frequency.

The primary scientific question is whether automatic safe-centre synthesis
provides a strict, reproducible advantage over a robustly optimized IMC-FxLMS
baseline. Automatic generation alone is insufficient as a contribution.

## 2. Signal and feedback convention

The SISO output-disturbance model is

\[
e = d + G u, \qquad u=-K e,
\]

where:

- \(d\) is the primary disturbance at the error sensor;
- \(u\) is the secondary-source command;
- \(G\) is the true secondary path;
- \(e\) is the residual error;
- \(K\) is the feedback controller.

Therefore

\[
S_G := \frac{e}{d}=\frac{1}{1+GK},
\qquad
U_G := \frac{u}{d}=-\frac{K}{1+GK}.
\]

All implementations and tests must use this convention. A different convention
requires an explicit specification revision.

## 3. Plant and uncertainty model

The nominal secondary path \(\hat G\in\mathcal{RH}_\infty\) is complete and
known. The initial theoretical uncertainty model is weighted additive
uncertainty:

\[
G=\hat G+W_\Delta\Delta,
\qquad
\Delta\in\mathcal{RH}_\infty,
\qquad
\|\Delta\|_\infty\le1.
\]

The uncertainty weight \(W_\Delta\) must be supplied or fitted from declared
physical/modeling uncertainty. It may not be enlarged or reduced merely to
obtain a preferred result.

A finite multimodel or structured non-convex uncertainty family may be added
later, but its certificate and comparison must be stated separately.

## 4. Zero-centred Youla/IMC parameterization

Because \(\hat G\) is stable, \(K=0\) is a non-handcrafted stabilizing anchor.
For stable proper \(Q\), define

\[
K(Q)=\frac{Q}{1-\hat GQ}.
\]

For the nominal plant,

\[
S_{\hat G}=1-\hat GQ,
\qquad
U_{\hat G}=-Q.
\]

For the true plant,

\[
S_G=\frac{1-\hat GQ}{1+W_\Delta\Delta Q},
\qquad
U_G=-\frac{Q}{1+W_\Delta\Delta Q}.
\]

A sufficient robust-stability condition is

\[
\boxed{\|W_\Delta Q\|_\infty\le1-\varepsilon},
\qquad \varepsilon>0.
\]

These identities must be re-derived and numerically checked in Phase 0.

## 5. Finite-dimensional fixed-controller coordinate

Use a stable, plant-independent basis:

\[
Q(q,z)=\sum_{i=1}^{n_q}q_i\psi_i(z),
\qquad q\in\mathbb R^{n_q}.
\]

The first implementation uses an FIR delay basis. Candidate orders are
enumerated; pole locations must not be manually tuned to individual plants or
frequencies. The offline fixed-controller coordinate may exceed two dimensions,
but the online harmonic adaptation must remain two-real-dimensional per tone.

Define a conservative convex safe set

\[
\mathcal Q_{\mathrm{safe}}=
\left\{q:
\begin{array}{l}
\|W_\Delta Q(q)\|_\infty\le1-\varepsilon,\\
\|W_s(1-\hat GQ(q))\|_\infty\le
\varepsilon\,\bar\gamma_s,\\
\|W_u Q(q)\|_\infty\le
\varepsilon\,\bar\gamma_u
\end{array}
\right\}.
\]

The last two inequalities are sufficient bounds obtained using
\(\|(1+W_\Delta\Delta Q)^{-1}\|_\infty\le1/\varepsilon\). Alternative less
conservative certificates may replace them only after proof and tests.

## 6. Target-frequency notch plane

At a frozen target frequency \(\omega\), exact ideal regulation is obtained if

\[
1-\hat G(e^{j\omega})Q(q,e^{j\omega})=0.
\]

Under the robust-stability condition, the true sensitivity has the same zero
because uncertainty appears only in its nonzero denominator.

Write the complex interpolation condition as two real affine equations:

\[
A_\omega q=b,
\qquad
b=\begin{bmatrix}1\\0\end{bmatrix},
\]

where column \(i\) of \(A_\omega\in\mathbb R^{2\times n_q}\) is

\[
\begin{bmatrix}
\operatorname{Re}\{\hat G(e^{j\omega})\psi_i(e^{j\omega})\}\\
\operatorname{Im}\{\hat G(e^{j\omega})\psi_i(e^{j\omega})\}
\end{bmatrix}.
\]

The two-dimensional construction is feasible only if
\(\operatorname{rank}A_\omega=2\).

## 7. Analytic two-real-dimensional direction

Let \(H\succ0\) weight coefficient motion according to out-of-band sensitivity,
control energy, and regularization. Define

\[
B_\omega=
H^{-1}A_\omega^\top
\left(A_\omega H^{-1}A_\omega^\top\right)^{-1}.
\]

Then

\[
A_\omega B_\omega=I_2.
\]

For a chosen centre \(q_0\), parameterize online motion as

\[
q(\theta,\omega)=q_0+B_\omega\theta,
\qquad \theta\in\mathbb R^2,
\]

with the ideal notch endpoint

\[
\theta_\omega^\star=b-A_\omega q_0.
\]

**Proof obligation:** establish that \(B_\omega\) is the unique weighted
minimum-norm right inverse under the stated rank condition and determine how
the choice of \(H\) affects robustness and convergence.

## 8. Automatic generation of the fixed centre

The fixed centre \(q_0\), hence \(K_0\), is generated by a deterministic
lexicographic program.

### Stage A: maximize certified safety reserve

Maximize \(\varepsilon\) subject to

\[
q_0\in\mathcal Q_{\mathrm{safe}}
\]

and, for every design frequency \(\omega\),

\[
q_\omega^\star
:=q_0+B_\omega(b-A_\omega q_0)
\in\mathcal Q_{\mathrm{safe}}.
\]

### Stage B: minimize adaptation and fixed-performance cost

Holding an accepted safety reserve, minimize

\[
\max_{\omega\in\Omega}
\|b-A_\omega q_0\|_2
+\lambda_s J_s(q_0)
+\lambda_u J_u(q_0)
+\lambda_q\|q_0\|_2^2.
\]

The final fixed controller is

\[
\boxed{K_0(z)=\frac{Q(q_0^\star,z)}
{1-\hat G(z)Q(q_0^\star,z)}}.
\]

The safe adaptive coordinate at each frequency is

\[
\Theta_{\mathrm{safe}}(\omega)=
\{\theta:q_0^\star+B_\omega\theta
\in\mathcal Q_{\mathrm{safe}}\}.
\]

Because \(\mathcal Q_{\mathrm{safe}}\) is convex, the segment between the safe
centre and a safe notch endpoint is safe. A projected law must keep every actual
iterate in \(\Theta_{\mathrm{safe}}(\omega)\), not merely on that segment.

## 9. AOR law and performance theorem

The exact projected, rate-limited AOR law has not yet been fixed. It must use no
more than two real adaptive states per tone and must respect
\(\Theta_{\mathrm{safe}}(\omega)\).

The required theorem chain is:

1. robust internal stability for every declared plant and every allowed
   adaptive iterate;
2. boundedness under rate-limited projection;
3. convergence or practical convergence of the two-dimensional AOR law;
4. reachability of at least 10 dB attenuation;
5. satisfaction of the actuator constraint for a declared disturbance-amplitude
   bound.

**Important:** a 10 dB guarantee under \(u_{\max}\) is impossible to certify
without a bound on disturbance amplitude. This bound is currently unresolved
in `configs/experiment.yaml`.

Frequency gridding establishes only sampled-frequency feasibility. A
continuous-band theorem requires generalized KYP, interval arithmetic, or a
proved inter-grid Lipschitz bound.

## 10. Fair IMC-FxLMS comparison

The decisive baseline is not a casually selected nominal IMC-FxLMS. It must be
allowed to optimize its secondary-path model/preconditioner and step size using
the same uncertainty description and computational budget.

Define a common finite-time metric, for example the worst-case contraction or
time-to-10-dB, and compare under identical:

- plant information;
- uncertainty set;
- target-frequency set;
- actuator limit;
- controller/order budget;
- online computational budget;
- initialization and stopping rule.

The project passes its scientific Go/No-Go gate only if the synthesized method
has a strict, reproducible advantage after these controls.

For an uncertainty disk containing the origin, a feedback Möbius transform
cannot remove the origin. Therefore the project must not generally claim that
an infeasible common descent direction becomes feasible. The default claim to
test is reduction of the worst-case contraction factor. A stronger
infeasible-to-feasible separation requires a separately declared structured or
non-convex plant family.

## 11. Role of learning

Learning is optional and disabled until the deterministic method passes. If
needed, a network may map

\[
(\hat G,W_\Delta,\Omega,u_{\max},M_s)
\mapsto\widetilde q_0
\]

as a warm start. A deterministic projection/repair and complete certificate
must produce the final controller. Network test accuracy never constitutes a
stability guarantee.

