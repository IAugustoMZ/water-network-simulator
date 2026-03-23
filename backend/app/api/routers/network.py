"""POST /network — upload and validate a network definition."""
from __future__ import annotations

import math
import logging
from fastapi import APIRouter, HTTPException

from ..schemas import (
    NetworkDefinitionRequest, NetworkCreatedResponse,
    PumpCurveResponseSchema, PumpCurvePointSchema,
    SpeedCurveSchema, EfficiencyContourSchema, EfficiencyContourPointSchema,
)
from ...storage.stores import network_store
from ...graph.models import (
    JunctionNode, ReservoirNode, TankNode,
    Pipe, Pump, Valve, PumpCurveData, ValveType,
)
from ...graph.network import NetworkGraph
from ...physics.pump import PumpInterpolator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/network", tags=["network"])


def _build_node(schema):
    """Convert a validated schema node to a graph model node."""
    if schema.node_type == "junction":
        return JunctionNode(id=schema.id, elevation=schema.elevation, base_demand=schema.base_demand)
    elif schema.node_type == "reservoir":
        return ReservoirNode(id=schema.id, elevation=schema.elevation, total_head=schema.total_head)
    elif schema.node_type == "tank":
        return TankNode(
            id=schema.id, elevation=schema.elevation, water_level=schema.water_level,
            min_level=schema.min_level, max_level=schema.max_level, diameter=schema.diameter,
        )
    raise ValueError(f"Unknown node_type: {schema.node_type}")


def _build_edge(schema):
    """Convert a validated schema edge to a graph model edge."""
    if schema.edge_type == "pipe":
        return Pipe(
            id=schema.id, start_node=schema.start_node, end_node=schema.end_node,
            length=schema.length, diameter=schema.diameter, roughness=schema.roughness,
            minor_loss_coeff=schema.minor_loss_coeff,
        )
    elif schema.edge_type == "pump":
        curve = PumpCurveData(
            flows=schema.curve.flows,
            heads=schema.curve.heads,
            efficiencies=schema.curve.efficiencies,
            npsh_required=schema.curve.npsh_required,
        )
        return Pump(
            id=schema.id, start_node=schema.start_node, end_node=schema.end_node,
            curve=curve, speed_ratio=schema.speed_ratio, is_on=schema.is_on,
            suction_elevation=schema.suction_elevation,
        )
    elif schema.edge_type == "valve":
        vtype = ValveType(schema.valve_type)
        return Valve(
            id=schema.id, start_node=schema.start_node, end_node=schema.end_node,
            valve_type=vtype, cv_max=schema.cv_max,
            opening_fraction=schema.opening_fraction, setting=schema.setting,
            rangeability=schema.rangeability,
        )
    raise ValueError(f"Unknown edge_type: {schema.edge_type}")


@router.post("", response_model=NetworkCreatedResponse, status_code=201)
async def create_network(request: NetworkDefinitionRequest):
    """
    Upload a network definition and validate its topology.
    Returns a network_id for use in subsequent simulation calls.
    """
    try:
        nodes = [_build_node(n) for n in request.nodes]
        edges = [_build_edge(e) for e in request.edges]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Network construction error: {e}")

    try:
        network = NetworkGraph(nodes, edges)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    warnings = network.topological_validate()

    # Build pump interpolators for all pump edges
    pump_interpolators = {}
    for edge in edges:
        if edge.edge_type.value == "pump":
            pump_interpolators[edge.id] = PumpInterpolator(edge.curve)

    # Build demand dict from junction nodes
    demands = {
        n.id: n.base_demand for n in nodes if hasattr(n, "base_demand")
    }

    network_id = await network_store.put(
        network,
        {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "pump_interpolators": pump_interpolators,
            "demands": demands,
        },
    )

    logger.info(f"Network created: id={network_id}, nodes={len(nodes)}, edges={len(edges)}")
    if warnings:
        logger.warning(f"Network {network_id} validation warnings: {warnings}")

    return NetworkCreatedResponse(
        network_id=network_id,
        node_count=len(nodes),
        edge_count=len(edges),
        validation_warnings=warnings,
    )


