"""
Darcy-Weisbach pipe head-loss with Colebrook-White friction factor.

Sign convention (critical for Newton-Raphson in looped networks):
  h = f(L/D) * Q|Q| / (2gA²)   [metres]

Using Q|Q| instead of Q² preserves the correct sign for reverse flows.
Head loss is positive when flow is positive (in the direction start→end).

Physical constants (water at 20 °C):
  ν  = 1.004 × 10⁻⁶ m²/s   kinematic viscosity
  ρ  = 998.2 kg/m³           density
  g  = 9.81 m/s²             gravitational acceleration
"""
from __future__ import annotations

import math
from typing import Tuple

from ..graph.models import Pipe

# Physical constants
NU: float = 1.004e-6   # m²/s  kinematic viscosity of water at 20 °C
RHO: float = 998.2     # kg/m³
G: float = 9.81        # m/s²

# Solver guards
Q_MIN: float = 1e-10   # m³/s — below this use laminar linearisation


def compute_friction_factor(Re: float, relative_roughness: float) -> Tuple[float, float]:
    """
    Compute Darcy friction factor f and its derivative df/dRe.

    Regimes:
      Re < 2000             → Hagen-Poiseuille:  f = 64/Re
      2000 ≤ Re < 4000      → Linear interpolation between laminar and turbulent
      Re ≥ 4000             → Colebrook-White (implicit, solved with Halley's method)

    Parameters
    ----------
    Re : float
        Reynolds number (dimensionless, must be > 0).
    relative_roughness : float
        ε/D (dimensionless).

    Returns
    -------
    f : float
        Darcy friction factor.
    df_dRe : float
        Derivative df/dRe (for chain-rule Jacobian construction).
    """
    if Re <= 0.0:
        # Zero or negative Re → laminar limit
        return 64.0 / max(Re, 1e-12), -64.0 / max(Re, 1e-12) ** 2

    if Re < 2000.0:
        # Laminar: Hagen-Poiseuille
        f = 64.0 / Re
        df_dRe = -64.0 / Re ** 2
        return f, df_dRe

    if Re >= 4000.0:
        # Turbulent: Colebrook-White via Halley's method
        f, df_dRe = _colebrook_white(Re, relative_roughness)
        return f, df_dRe

    # Transitional 2000–4000: linear interpolation
    f_lam = 64.0 / 2000.0
    f_turb, _ = _colebrook_white(4000.0, relative_roughness)
    alpha = (Re - 2000.0) / 2000.0          # 0 at Re=2000, 1 at Re=4000
    f = f_lam + alpha * (f_turb - f_lam)
    df_dRe = (f_turb - f_lam) / 2000.0
    return f, df_dRe


def _colebrook_white(Re: float, eps_D: float) -> Tuple[float, float]:
    """
    Solve Colebrook-White equation using Halley's method.

    Implicit equation in x = 1/√f:
        x = -2 log₁₀(ε/(3.71D)  +  2.51/(Re·x))

    Equivalently, define residual:
        g(x) = x + 2 log₁₀(eps_D/3.71 + 2.51/(Re·x)) = 0

    Halley's method converges in 3–5 iterations for all hydraulic Re.

    Returns (f, df/dRe).
    """
    # Swamee-Jain as robust initial guess
    term1 = eps_D / 3.7
    if Re > 0 and eps_D > 0:
        x0 = -2.0 * math.log10(term1 + 5.74 / Re ** 0.9)
        x0 = max(x0, 1.0)  # x = 1/√f must be positive
    else:
        x0 = 8.0  # fallback

    x = x0
    ln10 = math.log(10.0)
    A = eps_D / 3.71

    for _ in range(50):
        arg = A + 2.51 / (Re * x)
        if arg <= 0:
            x = max(x * 0.5, 1.0)
            continue
        log_arg = math.log10(arg)
        g = x + 2.0 * log_arg                  # residual
        dg_dx = 1.0 - 2.0 * 2.51 / (Re * x ** 2 * arg * ln10)
        d2g_dx2 = (
            2.0
            * (2.51 / (Re * ln10))
            * (2 * 2.51 / (Re * x ** 3 * arg) - 1.0 / (x ** 2 * arg) ** 1)
            / arg
            * (-2.51 / (Re * x))
        )
        # Simplified Halley: x_new = x - g / (dg_dx - g * d2g_dx2 / (2 * dg_dx))
        denom = dg_dx - g * d2g_dx2 / (2.0 * dg_dx)
        if abs(denom) < 1e-30:
            break
        dx = -g / denom
        x = x + dx
        x = max(x, 0.1)   # guard against negative x
        if abs(dx) < 1e-10:
            break

    f = 1.0 / x ** 2

    # Derivative df/dRe via implicit differentiation of Colebrook-White
    # dg/dRe = 2 * 2.51 / (Re² * x * arg * ln10)
    # df/dRe = -2/x³ · (dx/dRe)   where dx/dRe = -(dg/dRe)/(dg/dx)
    arg = A + 2.51 / (Re * x)
    if arg > 0 and abs(dg_dx) > 1e-30:
        dg_dRe = 2.0 * 2.51 / (Re ** 2 * x * arg * ln10)
        dx_dRe = -dg_dRe / dg_dx
        df_dRe = -2.0 / x ** 3 * dx_dRe
    else:
        df_dRe = 0.0

    return f, df_dRe


