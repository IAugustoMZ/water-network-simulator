"""
Pump physics: PCHIP curve interpolation, affinity laws, cavitation detection.

Pump head equation (solver perspective):
  h_pump(Q) = -H(Q, speed_ratio)   [negative = head GAIN in solver residual]

The solver minimises continuity residuals where head loss along an edge is:
  ΔH = H_end - H_start = +H_pump(Q)   →   residual = H_pump - ΔH

For an OFF pump we model a check valve with very high resistance so that
Q → 0 without removing the edge from the incidence structure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..graph.models import Pump, PumpCurveData

# Physical constants
G: float = 9.81        # m/s²
RHO: float = 998.2     # kg/m³
# Vapour pressure head for water at 20 °C
VAPOR_PRESSURE_HEAD: float = 0.24   # m  (P_v / ρg ≈ 2340 Pa / (998.2 × 9.81))

# High resistance for OFF pump (models check valve preventing reverse flow)
OFF_PUMP_RESISTANCE: float = 1e8   # m / (m³/s)


@dataclass
class CavitationResult:
    """Result of NPSHa vs NPSHr comparison."""
    is_cavitating: bool
    npsha: float          # m  — available NPSH
    npshr: float          # m  — required NPSH at operating flow
    margin: float         # m  — NPSHa - NPSHr  (negative → cavitating)


class PumpInterpolator:
    """
    Monotone cubic (PCHIP) interpolator for a centrifugal pump's performance curves.

    Stores three interpolants as functions of flow Q (m³/s) at rated speed:
      • H(Q)     — total head  [m]
      • η(Q)     — hydraulic efficiency  [0, 1]
      • NPSHr(Q) — required NPSH  [m]

    Affinity laws scale the operating point for variable speed:
      Q_ref = Q / (n/n₀)
      H     = H_ref(Q_ref) × (n/n₀)²
      η     = η_ref(Q_ref)          (efficiency is speed-invariant)
      NPSHr = NPSHr_ref(Q_ref) × (n/n₀)²
    """

    def __init__(self, curve: PumpCurveData) -> None:
        flows = np.asarray(curve.flows, dtype=float)
        heads = np.asarray(curve.heads, dtype=float)
        etas = np.asarray(curve.efficiencies, dtype=float)
        npshr = np.asarray(curve.npsh_required, dtype=float)

        self._Q_min = float(flows[0])
        self._Q_max = float(flows[-1])

        self._H_interp = PchipInterpolator(flows, heads, extrapolate=False)
        self._eta_interp = PchipInterpolator(flows, etas, extrapolate=False)
        self._npsh_interp = PchipInterpolator(flows, npshr, extrapolate=False)

        # Derivatives (PCHIP provides exact analytical derivatives)
        self._dH_interp = self._H_interp.derivative()
        self._deta_interp = self._eta_interp.derivative()

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def head(self, Q: float, speed_ratio: float = 1.0) -> float:
        """Total dynamic head (m) at flow Q and speed ratio n/n₀."""
        Q_ref = self._Q_ref(Q, speed_ratio)
        H_ref = self._eval_H(Q_ref)
        return H_ref * speed_ratio ** 2

    def efficiency(self, Q: float, speed_ratio: float = 1.0) -> float:
        """Hydraulic efficiency (dimensionless) — speed-invariant."""
        Q_ref = self._Q_ref(Q, speed_ratio)
        return float(np.clip(self._eta_interp(Q_ref), 0.01, 1.0))

    def npsh_required(self, Q: float, speed_ratio: float = 1.0) -> float:
        """Required NPSH (m) at flow Q and speed ratio."""
        Q_ref = self._Q_ref(Q, speed_ratio)
        NPSHr_ref = float(np.clip(self._npsh_interp(Q_ref), 0.0, None))
        return NPSHr_ref * speed_ratio ** 2

    def dhead_dQ(self, Q: float, speed_ratio: float = 1.0) -> float:
        """
        Derivative dH/dQ for Jacobian construction.

        By affinity law:  H(Q, n) = H_ref(Q/n) · n²   where n = speed_ratio
        ∂H/∂Q = H_ref'(Q/n) · n²  ·  (1/n) = H_ref'(Q/n) · n
        """
        Q_ref = self._Q_ref(Q, speed_ratio)
        Q_ref_clamped = np.clip(Q_ref, self._Q_min, self._Q_max)
        dH_ref_dQref = float(self._dH_interp(Q_ref_clamped))
        return dH_ref_dQref * speed_ratio   # ∂H/∂Q

    def power(self, Q: float, speed_ratio: float = 1.0) -> float:
        """Shaft power consumption (W)."""
        H = self.head(Q, speed_ratio)
        eta = self.efficiency(Q, speed_ratio)
        if eta < 1e-6:
            return 0.0
        return RHO * G * Q * H / eta

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _Q_ref(self, Q: float, speed_ratio: float) -> float:
        """Map actual flow Q back to the reference (rated-speed) curve."""
        if speed_ratio < 1e-6:
            return 0.0
        return Q / speed_ratio

    def _eval_H(self, Q_ref: float) -> float:
        """Evaluate H at reference flow, clamped to curve bounds."""
        Q_clamped = np.clip(Q_ref, self._Q_min, self._Q_max)
        H = float(self._H_interp(Q_clamped))
        # Extrapolation guard: below Q_min use shutoff, above Q_max use runout
        if Q_ref < self._Q_min:
            H = float(self._H_interp(self._Q_min))
        elif Q_ref > self._Q_max:
            # Linear extrapolation towards zero (pump cannot deliver negative head)
            H = max(0.0, float(self._H_interp(self._Q_max)))
        return max(0.0, H)


# ---------------------------------------------------------------------------
# Cavitation check
# ---------------------------------------------------------------------------

def check_cavitation(
    Q: float,
    speed_ratio: float,
    suction_head: float,
    interpolator: PumpInterpolator,
    safety_factor: float = 1.0,
) -> CavitationResult:
    """
    Compare available NPSH (NPSHa) against required NPSH (NPSHr).

    NPSHa = H_suction - H_vapor
          = (P_s / ρg + z_s + v_s²/2g) - P_v/ρg

    For this model:
      suction_head = hydraulic head at the suction node (m)
      NPSHa = suction_head - pump.suction_elevation - VAPOR_PRESSURE_HEAD

    Parameters
    ----------
    Q : float
        Operating flow (m³/s).
    speed_ratio : float
        n/n₀.
    suction_head : float
        Hydraulic head at the suction flange (m).
    interpolator : PumpInterpolator
    safety_factor : float
        NPSHr is multiplied by this (default 1.0; use 1.1 for engineering margin).
    """
    npshr = interpolator.npsh_required(Q, speed_ratio) * safety_factor
    # NPSHa = absolute pressure head at suction minus vapour pressure head
    npsha = suction_head - VAPOR_PRESSURE_HEAD
    margin = npsha - npshr
    return CavitationResult(
        is_cavitating=(margin < 0.0),
        npsha=npsha,
        npshr=npshr,
        margin=margin,
    )


# ---------------------------------------------------------------------------
# Head-loss function (solver interface)
# ---------------------------------------------------------------------------

def compute_pump_headloss(
    Q: float,
    pump: Pump,
    interpolator: PumpInterpolator,
) -> Tuple[float, float]:
    """
    Return (h, dh_dQ) for a pump edge in the solver sign convention.

    The solver solves:  H_end - H_start = +H_pump(Q)   →   pump provides +head gain
    In the head-loss dispatcher we express it as a *negative* head loss so that
    the incidence-matrix formulation is uniform across all edge types:

      h = -H_pump(Q)    (negative = gain)
      dh/dQ = -dH/dQ

    For an OFF pump: model as a large linear resistance Q → 0.
    """
    if not pump.is_on:
        # Large resistance: h = R·Q, dh/dQ = R
        return OFF_PUMP_RESISTANCE * Q, OFF_PUMP_RESISTANCE

    H = interpolator.head(Q, pump.speed_ratio)
    dH_dQ = interpolator.dhead_dQ(Q, pump.speed_ratio)

    h = -H          # negative head loss = head gain
    dh_dQ = -dH_dQ

    # Guard: dh/dQ must be bounded for solver stability
    # At Q near 0, dH/dQ is finite (shutoff slope), so this is normally fine
    return h, dh_dQ
