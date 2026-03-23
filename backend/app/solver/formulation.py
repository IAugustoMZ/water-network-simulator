"""
H-equation hydraulic formulation.

Unknowns: hydraulic heads H_i at FREE (junction) nodes.
Fixed heads: reservoir and tank nodes (known boundary conditions).

Continuity equation for each free node i:
    F_i(H) = Σ_e A[i,e] · Q_e(H)  -  D_i  =  0

Key design decision:
    Rather than inverting h(Q) = ΔH with an inner Newton loop per edge
    (which is O(n_edges × n_iter) per outer NR step), we directly compute Q
    from the analytical inverse for each edge type:

    Pipe:  h = C · Q|Q|  →  Q = sign(ΔH) · sqrt(|ΔH| / C)
           where C = (f·L/D + K) / (2gA²)
           This requires iterating on C (since f depends on Re = f(Q)).
           We use a single-step fixed-point iteration with the previous Q
           as warm start — typically 3–5 iterations total per NR step.

    Pump:  h = -H_pump(Q)  →  solve H_pump(Q) = -ΔH
           Since H_pump is monotone decreasing, we use bisection bracketed
           by [Q_min, Q_max] from the pump curve — very fast.

    Valve: h = C_v · Q|Q|  →  Q = sign(ΔH) · sqrt(|ΔH| / C_v)
           Purely algebraic — O(1).
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple, Optional

import numpy as np

from ..graph.network import NetworkGraph
from ..graph.models import (
    Pipe, Pump, Valve, EdgeType,
    ReservoirNode, TankNode,
)
from ..physics.headloss import compute_headloss, PhysicsResult
from ..physics.pump import PumpInterpolator
from ..physics.friction import NU, G as GRAV

# Physical constants
RHO = 998.2
G = GRAV

# Guard
Q_MIN_SOLVE = 1e-12  # m³/s — minimum Q for iterative inversion


class HydraulicFormulation:
    """
    Assembles residuals and edge flows for the H-equation system.
    Uses analytical/semi-analytical Q-from-ΔH inversion for speed.
    """

    def __init__(
        self,
        network: NetworkGraph,
        pump_interpolators: Dict[str, PumpInterpolator],
    ) -> None:
        self.network = network
        self.pump_interpolators = pump_interpolators

        self.free_indices: List[int] = network.get_free_nodes()
        self.fixed_indices: List[int] = network.get_fixed_head_nodes()
        self.n_free: int = len(self.free_indices)
        self.n_fixed: int = len(self.fixed_indices)

        if self.n_free == 0:
            raise ValueError("Network has no free (junction) nodes.")
        if self.n_fixed == 0:
            raise ValueError("Network has no fixed-head nodes (reservoir or tank).")

        self.global_to_free: Dict[int, int] = {
            g: f for f, g in enumerate(self.free_indices)
        }
        self.global_to_fixed: Dict[int, int] = {
            g: f for f, g in enumerate(self.fixed_indices)
        }

        self.A_full = network.build_incidence_matrix()
        self.A_free = self.A_full[self.free_indices, :]

        # Warm-start cache for edge flows (speeds up line search)
        self._Q_cache: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Fixed heads
    # ------------------------------------------------------------------

    def get_fixed_heads(self) -> np.ndarray:
        heads = np.zeros(self.n_fixed)
        fixed_map = self.network.get_fixed_head_values()
        for f, g in enumerate(self.fixed_indices):
            heads[f] = fixed_map[g]
        return heads

    # ------------------------------------------------------------------
    # Full head vector
    # ------------------------------------------------------------------

    def build_full_head_vector(self, H_free: np.ndarray) -> np.ndarray:
        H_full = np.zeros(self.network.n_nodes)
        fixed_heads = self.get_fixed_heads()
        for f, g in enumerate(self.free_indices):
            H_full[g] = H_free[f]
        for f, g in enumerate(self.fixed_indices):
            H_full[g] = fixed_heads[f]
        return H_full

    # ------------------------------------------------------------------
    # Edge Q computation (fast analytical inversion)
    # ------------------------------------------------------------------

    def compute_edge_flows(
        self,
        H_free: np.ndarray,
    ) -> Tuple[np.ndarray, List[PhysicsResult]]:
        """
        Compute Q for all edges given current free-node heads.
        Uses fast analytical/semi-analytical inversion, no inner Newton loops.
        """
        H_full = self.build_full_head_vector(H_free)
        Q_vec = np.zeros(self.network.n_edges)
        results: List[PhysicsResult] = []

        # Use cached Q as warm start for pipe friction iteration
        Q_warm = self._Q_cache if self._Q_cache is not None else np.zeros(self.network.n_edges)

        for e_idx, edge in enumerate(self.network.edges):
            s = self.network.node_index[edge.start_node]
            t = self.network.node_index[edge.end_node]
            dH = H_full[s] - H_full[t]

            Q_w = float(Q_warm[e_idx]) if e_idx < len(Q_warm) else 0.0

            if edge.edge_type == EdgeType.PIPE:
                Q = _invert_pipe(edge, dH, Q_w)  # type: ignore[arg-type]
            elif edge.edge_type == EdgeType.PUMP:
                interp = self.pump_interpolators.get(edge.id)
                if interp is None:
                    raise KeyError(f"No interpolator for pump '{edge.id}'.")
                Q = _invert_pump(edge, dH, interp, Q_w)  # type: ignore[arg-type]
            elif edge.edge_type == EdgeType.VALVE:
                Q = _invert_valve(edge, dH)  # type: ignore[arg-type]
            else:
                Q = 0.0

            Q_vec[e_idx] = Q

            suction_heads = {edge.id: H_full[s]} if edge.edge_type == EdgeType.PUMP else {}
            res = compute_headloss(edge, Q, self.pump_interpolators, suction_heads)
            results.append(res)

        self._Q_cache = Q_vec.copy()
        return Q_vec, results

    # ------------------------------------------------------------------
    # Residual assembly
    # ------------------------------------------------------------------

    def assemble_residuals(
        self,
        H_free: np.ndarray,
        demands: np.ndarray,
    ) -> np.ndarray:
        Q_vec, _ = self.compute_edge_flows(H_free)
        F = np.asarray(self.A_free @ Q_vec).ravel() - demands
        return F

    def assemble_residuals_with_physics(
        self,
        H_free: np.ndarray,
        demands: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, List[PhysicsResult]]:
        Q_vec, physics_results = self.compute_edge_flows(H_free)
        F = np.asarray(self.A_free @ Q_vec).ravel() - demands
        return F, Q_vec, physics_results

    # ------------------------------------------------------------------
    # Legacy compatibility (used by Jacobian assembler)
    # ------------------------------------------------------------------

    def _invert_headloss(self, edge, dH: float, e_idx: int, max_iter: int = 10) -> float:
        """Single-edge Q inversion — fast analytical path."""
        if edge.edge_type == EdgeType.PIPE:
            Q_w = float(self._Q_cache[e_idx]) if self._Q_cache is not None and e_idx < len(self._Q_cache) else 0.0
            return _invert_pipe(edge, dH, Q_w)
        elif edge.edge_type == EdgeType.PUMP:
            interp = self.pump_interpolators.get(edge.id)
            Q_w = float(self._Q_cache[e_idx]) if self._Q_cache is not None and e_idx < len(self._Q_cache) else 0.0
            return _invert_pump(edge, dH, interp, Q_w)
        elif edge.edge_type == EdgeType.VALVE:
            return _invert_valve(edge, dH)
        return 0.0


# ---------------------------------------------------------------------------
# Fast analytical Q-from-ΔH inversion functions
# ---------------------------------------------------------------------------

def _invert_pipe(pipe: Pipe, dH: float, Q_warm: float = 0.0, max_iter: int = 8) -> float:
    """
    Solve h_pipe(Q) = dH for Q.

    h = [f(Re)·L/D + K] · Q|Q| / (2gA²) = C(Q) · Q|Q|

    Since C depends on Q via f(Re), iterate:
      1. Estimate f from current Q (warm start)
      2. Solve Q = sign(dH) · sqrt(|dH| / C) analytically
      3. Repeat 3–5 times until Q stabilises

    This converges much faster than inner Newton because it exploits
    the monotone structure of the Darcy-Weisbach equation.
    """
    from ..physics.friction import compute_friction_factor, NU

    A = pipe.area
    D = pipe.diameter
    L = pipe.length
    eps_D = pipe.relative_roughness
    K = pipe.minor_loss_coeff
    two_g_A2 = 2.0 * G * A ** 2

    # Near-zero head difference → near-zero flow
    if abs(dH) < 1e-12:
        return 0.0

    sign_dH = 1.0 if dH >= 0 else -1.0

    # Initial Q estimate
    Q = Q_warm if abs(Q_warm) > Q_MIN_SOLVE else sign_dH * math.sqrt(abs(dH) * two_g_A2) * 0.01

    for _ in range(max_iter):
        abs_Q = abs(Q)
        if abs_Q < Q_MIN_SOLVE:
            # Laminar limit
            f_lam = 128.0 * NU * L / (math.pi * G * D ** 4)
            Q_new = dH / (f_lam + K / (2.0 * G * A ** 2))
            return Q_new

        vel = abs_Q / A
        Re = vel * D / NU
        f, _ = compute_friction_factor(Re, eps_D)
        C = (f * L / D + K) / two_g_A2
        if C < 1e-30:
            return 0.0
        Q_new = sign_dH * math.sqrt(abs(dH) / C)
        if abs(Q_new - Q) < 1e-8:
            return Q_new
        Q = Q_new

    return Q


def _invert_pump(pump: Pump, dH: float, interp: PumpInterpolator, Q_warm: float = 0.0) -> float:
    """
    Solve h_pump(Q) = dH  (i.e., -H_pump(Q) = dH  →  H_pump(Q) = -dH).

    For a running pump: use bisection on H_pump(Q) = -dH.
    For a stopped pump: h = R·Q → Q = dH / R (linear).
    """
    if not pump.is_on:
        from ..physics.pump import OFF_PUMP_RESISTANCE
        return dH / OFF_PUMP_RESISTANCE

    target_H = -dH  # what the pump must produce

    # Pump produces positive head → target_H must be > 0
    if target_H <= 0.0:
        # Pump cannot sustain reverse head — return near-zero flow
        return Q_MIN_SOLVE

    # Bounds from affinity-scaled curve
    n = pump.speed_ratio
    Q_lo = interp._Q_min * n
    Q_hi = interp._Q_max * n

    H_lo = interp.head(Q_lo, n)
    H_hi = interp.head(Q_hi, n)

    # Check bounds
    if target_H >= H_lo:
        return Q_lo
    if target_H <= H_hi:
        return Q_hi

    # Bisection on monotone H(Q) curve
    for _ in range(50):
        Q_mid = (Q_lo + Q_hi) * 0.5
        H_mid = interp.head(Q_mid, n)
        if abs(H_mid - target_H) < 1e-6:
            return Q_mid
        if H_mid > target_H:
            Q_lo = Q_mid
        else:
            Q_hi = Q_mid
        if Q_hi - Q_lo < 1e-10:
            break

    return (Q_lo + Q_hi) * 0.5


def _invert_valve(valve: Valve, dH: float) -> float:
    """
    Solve h_valve(Q) = dH.

    h = Q|Q| / (Cv_eff² · g)  →  Q = sign(dH) · sqrt(|dH| · Cv_eff² · g)

    Fully analytical — O(1).
    """
    from ..physics.valve import cv_to_si, equal_percentage_characteristic, CV_MIN

    if valve.opening_fraction <= 0.0:
        # Closed valve: very high resistance
        return dH / 1e12

    Cv_si = cv_to_si(valve.cv_max)
    f_char = equal_percentage_characteristic(valve.opening_fraction, valve.rangeability)
    Cv_eff = Cv_si * f_char

    if Cv_eff < CV_MIN:
        return dH / 1e12

    Cv2g = Cv_eff ** 2 * G
    sign_dH = 1.0 if dH >= 0 else -1.0
    Q = sign_dH * math.sqrt(abs(dH) * Cv2g)
    return Q
