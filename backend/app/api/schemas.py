"""
Pydantic v2 request/response schemas for all API endpoints.
"""
from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (string literals for Pydantic discriminators)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Node schemas
# ---------------------------------------------------------------------------

class JunctionNodeSchema(BaseModel):
    id: str
    node_type: Literal["junction"]
    elevation: float = Field(..., ge=-100.0, le=5000.0, description="m above datum")
    base_demand: float = Field(..., ge=0.0, description="m³/s")


class ReservoirNodeSchema(BaseModel):
    id: str
    node_type: Literal["reservoir"]
    elevation: float = Field(..., description="Reference elevation (m)")
    total_head: float = Field(..., description="Fixed hydraulic head (m)")


class TankNodeSchema(BaseModel):
    id: str
    node_type: Literal["tank"]
    elevation: float
    water_level: float = Field(..., ge=0.0)
    min_level: float = Field(..., ge=0.0)
    max_level: float
    diameter: float = Field(..., gt=0.0)


NodeSchema = Annotated[
    Union[JunctionNodeSchema, ReservoirNodeSchema, TankNodeSchema],
    Field(discriminator="node_type"),
]


# ---------------------------------------------------------------------------
# Edge schemas
# ---------------------------------------------------------------------------

class PipeSchema(BaseModel):
    id: str
    edge_type: Literal["pipe"]
    start_node: str
    end_node: str
    length: float = Field(..., gt=0.0, description="m")
    diameter: float = Field(..., gt=0.0, description="m")
    roughness: float = Field(..., gt=0.0, description="m (absolute roughness)")
    minor_loss_coeff: float = Field(default=0.0, ge=0.0)


class PumpCurveDataSchema(BaseModel):
    flows: List[float]
    heads: List[float]
    efficiencies: List[float]
    npsh_required: List[float]


class PumpSchema(BaseModel):
    id: str
    edge_type: Literal["pump"]
    start_node: str
    end_node: str
    curve: PumpCurveDataSchema
    speed_ratio: float = Field(default=1.0, ge=0.1, le=1.5)
    is_on: bool = True
    suction_elevation: float = 0.0


class ValveSchema(BaseModel):
    id: str
    edge_type: Literal["valve"]
    start_node: str
    end_node: str
    valve_type: Literal["isolation", "prv", "fcv"]
    cv_max: float = Field(..., gt=0.0, description="US gpm/√psi")
    opening_fraction: float = Field(default=1.0, ge=0.0, le=1.0)
    setting: float = Field(default=0.0)
    rangeability: float = Field(default=50.0, gt=1.0)


EdgeSchema = Annotated[
    Union[PipeSchema, PumpSchema, ValveSchema],
    Field(discriminator="edge_type"),
]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class NetworkDefinitionRequest(BaseModel):
    nodes: List[NodeSchema]
    edges: List[EdgeSchema]


class PumpOverride(BaseModel):
    is_on: Optional[bool] = None
    speed_ratio: Optional[float] = Field(default=None, ge=0.1, le=1.5)


class ValveOverride(BaseModel):
    opening_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    setting: Optional[float] = None


class ScenarioOverrides(BaseModel):
    pumps: Dict[str, PumpOverride] = Field(default_factory=dict)
    valves: Dict[str, ValveOverride] = Field(default_factory=dict)
    demand_multipliers: Dict[str, float] = Field(default_factory=dict)
    global_demand_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    tank_levels: Dict[str, float] = Field(default_factory=dict)


class SimulationRequest(BaseModel):
    network_id: str
    scenario_name: Optional[str] = None
    overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class NetworkCreatedResponse(BaseModel):
    network_id: str
    node_count: int
    edge_count: int
    validation_warnings: List[str]


class NodeResultSchema(BaseModel):
    node_id: str
    node_type: str
    elevation: float
    hydraulic_head: float
    pressure_m: float
    pressure_kpa: float
    demand: float


