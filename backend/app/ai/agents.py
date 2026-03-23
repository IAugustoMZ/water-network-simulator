"""
AI-powered hydraulic network analysis using PydanticAI agents and a LangGraph workflow.

Two-node pipeline:
  [HydraulicAnalyzer] → identifies issues, computes health score
  [RecommendationsGenerator] → produces actionable recommendations

Both nodes use Groq (llama-3.3-70b-versatile) via PydanticAI.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_ai import Agent
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic output models (structured LLM outputs)
# ---------------------------------------------------------------------------

class IssueModel(BaseModel):
    category: str           # pressure | cavitation | efficiency | flow | capacity
    severity: str           # critical | warning | info
    component_id: Optional[str] = None
    description: str
    metric: Optional[str] = None


def _patch_health_score_schema(schema: dict) -> None:
    """Allow health_score to be string or int so Groq's validator accepts both."""
    props = schema.get('properties', {})
    if 'health_score' in props:
        props['health_score'] = {'title': 'Health Score', 'anyOf': [{'type': 'integer'}, {'type': 'string'}]}


class HydraulicAnalysisModel(BaseModel):
    model_config = ConfigDict(json_schema_extra=_patch_health_score_schema)
    issues: list[IssueModel]
    health_score: int       # 0–100
    summary: str

    @field_validator('health_score', mode='before')
    @classmethod
    def coerce_health_score(cls, v: Any) -> int:
        try:
            return int(v)
        except (ValueError, TypeError):
            return 50


def _patch_priority_schema(schema: dict) -> None:
    """Allow priority to be string or int so Groq's tool-call validator accepts both."""
    props = schema.get('properties', {})
    if 'priority' in props:
        props['priority'] = {'title': 'Priority', 'anyOf': [{'type': 'integer'}, {'type': 'string'}], 'default': 3}


class RecommendationModel(BaseModel):
    model_config = ConfigDict(json_schema_extra=_patch_priority_schema)
    title: str
    action: str
    expected_impact: str
    priority: int = 3
    component_id: Optional[str] = None

    @field_validator('priority', mode='before')
    @classmethod
    def coerce_priority(cls, v: Any) -> int:
        """Coerce string priorities (e.g. '1') to int."""
        try:
            return int(v)
        except (ValueError, TypeError):
            return 3  # default to low priority


class RecommendationsModel(BaseModel):
    recommendations: list[RecommendationModel]
    overall_strategy: str


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class AnalysisState(TypedDict):
    simulation_summary: str
    analysis: Optional[Any]        # HydraulicAnalysisModel after node 1
    recommendations: Optional[Any] # RecommendationsModel after node 2


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_ANALYZER_PROMPT = """\
You are a senior hydraulic engineer specializing in water distribution network operation.

Analyze the provided simulation results and identify all hydraulic engineering issues.

For each issue specify:
- category: exactly one of "pressure" | "cavitation" | "efficiency" | "flow" | "capacity"
- severity: "critical" (needs immediate action), "warning" (monitor closely), "info" (informational)
- description: precise technical description; always cite measured values and thresholds
- metric: the key measured value vs target (e.g. "NPSHa 3.1 m < NPSHr 4.8 m")
- component_id: the node / pipe / pump ID if applicable

Also produce:
- summary: 2–3 sentence executive overview of network health
- health_score: integer 0–100 (100 = all within optimal ranges; 0 = critical failure)

Be specific. Use engineering units. Quote exact values from the data.
"""

_RECOMMENDER_PROMPT = """\
You are a senior hydraulic engineer providing optimization recommendations for a water \
distribution network operation team.

Based on the hydraulic analysis, generate specific, actionable, quantified recommendations.

For each recommendation specify:
- title: action-oriented title starting with a verb (Increase / Reduce / Isolate / Replace …)
- action: exact steps with specific values (e.g. "Set PUMP1 speed ratio from 0.80 → 0.95")
- expected_impact: quantified improvement (e.g. "Raises J14 pressure from 5.2 m to ~13 m")
- priority: MUST be the integer 1 (address immediately), 2 (address this week), or 3 (address this quarter) — not a string
- component_id: the primary component to modify

Also provide:
- overall_strategy: 2–3 sentence summary of the key operational priorities

Never give vague advice. Always cite the specific values and components from the analysis.
"""


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def _make_graph(groq_api_key: str) -> Any:
    """Build and compile the LangGraph analysis pipeline."""
    # pydantic-ai reads GROQ_API_KEY from env; set it explicitly if not already present
    if groq_api_key:
        os.environ.setdefault("GROQ_API_KEY", groq_api_key)

    model = "groq:llama-3.3-70b-versatile"

    analyzer: Agent[None, HydraulicAnalysisModel] = Agent(
        model,
        result_type=HydraulicAnalysisModel,
        system_prompt=_ANALYZER_PROMPT,
    )

    recommender: Agent[None, RecommendationsModel] = Agent(
        model,
        result_type=RecommendationsModel,
        system_prompt=_RECOMMENDER_PROMPT,
    )

    async def analyze_node(state: AnalysisState) -> dict:
        logger.info("AI hydraulic-analyzer: running …")
        result = await analyzer.run(state["simulation_summary"])
        return {"analysis": result.data}

    async def recommend_node(state: AnalysisState) -> dict:
        logger.info("AI recommendations-generator: running …")
        analysis: HydraulicAnalysisModel = state["analysis"]
        issues_text = "\n".join(
            f"- [{i.severity.upper()}] ({i.category}) {i.description}"
            + (f"  metric: {i.metric}" if i.metric else "")
            + (f"  component: {i.component_id}" if i.component_id else "")
            for i in analysis.issues
        ) or "No issues found."
        prompt = (
            f"Health score: {analysis.health_score}/100\n"
            f"Summary: {analysis.summary}\n\n"
            f"Issues:\n{issues_text}"
        )
        result = await recommender.run(prompt)
        return {"recommendations": result.data}

    workflow: StateGraph = StateGraph(AnalysisState)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("recommend", recommend_node)
    workflow.add_edge(START, "analyze")
    workflow.add_edge("analyze", "recommend")
    workflow.add_edge("recommend", END)
    return workflow.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_analysis_graph(
    simulation_summary: str,
    groq_api_key: str,
) -> tuple[HydraulicAnalysisModel, RecommendationsModel]:
    graph = _make_graph(groq_api_key)
    state = await graph.ainvoke(
        {
            "simulation_summary": simulation_summary,
            "analysis": None,
            "recommendations": None,
        }
    )
    return state["analysis"], state["recommendations"]
