"""POST /simulate — run steady-state hydraulic simulation."""
from __future__ import annotations

import copy
import logging
from dataclasses import asdict

import numpy as np
from fastapi import APIRouter, HTTPException

from ..schemas import (
    SimulationRequest, SimulationPreviewResponse, SimulationResultSchema,
    NodeResultSchema, EdgeResultSchema, PumpResultSchema, ValveResultSchema,
    TankResultSchema, SystemMetricsSchema, SimulationWarningSchema,
)
from ...storage.stores import network_store, result_store
from ...solver.formulation import HydraulicFormulation
from ...solver.newton_raphson import NewtonRaphsonSolver, SolverConfig, SolverDivergenceError
from ...solver.postprocessor import PostProcessor
from ...network.city_network import SCENARIOS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulate", tags=["simulation"])


def _apply_overrides(network, demands: dict, overrides) -> None:
    """Mutate network and demands in-place with user overrides."""
    # Pump overrides
    for edge in network.edges:
        if edge.edge_type.value == "pump":
            ov = overrides.pumps.get(edge.id)
            if ov:
                if ov.is_on is not None:
                    edge.is_on = ov.is_on
                if ov.speed_ratio is not None:
                    edge.speed_ratio = ov.speed_ratio

    # Valve overrides
    for edge in network.edges:
        if edge.edge_type.value == "valve":
            ov = overrides.valves.get(edge.id)
            if ov:
                if ov.opening_fraction is not None:
                    edge.opening_fraction = ov.opening_fraction
                if ov.setting is not None:
                    edge.setting = ov.setting

    # Per-node demand multipliers
    for node_id, mult in overrides.demand_multipliers.items():
        if node_id in demands:
            demands[node_id] *= mult

    # Global demand multiplier
    gm = overrides.global_demand_multiplier
    if gm != 1.0:
        for k in demands:
            demands[k] *= gm

    # Tank level overrides
    for node in network.nodes:
        if node.node_type.value == "tank" and node.id in overrides.tank_levels:
            node.water_level = overrides.tank_levels[node.id]


def _build_demand_vector(formulation: HydraulicFormulation, demands: dict) -> np.ndarray:
    """Build demand array aligned to free node indices."""
    D = np.zeros(formulation.n_free)
    for f, g in enumerate(formulation.free_indices):
        node = formulation.network.nodes[g]
        D[f] = demands.get(node.id, 0.0)
    return D


def _collect_warnings(solver_warnings, processed) -> list[SimulationWarningSchema]:
    warnings = []

    # Solver warnings
    for w in solver_warnings:
        warnings.append(SimulationWarningSchema(
            code="solver_warning", message=w, severity="warning"
        ))

    # Cavitating pumps
    for pr in processed["pumps"]:
        if pr.is_cavitating:
            warnings.append(SimulationWarningSchema(
                code="cavitation", component_id=pr.pump_id,
                message=f"Pump {pr.pump_id} is cavitating (margin={pr.cavitation_margin:.2f} m)",
                severity="critical",
            ))

    # Low pressure nodes
    metrics = processed["system_metrics"]
    for nid in metrics.low_pressure_nodes:
        warnings.append(SimulationWarningSchema(
            code="low_pressure", component_id=nid,
            message=f"Node {nid} has pressure below 10 m",
            severity="warning",
        ))

    # Bottleneck pipes
    for eid in metrics.bottleneck_edges:
        warnings.append(SimulationWarningSchema(
            code="bottleneck", component_id=eid,
            message=f"Edge {eid} velocity exceeds 2.5 m/s",
            severity="info",
        ))

    return warnings


def _build_result_schema(
    result_id: str,
    network_id: str,
    scenario_name: str,
    solver_result,
    status: str,
    processed: dict,
    warnings: list,
) -> SimulationResultSchema:
    metrics = processed["system_metrics"]

    return SimulationResultSchema(
        result_id=result_id,
        network_id=network_id,
        scenario_name=scenario_name,
        status=status,
        iterations=solver_result.iterations,
        residual_norm=solver_result.residual_norm,
        nodes=[NodeResultSchema(**{
            k: getattr(n, k) for k in NodeResultSchema.model_fields
        }) for n in processed["nodes"]],
        edges=[EdgeResultSchema(**{
            k: getattr(e, k) for k in EdgeResultSchema.model_fields
        }) for e in processed["edges"]],
        pumps=[PumpResultSchema(**{
            k: getattr(p, k) for k in PumpResultSchema.model_fields
        }) for p in processed["pumps"]],
        valves=[ValveResultSchema(**{
            k: getattr(v, k) for k in ValveResultSchema.model_fields
        }) for v in processed["valves"]],
        tanks=[TankResultSchema(**{
            k: getattr(t, k) for k in TankResultSchema.model_fields
        }) for t in processed["tanks"]],
        system_metrics=SystemMetricsSchema(**{
            k: getattr(metrics, k) for k in SystemMetricsSchema.model_fields
        }),
        warnings=warnings,
    )