@router.get("/{network_id}/pump-curves", response_model=list[PumpCurveResponseSchema])
async def get_pump_curves(network_id: str):
    """Return pump characteristic curves for plotting (multi-speed + iso-efficiency contours)."""
    network_data = await network_store.get(network_id)
    if network_data is None:
        raise HTTPException(status_code=404, detail=f"Network '{network_id}' not found or expired.")

    network = network_data["object"]
    pump_interpolators: dict = network_data.get("pump_interpolators", {})
    RHO, G = 998.2, 9.81
    N_PTS = 50

    def _safe(v: float) -> float:
        return 0.0 if (math.isnan(v) or math.isinf(v)) else v

    def _build_points(interp, speed: float, q_min: float, q_max: float) -> list[PumpCurvePointSchema]:
        pts = []
        for i in range(N_PTS + 1):
            q_ref = q_min + (q_max - q_min) * i / N_PTS
            q = q_ref * speed
            h = interp.head(q, speed)
            eta = interp.efficiency(q, speed)
            npshr = interp.npsh_required(q, speed)
            pw = (RHO * G * q * h / eta) / 1000.0 if eta > 1e-6 else 0.0
            pts.append(PumpCurvePointSchema(
                flow_lps=_safe(q * 1000.0), head=_safe(h),
                efficiency=_safe(eta), power_kw=_safe(pw), npsh_required=_safe(npshr),
            ))
        return pts

    def _build_speed_curves(interp, q_min: float, q_max: float, current_speed: float) -> list[SpeedCurveSchema]:
        levels = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        # Always include the current speed
        if not any(abs(current_speed - s) < 0.005 for s in levels):
            levels = sorted(set(levels + [current_speed]))
        curves = []
        for n in levels:
            if interp.head(0.0, n) < 0.5:
                continue  # skip speeds that produce negligible head
            is_current = abs(n - current_speed) < 0.005
            curves.append(SpeedCurveSchema(
                speed_ratio=n,
                label=f"{int(round(n * 100))}%",
                is_current=is_current,
                points=_build_points(interp, n, q_min, q_max),
            ))
        return curves

    def _build_efficiency_contours(
        interp, q_min: float, q_max: float, speed_min: float = 0.4, speed_max: float = 1.0,
    ) -> list[EfficiencyContourSchema]:
        from scipy.optimize import brentq
        import numpy as np

        q_scan = np.linspace(q_min + 1e-6, q_max - 1e-6, 500)
        eta_scan = np.array([interp.efficiency(float(q), 1.0) for q in q_scan])
        eta_max = float(eta_scan.max())
        q_bep_idx = int(np.argmax(eta_scan))
        q_bep = float(q_scan[q_bep_idx])

        # Generate contour levels from 30% up to 2% below BEP efficiency
        targets_raw = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.82, 0.85]
        eta_levels = [e for e in targets_raw if e < eta_max * 0.98]

        n_sweep = np.linspace(speed_min, speed_max, 35)
        contours = []

        for eta_target in eta_levels:
            branch_q_refs: list[tuple[str, float]] = []

            # Ascending branch (q_min → q_bep)
            try:
                if interp.efficiency(float(q_min + 1e-6), 1.0) < eta_target <= interp.efficiency(q_bep, 1.0):
                    q_lo = brentq(
                        lambda q: interp.efficiency(float(q), 1.0) - eta_target,
                        q_min + 1e-6, q_bep, xtol=1e-7,
                    )
                    branch_q_refs.append(("left", float(q_lo)))
            except ValueError:
                pass

            # Descending branch (q_bep → q_max)
            try:
                if interp.efficiency(float(q_max - 1e-6), 1.0) < eta_target <= interp.efficiency(q_bep, 1.0):
                    q_hi = brentq(
                        lambda q: interp.efficiency(float(q), 1.0) - eta_target,
                        q_bep, q_max - 1e-6, xtol=1e-7,
                    )
                    branch_q_refs.append(("right", float(q_hi)))
            except ValueError:
                pass

            if not branch_q_refs:
                continue

            # Build branches: each Q_ref traces a parabola H = H_ref · n², Q = Q_ref · n
            branches: dict[str, list[EfficiencyContourPointSchema]] = {}
            for side, q_ref in branch_q_refs:
                h_ref = interp.head(q_ref, 1.0)
                pts = []
                for n in n_sweep:
                    fl = _safe(q_ref * n * 1000.0)
                    hd = _safe(h_ref * n * n)
                    if fl > 0 and hd > 0:
                        pts.append(EfficiencyContourPointSchema(
                            flow_lps=round(fl, 3), head=round(hd, 3)
                        ))
                branches[side] = pts

            # Combine into a closed "banana" contour (left ascending, right descending reversed)
            if "left" in branches and "right" in branches:
                combined = branches["left"] + list(reversed(branches["right"]))
            else:
                combined = branches.get("left", []) or branches.get("right", [])

            if combined:
                contours.append(EfficiencyContourSchema(
                    efficiency=eta_target,
                    label=f"{int(round(eta_target * 100))}%",
                    points=combined,
                ))

        return contours

    results = []
    for edge in network.edges:
        if edge.edge_type.value != "pump":
            continue
        interp = pump_interpolators.get(edge.id)
        if interp is None:
            continue

        curve = edge.curve
        q_min, q_max = curve.flows[0], curve.flows[-1]
        current_speed = edge.speed_ratio

        results.append(PumpCurveResponseSchema(
            pump_id=edge.id,
            start_node=edge.start_node,
            end_node=edge.end_node,
            speed_ratio=current_speed,
            is_on=edge.is_on,
            rated_curve=_build_points(interp, 1.0, q_min, q_max),
            current_curve=_build_points(interp, current_speed, q_min, q_max),
            speed_curves=_build_speed_curves(interp, q_min, q_max, current_speed),
            efficiency_contours=_build_efficiency_contours(interp, q_min, q_max),
        ))

    return results


@router.get("/default-id")
async def get_default_network_id():
    """Return the ID of the pre-loaded city network."""
    from main import DEFAULT_NETWORK_ID
    return {"network_id": DEFAULT_NETWORK_ID}
