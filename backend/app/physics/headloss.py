"""
Unified head-loss dispatcher.

Given any edge (Pipe, Pump, or Valve) and a flow Q, returns a PhysicsResult
with all hydraulic quantities needed by the solver and post-processor.

This is the single entry point for the solver; it never calls individual
physics modules directly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..graph.models import AnyEdge, EdgeType, Pipe, Pump, Valve
from .friction import compute_pipe_headloss, NU, G
from .pump import PumpInterpolator, compute_pump_headloss, check_cavitation
from .valve import compute_valve_headloss


@dataclass
class PhysicsResult:
    """Full hydraulic result for a single edge."""
    edge_id: str
    edge_type: str                  # "pipe" | "pump" | "valve"
    flow: float                     # m³/s  (signed — positive = start→end)
    head_loss: float                # m  (positive = loss; negative = gain for pumps)
    dh_dQ: float                    # dh/dQ  for Jacobian
    velocity: float                 # m/s  (magnitude, unsigned)
    reynolds: float                 # Re  (0 for pumps/valves)
    friction_factor: float          # f   (0 for pumps/valves)
    status: str                     # "normal" | "cavitating" | "closed" | "off" | "throttling"
    # Pump-specific (None for pipes/valves)
    pump_head: Optional[float] = None         # m
    pump_efficiency: Optional[float] = None   # [0, 1]
    pump_power_w: Optional[float] = None      # W
    npsha: Optional[float] = None             # m
    npshr: Optional[float] = None             # m
    cavitation_margin: Optional[float] = None # m
    # Valve-specific
    valve_opening: Optional[float] = None     # [0, 1]


def compute_headloss(
    edge: AnyEdge,
    Q: float,
    pump_interpolators: Optional[Dict[str, PumpInterpolator]] = None,
    suction_heads: Optional[Dict[str, float]] = None,
) -> PhysicsResult:
    """
    Dispatch head-loss computation to the appropriate physics model.

    Parameters
    ----------
    edge : AnyEdge
        Pipe, Pump, or Valve object.
    Q : float
        Flow (m³/s), signed.
    pump_interpolators : dict, optional
        Mapping pump_id → PumpInterpolator.  Required for Pump edges.
    suction_heads : dict, optional
        Mapping pump_id → hydraulic head at suction node (m).
        Required for cavitation check.

    Returns
    -------
    PhysicsResult
    """
    if pump_interpolators is None:
        pump_interpolators = {}
    if suction_heads is None:
        suction_heads = {}

    if edge.edge_type == EdgeType.PIPE:
        return _pipe_result(edge, Q)  # type: ignore[arg-type]
    elif edge.edge_type == EdgeType.PUMP:
        return _pump_result(edge, Q, pump_interpolators, suction_heads)  # type: ignore[arg-type]
    elif edge.edge_type == EdgeType.VALVE:
        return _valve_result(edge, Q)  # type: ignore[arg-type]
    else:
        raise ValueError(f"Unknown edge type: {edge.edge_type}")


# ---------------------------------------------------------------------------
# Private dispatch functions
# ---------------------------------------------------------------------------

def _pipe_result(pipe: Pipe, Q: float) -> PhysicsResult:
    h, dh_dQ = compute_pipe_headloss(Q, pipe)

    A = pipe.area
    vel = abs(Q) / A if A > 0 else 0.0
    Re = vel * pipe.diameter / NU if NU > 0 else 0.0

    # Friction factor: derive from h = f·(L/D)·Q|Q|/(2gA²) + K·Q|Q|/(2gA²)
    # Solve for f from computed h and Q (approximate — minor losses included)
    two_g_A2 = 2.0 * G * A ** 2
    abs_Q = abs(Q)
    if abs_Q > 1e-10 and pipe.length > 0:
        h_major = h - pipe.minor_loss_coeff * Q * abs_Q / two_g_A2
        f_approx = h_major * two_g_A2 / (abs_Q ** 2 * pipe.length / pipe.diameter)
        f_approx = max(0.0, f_approx)
    else:
        # Use laminar formula as fallback
        if Re > 0:
            f_approx = min(64.0 / Re, 1.0)
        else:
            f_approx = 0.064

    return PhysicsResult(
        edge_id=pipe.id,
        edge_type="pipe",
        flow=Q,
        head_loss=h,
        dh_dQ=dh_dQ,
        velocity=vel,
        reynolds=Re,
        friction_factor=f_approx,
        status="normal",
    )


def _pump_result(
    pump: Pump,
    Q: float,
    interpolators: Dict[str, PumpInterpolator],
    suction_heads: Dict[str, float],
) -> PhysicsResult:
    interp = interpolators.get(pump.id)
    if interp is None:
        raise KeyError(f"No interpolator found for pump '{pump.id}'.")

    h, dh_dQ = compute_pump_headloss(Q, pump, interp)

    if not pump.is_on:
        return PhysicsResult(
            edge_id=pump.id,
            edge_type="pump",
            flow=Q,
            head_loss=h,
            dh_dQ=dh_dQ,
            velocity=0.0,
            reynolds=0.0,
            friction_factor=0.0,
            status="off",
            pump_head=0.0,
            pump_efficiency=0.0,
            pump_power_w=0.0,
            npsha=0.0,
            npshr=0.0,
            cavitation_margin=0.0,
        )

    pump_head = interp.head(Q, pump.speed_ratio)
    eta = interp.efficiency(Q, pump.speed_ratio)
    power = interp.power(Q, pump.speed_ratio)

    # Cavitation check
    suction_head = suction_heads.get(pump.id, pump.suction_elevation + 10.0)
    cav = check_cavitation(Q, pump.speed_ratio, suction_head, interp)

    status = "cavitating" if cav.is_cavitating else "normal"

    return PhysicsResult(
        edge_id=pump.id,
        edge_type="pump",
        flow=Q,
        head_loss=h,
        dh_dQ=dh_dQ,
        velocity=0.0,       # pumps don't have a single representative pipe velocity
        reynolds=0.0,
        friction_factor=0.0,
        status=status,
        pump_head=pump_head,
        pump_efficiency=eta,
        pump_power_w=power,
        npsha=cav.npsha,
        npshr=cav.npshr,
        cavitation_margin=cav.margin,
    )


def _valve_result(valve: Valve, Q: float) -> PhysicsResult:
    h, dh_dQ = compute_valve_headloss(Q, valve)

    if valve.opening_fraction <= 0.0:
        status = "closed"
    elif valve.opening_fraction >= 1.0:
        status = "open"
    else:
        status = "throttling"

    return PhysicsResult(
        edge_id=valve.id,
        edge_type="valve",
        flow=Q,
        head_loss=h,
        dh_dQ=dh_dQ,
        velocity=0.0,
        reynolds=0.0,
        friction_factor=0.0,
        status=status,
        valve_opening=valve.opening_fraction,
    )