class EdgeResultSchema(BaseModel):
    edge_id: str
    edge_type: str
    start_node: str
    end_node: str
    flow: float
    flow_lps: float
    velocity: float
    head_loss: float
    reynolds: float
    friction_factor: float
    is_reversed: bool
    status: str


class PumpResultSchema(BaseModel):
    pump_id: str
    is_on: bool
    flow: float
    flow_lps: float
    head: float
    speed_ratio: float
    efficiency: float
    power_kw: float
    npsha: float
    npshr: float
    cavitation_margin: float
    is_cavitating: bool
    status: str


class ValveResultSchema(BaseModel):
    valve_id: str
    valve_type: str
    flow: float
    flow_lps: float
    pressure_drop_m: float
    opening_fraction: float
    status: str


class TankResultSchema(BaseModel):
    tank_id: str
    water_level: float
    hydraulic_head: float
    outflow: float
    residence_time: float


class SystemMetricsSchema(BaseModel):
    total_demand: float
    total_supply: float
    mass_balance_error: float
    min_pressure_m: float
    max_pressure_m: float
    min_pressure_node: str
    max_pressure_node: str
    low_pressure_nodes: List[str]
    flow_reversals: List[str]
    bottleneck_edges: List[str]
    system_efficiency: float
    total_power_kw: float


class SimulationWarningSchema(BaseModel):
    code: str
    message: str
    component_id: Optional[str] = None
    severity: Literal["info", "warning", "critical"]


class SimulationResultSchema(BaseModel):
    result_id: str
    network_id: str
    scenario_name: str
    status: Literal["converged", "diverged"]
    iterations: int
    residual_norm: float
    nodes: List[NodeResultSchema]
    edges: List[EdgeResultSchema]
    pumps: List[PumpResultSchema]
    valves: List[ValveResultSchema]
    tanks: List[TankResultSchema]
    system_metrics: SystemMetricsSchema
    warnings: List[SimulationWarningSchema]


class SimulationPreviewResponse(BaseModel):
    result_id: str
    status: Literal["converged", "diverged"]
    iterations: int
    residual_norm: float
    total_demand: float
    min_pressure_m: float
    max_pressure_m: float
    warnings_count: int


# ---------------------------------------------------------------------------
# Pump curve data response
# ---------------------------------------------------------------------------

class PumpCurvePointSchema(BaseModel):
    flow_lps: float
    head: float
    efficiency: float
    power_kw: float
    npsh_required: float


class SpeedCurveSchema(BaseModel):
    speed_ratio: float
    label: str
    is_current: bool
    points: List[PumpCurvePointSchema]


class EfficiencyContourPointSchema(BaseModel):
    flow_lps: float
    head: float


class EfficiencyContourSchema(BaseModel):
    efficiency: float
    label: str
    points: List[EfficiencyContourPointSchema]


class PumpCurveResponseSchema(BaseModel):
    pump_id: str
    start_node: str
    end_node: str
    speed_ratio: float
    is_on: bool
    # Detail charts (single speed)
    rated_curve: List[PumpCurvePointSchema]
    current_curve: List[PumpCurvePointSchema]
    # Vendor-style chart data
    speed_curves: List[SpeedCurveSchema]
    efficiency_contours: List[EfficiencyContourSchema]


# ---------------------------------------------------------------------------
# AI Analysis response
# ---------------------------------------------------------------------------

class AnalysisIssueSchema(BaseModel):
    category: str  # pressure | cavitation | efficiency | flow | capacity
    severity: Literal["critical", "warning", "info"]
    component_id: Optional[str] = None
    description: str
    metric: Optional[str] = None


class AnalysisRecommendationSchema(BaseModel):
    title: str
    action: str
    expected_impact: str
    priority: int  # 1=high, 2=medium, 3=low
    component_id: Optional[str] = None


class AIAnalysisResponseSchema(BaseModel):
    summary: str
    health_score: int  # 0–100
    issues: List[AnalysisIssueSchema]
    recommendations: List[AnalysisRecommendationSchema]
    overall_strategy: str
