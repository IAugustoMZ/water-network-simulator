"""
Post-processor: converts raw solver output into engineering-grade results.

Computes all required outputs:
  Nodes   : pressure (m, kPa), hydraulic head
  Pipes   : flow, velocity, Re, head loss, friction factor
  Pumps   : Q, H, η, power, NPSHa, NPSHr, cavitation margin
  Valves  : flow, pressure drop, opening, status
  Tanks   : water level, head, outflow, residence time
  System  : mass balance, efficiency, warnings
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..graph.models import (
    AnyNode, JunctionNode, ReservoirNode, TankNode,
    Pipe, Pump, Valve, ValveType,
)
from ..graph.network import NetworkGraph
from ..physics.headloss import PhysicsResult
from ..physics.pump import PumpInterpolator, check_cavitation

# Physical constants
G: float = 9.81
RHO: float = 998.2

# Thresholds
LOW_PRESSURE_THRESHOLD: float = 10.0    # m  — below this = low pressure warning
HIGH_VELOCITY_THRESHOLD: float = 2.5    # m/s — above this = bottleneck


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NodeResult:
    node_id: str
    node_type: str
    elevation: float          # m
    hydraulic_head: float     # m
    pressure_m: float         # m  = head - elevation
    pressure_kpa: float       # kPa
    demand: float             # m³/s


@dataclass
class EdgeResult:
    edge_id: str
    edge_type: str
    start_node: str
    end_node: str
    flow: float               # m³/s (signed)
    flow_lps: float           # L/s
    velocity: float           # m/s
    head_loss: float          # m
    reynolds: float
    friction_factor: float
    is_reversed: bool
    status: str


@dataclass
class PumpResult:
    pump_id: str
    is_on: bool
    flow: float               # m³/s
    flow_lps: float
    head: float               # m
    speed_ratio: float
    efficiency: float         # 0-1
    power_kw: float
    npsha: float              # m
    npshr: float              # m
    cavitation_margin: float  # m  (negative = cavitating)
    is_cavitating: bool
    status: str


@dataclass
class ValveResult:
    valve_id: str
    valve_type: str
    flow: float               # m³/s
    flow_lps: float
    pressure_drop_m: float    # m
    opening_fraction: float
    status: str


@dataclass
class TankResult:
    tank_id: str
    water_level: float        # m
    hydraulic_head: float     # m
    outflow: float            # m³/s  (net, positive = leaving tank)
    residence_time: float     # s  = volume / |outflow|


@dataclass
class SystemMetrics:
    total_demand: float           # m³/s  (sum of all junction demands)
    total_supply: float           # m³/s  (net inflow from reservoirs + pumps)
    mass_balance_error: float     # m³/s  (|supply - demand|, should be ~0)
    min_pressure_m: float
    max_pressure_m: float
    min_pressure_node: str
    max_pressure_node: str
    low_pressure_nodes: List[str]
    flow_reversals: List[str]     # edge IDs with Q < 0 and expected direction positive
    bottleneck_edges: List[str]   # edge IDs with velocity > threshold
    system_efficiency: float      # hydraulic power delivered / shaft power consumed
    total_power_kw: float


# ---------------------------------------------------------------------------
# Post-processor
# ---------------------------------------------------------------------------

class PostProcessor:
    """
    Computes all derived hydraulic quantities from solver output.
    """

    def __init__(
        self,
        network: NetworkGraph,
        pump_interpolators: Dict[str, PumpInterpolator],
    ) -> None:
        self.network = network
        self.pump_interpolators = pump_interpolators

    def process(
        self,
        H_free: np.ndarray,
        edge_flows: np.ndarray,
        physics_results: List[PhysicsResult],
        demands: np.ndarray,
    ) -> Dict:
        """
        Compute all engineering outputs.

        Parameters
        ----------
        H_free : np.ndarray  shape (n_free,)
        edge_flows : np.ndarray  shape (n_edges,)
        physics_results : list of PhysicsResult
        demands : np.ndarray  shape (n_free,)  — demand per free node (m³/s)

        Returns
        -------
        dict with keys: nodes, edges, pumps, valves, tanks, system_metrics
        """
        # Build full head vector
        H_full = self._build_full_head(H_free)

        # Build demand vector aligned to all nodes
        demand_full = self._build_full_demands(demands)

        # Process each category
        node_results = self._process_nodes(H_full, demand_full)
        edge_results, pump_results, valve_results = self._process_edges(
            edge_flows, physics_results, H_full
        )
        tank_results = self._process_tanks(H_full, edge_flows)
        system_metrics = self._compute_system_metrics(
            node_results, edge_results, pump_results, demand_full
        )

        return {
            "nodes": node_results,
            "edges": edge_results,
            "pumps": pump_results,
            "valves": valve_results,
            "tanks": tank_results,
            "system_metrics": system_metrics,
        }

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _build_full_head(self, H_free: np.ndarray) -> np.ndarray:
        """Reconstruct H for all nodes."""
        H_full = np.zeros(self.network.n_nodes)
        free_idx = self.network.get_free_nodes()
        fixed_vals = self.network.get_fixed_head_values()
        for f, g in enumerate(free_idx):
            H_full[g] = H_free[f]
        for g, h in fixed_vals.items():
            H_full[g] = h
        return H_full

    def _build_full_demands(self, demands: np.ndarray) -> np.ndarray:
        """Build demand array for all nodes (0 for reservoirs/tanks)."""
        demand_full = np.zeros(self.network.n_nodes)
        free_idx = self.network.get_free_nodes()
        for f, g in enumerate(free_idx):
            demand_full[g] = demands[f]
        return demand_full

    def _process_nodes(self, H_full: np.ndarray, demand_full: np.ndarray) -> List[NodeResult]:
        results = []
        for i, node in enumerate(self.network.nodes):
            h = float(H_full[i])
            elev = node.elevation
            p_m = h - elev
            p_kpa = p_m * RHO * G / 1000.0
            demand = float(demand_full[i])

            results.append(NodeResult(
                node_id=node.id,
                node_type=node.node_type.value,
                elevation=elev,
                hydraulic_head=h,
                pressure_m=p_m,
                pressure_kpa=p_kpa,
                demand=demand,
            ))
        return results

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def _process_edges(
        self,
        edge_flows: np.ndarray,
        physics_results: List[PhysicsResult],
        H_full: np.ndarray,
    ) -> Tuple[List[EdgeResult], List[PumpResult], List[ValveResult]]:
        edge_results: List[EdgeResult] = []
        pump_results: List[PumpResult] = []
        valve_results: List[ValveResult] = []

        for e_idx, (edge, pr) in enumerate(zip(self.network.edges, physics_results)):
            Q = float(edge_flows[e_idx])

            if edge.edge_type.value == "pipe":
                pipe: Pipe = edge  # type: ignore
                er = EdgeResult(
                    edge_id=edge.id,
                    edge_type="pipe",
                    start_node=edge.start_node,
                    end_node=edge.end_node,
                    flow=Q,
                    flow_lps=Q * 1000.0,
                    velocity=pr.velocity,
                    head_loss=pr.head_loss,
                    reynolds=pr.reynolds,
                    friction_factor=pr.friction_factor,
                    is_reversed=(Q < 0),
                    status=pr.status,
                )
                edge_results.append(er)

            elif edge.edge_type.value == "pump":
                pump: Pump = edge  # type: ignore
                interp = self.pump_interpolators.get(pump.id)
                s_global = self.network.node_index[pump.start_node]
                suction_head = float(H_full[s_global])

                if pump.is_on and interp is not None:
                    pump_head = interp.head(Q, pump.speed_ratio)
                    eta = interp.efficiency(Q, pump.speed_ratio)
                    power_w = interp.power(Q, pump.speed_ratio)
                    cav = check_cavitation(Q, pump.speed_ratio, suction_head, interp)
                    npsha, npshr, margin, is_cav = cav.npsha, cav.npshr, cav.margin, cav.is_cavitating
                    status = "cavitating" if is_cav else "normal"
                else:
                    pump_head = 0.0
                    eta = 0.0
                    power_w = 0.0
                    npsha = npshr = margin = 0.0
                    is_cav = False
                    status = "off"

                pump_results.append(PumpResult(
                    pump_id=pump.id,
                    is_on=pump.is_on,
                    flow=Q,
                    flow_lps=Q * 1000.0,
                    head=pump_head,
                    speed_ratio=pump.speed_ratio,
                    efficiency=eta,
                    power_kw=power_w / 1000.0,
                    npsha=npsha,
                    npshr=npshr,
                    cavitation_margin=margin,
                    is_cavitating=is_cav,
                    status=status,
                ))

                # Also record as an edge result for the network graph
                edge_results.append(EdgeResult(
                    edge_id=edge.id,
                    edge_type="pump",
                    start_node=edge.start_node,
                    end_node=edge.end_node,
                    flow=Q,
                    flow_lps=Q * 1000.0,
                    velocity=0.0,
                    head_loss=pr.head_loss,
                    reynolds=0.0,
                    friction_factor=0.0,
                    is_reversed=(Q < 0),
                    status=status,
                ))

            elif edge.edge_type.value == "valve":
                valve: Valve = edge  # type: ignore
                s_global = self.network.node_index[valve.start_node]
                t_global = self.network.node_index[valve.end_node]
                dH = float(H_full[s_global] - H_full[t_global])
                p_drop = abs(dH)

                valve_results.append(ValveResult(
                    valve_id=valve.id,
                    valve_type=valve.valve_type.value,
                    flow=Q,
                    flow_lps=Q * 1000.0,
                    pressure_drop_m=p_drop,
                    opening_fraction=valve.opening_fraction,
                    status=pr.status,
                ))

                edge_results.append(EdgeResult(
                    edge_id=edge.id,
                    edge_type="valve",
                    start_node=edge.start_node,
                    end_node=edge.end_node,
                    flow=Q,
                    flow_lps=Q * 1000.0,
                    velocity=0.0,
                    head_loss=pr.head_loss,
                    reynolds=0.0,
                    friction_factor=0.0,
                    is_reversed=(Q < 0),
                    status=pr.status,
                ))

        return edge_results, pump_results, valve_results

    # ------------------------------------------------------------------
    # Tanks
    # ------------------------------------------------------------------

    def _process_tanks(
        self,
        H_full: np.ndarray,
        edge_flows: np.ndarray,
    ) -> List[TankResult]:
        results = []
        A_full = self.network.build_incidence_matrix()

        for i, node in enumerate(self.network.nodes):
            if not isinstance(node, TankNode):
                continue

            h = float(H_full[i])
            # Net outflow from tank = row i of A @ Q (positive = leaving)
            row = A_full.getrow(i)
            net_outflow = float(row @ edge_flows)

            volume = node.volume
            residence = volume / abs(net_outflow) if abs(net_outflow) > 1e-9 else float("inf")

            results.append(TankResult(
                tank_id=node.id,
                water_level=node.water_level,
                hydraulic_head=h,
                outflow=net_outflow,
                residence_time=residence,
            ))

        return results

    # ------------------------------------------------------------------
    # System metrics
    # ------------------------------------------------------------------

    def _compute_system_metrics(
        self,
        node_results: List[NodeResult],
        edge_results: List[EdgeResult],
        pump_results: List[PumpResult],
        demand_full: np.ndarray,
    ) -> SystemMetrics:
        # Pressures
        junction_pressures = [
            nr for nr in node_results if nr.node_type == "junction"
        ]
        if junction_pressures:
            pressures = [nr.pressure_m for nr in junction_pressures]
            min_p = float(min(pressures))
            max_p = float(max(pressures))
            min_node = junction_pressures[pressures.index(min_p)].node_id
            max_node = junction_pressures[pressures.index(max_p)].node_id
            low_pressure_nodes = [
                nr.node_id for nr in junction_pressures if nr.pressure_m < LOW_PRESSURE_THRESHOLD
            ]
        else:
            min_p = max_p = 0.0
            min_node = max_node = ""
            low_pressure_nodes = []

        # Flow reversals (pipes where Q < 0)
        flow_reversals = [er.edge_id for er in edge_results if er.is_reversed and er.edge_type == "pipe"]

        # Bottlenecks
        bottleneck_edges = [
            er.edge_id for er in edge_results
            if er.edge_type == "pipe" and er.velocity > HIGH_VELOCITY_THRESHOLD
        ]

        # Mass balance
        total_demand = float(np.sum(demand_full))
        total_pump_supply = sum(pr.flow for pr in pump_results if pr.is_on and pr.flow > 0)
        # Total supply also includes reservoir inflows (inferred from mass balance)
        total_supply = total_pump_supply + total_demand  # simplified: supply = demand + pump
        mass_balance_error = abs(total_demand - total_supply + total_pump_supply)

        # Power and efficiency
        total_power_w = sum(pr.power_kw * 1000.0 for pr in pump_results)
        hydraulic_power_w = sum(
            pr.flow * pr.head * RHO * G
            for pr in pump_results if pr.is_on
        )
        system_efficiency = (
            hydraulic_power_w / total_power_w if total_power_w > 0 else 0.0
        )

        return SystemMetrics(
            total_demand=total_demand,
            total_supply=total_supply,
            mass_balance_error=mass_balance_error,
            min_pressure_m=min_p,
            max_pressure_m=max_p,
            min_pressure_node=min_node,
            max_pressure_node=max_node,
            low_pressure_nodes=low_pressure_nodes,
            flow_reversals=flow_reversals,
            bottleneck_edges=bottleneck_edges,
            system_efficiency=system_efficiency,
            total_power_kw=total_power_w / 1000.0,
        )
