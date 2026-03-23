"""POST /analyze/{result_id} — AI-powered hydraulic network analysis."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from ..schemas import AIAnalysisResponseSchema, AnalysisIssueSchema, AnalysisRecommendationSchema
from ...storage.stores import result_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["AI analysis"])


def _format_simulation_summary(result) -> str:
    """Build a concise text summary of the simulation result for the LLM."""
    m = result.system_metrics
    pumps = result.pumps
    warnings = result.warnings

    pump_lines = []
    for p in pumps:
        if p.is_on:
            cav = " ⚠ CAVITATING" if p.is_cavitating else ""
            pump_lines.append(
                f"  {p.pump_id}: Q={p.flow_lps:.1f} L/s  H={p.head:.1f} m  "
                f"speed={p.speed_ratio * 100:.0f}%  η={p.efficiency * 100:.1f}%  "
                f"P={p.power_kw:.1f} kW  NPSHa={p.npsha:.2f} m  NPSHr={p.npshr:.2f} m  "
                f"margin={p.cavitation_margin:.2f} m{cav}"
            )
        else:
            pump_lines.append(f"  {p.pump_id}: OFF")

    warning_lines = [
        f"  [{w.severity.upper()}] {w.message}"
        for w in warnings
    ]

    lp_nodes = ", ".join(m.low_pressure_nodes) if m.low_pressure_nodes else "None"
    reversals = ", ".join(m.flow_reversals) if m.flow_reversals else "None"
    bottlenecks = ", ".join(m.bottleneck_edges) if m.bottleneck_edges else "None"

    # Low-pressure node details (top 5)
    low_p_details = ""
    lp_node_ids = set(m.low_pressure_nodes)
    if lp_node_ids:
        lp_rows = [
            f"  {n.node_id}: {n.pressure_m:.1f} m"
            for n in result.nodes
            if n.node_id in lp_node_ids
        ][:5]
        low_p_details = "\nLOW-PRESSURE NODE DETAILS:\n" + "\n".join(lp_rows)

    return (
        f"SCENARIO: {result.scenario_name}\n"
        f"SOLVER STATUS: {result.status} in {result.iterations} iterations "
        f"(residual {result.residual_norm:.2e} m³/s)\n\n"
        f"SYSTEM METRICS:\n"
        f"  Demand:           {m.total_demand * 1000:.1f} L/s\n"
        f"  Supply:           {m.total_supply * 1000:.1f} L/s\n"
        f"  Mass-balance err: {m.mass_balance_error:.2e} m³/s\n"
        f"  Pressure range:   {m.min_pressure_m:.1f} – {m.max_pressure_m:.1f} m "
        f"(minimum acceptable: 10 m)\n"
        f"  System efficiency:{m.system_efficiency * 100:.1f}%\n"
        f"  Total power:      {m.total_power_kw:.1f} kW\n"
        f"  Low-pressure nodes ({len(m.low_pressure_nodes)}): {lp_nodes}\n"
        f"  Flow reversals ({len(m.flow_reversals)}): {reversals}\n"
        f"  Bottleneck pipes ({len(m.bottleneck_edges)}): {bottlenecks}\n"
        f"{low_p_details}\n"
        f"PUMP OPERATING POINTS:\n"
        + "\n".join(pump_lines) + "\n\n"
        f"SIMULATION WARNINGS ({len(warnings)}):\n"
        + ("\n".join(warning_lines) if warning_lines else "  None")
    )


@router.post("/{result_id}", response_model=AIAnalysisResponseSchema)
async def analyze_simulation(result_id: str):
    """
    Run AI-powered hydraulic analysis on a stored simulation result.
    Requires GROQ_API_KEY to be set in the environment.
    """
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI analysis is unavailable: GROQ_API_KEY is not configured. "
                "Add it to your .env file (get a free key at https://console.groq.com)."
            ),
        )

    result_data = await result_store.get(result_id)
    if result_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Simulation result '{result_id}' not found or has expired.",
        )

    result = result_data["object"]
    summary = _format_simulation_summary(result)
    logger.info(f"AI analysis requested for result {result_id}")

    try:
        from ...ai.agents import run_analysis_graph
        analysis, recommendations = await run_analysis_graph(summary, groq_api_key)
    except Exception as exc:
        logger.error(f"AI analysis failed for {result_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {exc}")

    return AIAnalysisResponseSchema(
        summary=analysis.summary,
        health_score=max(0, min(100, analysis.health_score)),
        issues=[
            AnalysisIssueSchema(
                category=i.category,
                severity=i.severity,
                component_id=i.component_id,
                description=i.description,
                metric=i.metric,
            )
            for i in analysis.issues
        ],
        recommendations=[
            AnalysisRecommendationSchema(
                title=r.title,
                action=r.action,
                expected_impact=r.expected_impact,
                priority=r.priority,
                component_id=r.component_id,
            )
            for r in recommendations.recommendations
        ],
        overall_strategy=recommendations.overall_strategy,
    )
