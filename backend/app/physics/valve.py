"""
ISA valve model using Cv-based formulation with equal-percentage characteristic.

Flow equation:
  Q = Cv_SI · f(x) · sign(ΔP) · √(|ΔP| / ρ)   [m³/s]

Rearranged to head-loss form (consistent with pipe formulation):
  h = sign(Q) · (Q / (Cv_SI · f(x)))² · ρ / (ρ·g)
    = Q·|Q| / (Cv_SI · f(x))² / g   [m]

Equal-percentage inherent characteristic (ISA standard):
  f(x) = R^(x-1)    x ∈ (0, 1],  R = rangeability (typically 30–50)
  f(0) = 0  (fully closed)

Cv unit conversion (US → SI):
  1 US gpm/√psi  →  6.309e-5 / √6894.76  m³/s/√Pa  ≈  7.598e-7 m³/s/√Pa
"""
from __future__ import annotations

import math
from typing import Tuple

from ..graph.models import Valve, ValveType

# Physical constants
G: float = 9.81
RHO: float = 998.2

# Conversion: US Cv [gpm/√psi]  →  SI Cv [m³/s / √Pa]
_GPM_TO_M3S = 6.309e-5          # 1 US gpm = 6.309e-5 m³/s
_PSI_TO_PA = 6894.76            # 1 psi = 6894.76 Pa
CV_CONVERSION = _GPM_TO_M3S / math.sqrt(_PSI_TO_PA)   # ≈ 7.598e-7

# Guard values
Q_MIN: float = 1e-10            # m³/s — near-zero flow guard
CV_MIN: float = 1e-12           # m³/s/√Pa — guard against division by zero


def cv_to_si(cv_us: float) -> float:
    """Convert Cv from US customary (gpm/√psi) to SI (m³/s/√Pa)."""
    return cv_us * CV_CONVERSION


def equal_percentage_characteristic(opening: float, rangeability: float = 50.0) -> float:
    """
    ISA equal-percentage inherent flow characteristic.

      f(x) = R^(x-1)   for x ∈ (0, 1]
      f(0) = 0          (fully closed — no flow)

    Parameters
    ----------
    opening : float
        Valve opening fraction in [0, 1].
    rangeability : float
        R — ratio of maximum to minimum controllable flow (default 50).

    Returns
    -------
    float
        Normalised flow coefficient in [0, 1].
    """
    if opening <= 0.0:
        return 0.0
    if opening >= 1.0:
        return 1.0
    return rangeability ** (opening - 1.0)


def d_characteristic_d_opening(opening: float, rangeability: float = 50.0) -> float:
    """
    Derivative of equal-percentage characteristic w.r.t. opening fraction.
    df/dx = ln(R) · R^(x-1)
    """
    if opening <= 0.0 or opening >= 1.0:
        return 0.0
    return math.log(rangeability) * rangeability ** (opening - 1.0)


def compute_valve_headloss(Q: float, valve: Valve) -> Tuple[float, float]:
    """
    Compute head loss h (m) and derivative dh/dQ for a valve.

    Head-loss equation (all valves):
      h = Q·|Q| / (Cv_SI_eff² · g)

    where Cv_SI_eff = cv_to_si(cv_max) · f(opening).

    Special cases:
      - Fully closed (opening = 0 or ISOLATION with opening = 0):
          Very large resistance — effectively blocks flow.
      - PRV in active mode: handled at solver level; here returns basic Cv loss.
      - FCV: returns basic Cv loss; flow setpoint constraint handled in solver.

    Parameters
    ----------
    Q : float
        Flow (m³/s), signed.
    valve : Valve
        Valve object.

    Returns
    -------
    h : float
        Head loss in metres (positive = loss in flow direction).
    dh_dQ : float
        Derivative for Jacobian.
    """
    opening = valve.opening_fraction

    # Fully closed valve — massive resistance
    if opening <= 0.0:
        # h = 1e12 · Q  (linear, avoids singularity, drives Q → 0)
        return 1e12 * Q, 1e12

    # Cv-based head loss
    Cv_si = cv_to_si(valve.cv_max)
    f_char = equal_percentage_characteristic(opening, valve.rangeability)
    Cv_eff = Cv_si * f_char

    if Cv_eff < CV_MIN:
        # Effectively closed
        return 1e12 * Q, 1e12

    # h = Q|Q| / (Cv_eff² · g)
    Cv2g = Cv_eff ** 2 * G
    abs_Q = abs(Q)

    if abs_Q < Q_MIN:
        # Linearise around zero to avoid 0/0 in dh/dQ
        # h ≈ 2|Q_ref| / Cv2g · Q  (zero-flow linearisation — very small)
        # Use a tiny reference flow for the linearisation slope
        Q_ref = Q_MIN
        dh_dQ = 2.0 * Q_ref / Cv2g
        h = dh_dQ * Q
        return h, dh_dQ

    h = Q * abs_Q / Cv2g
    dh_dQ = 2.0 * abs_Q / Cv2g

    # Regularise dh/dQ
    dh_dQ = max(dh_dQ, 1e-12)
    return h, dh_dQ