def compute_pipe_headloss(Q: float, pipe: Pipe) -> Tuple[float, float]:
    """
    Compute head loss (m) and its derivative w.r.t. flow Q (m³/s) for a pipe.

    Uses Darcy-Weisbach with Colebrook-White friction factor.
    Includes minor losses (fittings, bends).

    h  = [f·L/D + K] · Q|Q| / (2gA²)
    dh/dQ = [f·L/D + K] · 2|Q| / (2gA²)  +  Q|Q|/(2gA²) · df/dQ

    Parameters
    ----------
    Q : float
        Volumetric flow rate (m³/s). Signed: positive = start→end direction.
    pipe : Pipe
        Pipe object with geometry and roughness.

    Returns
    -------
    h : float
        Head loss in metres (positive = energy lost in flow direction).
    dh_dQ : float
        Derivative dh/dQ for Jacobian assembly.
    """
    A = pipe.area
    D = pipe.diameter
    L = pipe.length
    eps_D = pipe.relative_roughness
    K = pipe.minor_loss_coeff

    abs_Q = abs(Q)

    # Guard against near-zero flow — use laminar linearisation
    if abs_Q < Q_MIN:
        # Laminar limit: h = (128 ν L)/(π g D⁴) · Q  (linear Hagen-Poiseuille)
        f_lam = 128.0 * NU * L / (math.pi * G * D ** 4)
        h = f_lam * Q
        dh_dQ = f_lam
        # Add linearised minor losses (small but consistent)
        km = K / (2.0 * G * A ** 2)
        return h + km * Q, dh_dQ + km

    # Reynolds number
    velocity = Q / A
    Re = abs(velocity) * D / NU

    # Friction factor
    f, df_dRe = compute_friction_factor(Re, eps_D)

    # Head loss coefficient
    coeff = f * L / D + K                     # dimensionless

    # Darcy-Weisbach: h = coeff · Q|Q| / (2gA²)
    two_g_A2 = 2.0 * G * A ** 2
    h = coeff * Q * abs_Q / two_g_A2

    # Derivative: d/dQ [coeff · Q|Q|] = coeff · 2|Q| + Q|Q| · dcoeff/dQ
    # dcoeff/dQ = (L/D) · df/dQ
    # df/dQ = df/dRe · dRe/dQ = df/dRe · D/(ν·A)
    dRe_dQ = D / (NU * A)        # dRe/d|Q| (sign handled separately)
    df_dQ = df_dRe * dRe_dQ      # always positive (both terms)

    dh_dQ = (coeff * 2.0 * abs_Q + Q * abs_Q * (L / D) * df_dQ) / two_g_A2

    # Regularisation: ensure dh/dQ is strictly positive to keep Jacobian non-singular
    dh_dQ = max(dh_dQ, 1e-12)

    return h, dh_dQ