@router.post("", response_model=SimulationPreviewResponse)
async def run_simulation(request: SimulationRequest):
    """
    Run steady-state hydraulic simulation.
    Returns a preview immediately; full results at GET /results/{result_id}.
    """
    # 1. Retrieve network
    network_data = await network_store.get(request.network_id)
    if network_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Network '{request.network_id}' not found or expired."
        )

    network = network_data["object"]
    pump_interpolators = network_data.get("pump_interpolators", {})
    base_demands = network_data.get("demands", {})

    # 2. Deep copy to avoid mutating the stored network
    network_copy = copy.deepcopy(network)
    demands_copy = copy.deepcopy(base_demands)

    # 3. Apply scenario presets first (if specified)
    scenario_name = request.scenario_name or "baseline"
    if scenario_name in SCENARIOS:
        preset = SCENARIOS[scenario_name]
        # Apply preset pump overrides
        for edge in network_copy.edges:
            if edge.edge_type.value == "pump":
                ov = preset.get("pump_overrides", {}).get(edge.id, {})
                if "is_on" in ov:
                    edge.is_on = ov["is_on"]
                if "speed_ratio" in ov:
                    edge.speed_ratio = ov["speed_ratio"]
        # Apply preset valve overrides
        for edge in network_copy.edges:
            if edge.edge_type.value == "valve":
                ov = preset.get("valve_overrides", {}).get(edge.id, {})
                if "opening_fraction" in ov:
                    edge.opening_fraction = ov["opening_fraction"]
                if "setting" in ov:
                    edge.setting = ov["setting"]
        # Apply preset demand multipliers
        for nid, mult in preset.get("demand_multipliers", {}).items():
            if nid in demands_copy:
                demands_copy[nid] *= mult
        gm = preset.get("global_demand_multiplier", 1.0)
        if gm != 1.0:
            demands_copy = {k: v * gm for k, v in demands_copy.items()}

    # 4. Apply manual overrides on top (override takes precedence)
    _apply_overrides(network_copy, demands_copy, request.overrides)

    # 5. Setup and run solver
    formulation = HydraulicFormulation(network_copy, pump_interpolators)
    solver = NewtonRaphsonSolver(formulation, SolverConfig())
    demand_vector = _build_demand_vector(formulation, demands_copy)

    try:
        solver_result = solver.solve(demand_vector)
        status = "converged" if solver_result.converged else "diverged"
    except SolverDivergenceError as exc:
        logger.error(f"Solver diverged: {exc}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "solver_divergence",
                "message": str(exc),
                "iterations": exc.iterations,
                "residual": exc.residual,
            },
        )

    # 6. Post-process
    pp = PostProcessor(network_copy, pump_interpolators)
    processed = pp.process(
        solver_result.H_free,
        solver_result.edge_flows,
        solver_result.physics_results,
        demand_vector,
    )

    # 7. Collect warnings
    all_warnings = _collect_warnings(solver_result.warnings, processed)

    # 8. Build and store full result
    result_id = str(__import__("uuid").uuid4())
    full_result = _build_result_schema(
        result_id=result_id,
        network_id=request.network_id,
        scenario_name=scenario_name,
        solver_result=solver_result,
        status=status,
        processed=processed,
        warnings=all_warnings,
    )
    await result_store.put(full_result, {}, store_id=result_id)

    metrics = processed["system_metrics"]
    logger.info(
        f"Simulation complete: scenario={scenario_name}, status={status}, "
        f"iters={solver_result.iterations}, residual={solver_result.residual_norm:.2e}"
    )

    return SimulationPreviewResponse(
        result_id=result_id,
        status=status,
        iterations=solver_result.iterations,
        residual_norm=solver_result.residual_norm,
        total_demand=metrics.total_demand,
        min_pressure_m=metrics.min_pressure_m,
        max_pressure_m=metrics.max_pressure_m,
        warnings_count=len(all_warnings),
    )
