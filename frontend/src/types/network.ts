export interface NodeResult {
  node_id: string;
  node_type: 'junction' | 'reservoir' | 'tank';
  elevation: number;
  hydraulic_head: number;
  pressure_m: number;
  pressure_kpa: number;
  demand: number;
}

export interface EdgeResult {
  edge_id: string;
  edge_type: 'pipe' | 'pump' | 'valve';
  start_node: string;
  end_node: string;
  flow: number;
  flow_lps: number;
  velocity: number;
  head_loss: number;
  reynolds: number;
  friction_factor: number;
  is_reversed: boolean;
  status: string;
}

export interface PumpResult {
  pump_id: string;
  is_on: boolean;
  flow: number;
  flow_lps: number;
  head: number;
  speed_ratio: number;
  efficiency: number;
  power_kw: number;
  npsha: number;
  npshr: number;
  cavitation_margin: number;
  is_cavitating: boolean;
  status: string;
}

export interface ValveResult {
  valve_id: string;
  valve_type: string;
  flow: number;
  flow_lps: number;
  pressure_drop_m: number;
  opening_fraction: number;
  status: string;
}

export interface TankResult {
  tank_id: string;
  water_level: number;
  hydraulic_head: number;
  outflow: number;
  residence_time: number;
}

export interface SystemMetrics {
  total_demand: number;
  total_supply: number;
  mass_balance_error: number;
  min_pressure_m: number;
  max_pressure_m: number;
  min_pressure_node: string;
  max_pressure_node: string;
  low_pressure_nodes: string[];
  flow_reversals: string[];
  bottleneck_edges: string[];
  system_efficiency: number;
  total_power_kw: number;
}

export interface SimulationWarning {
  code: string;
  message: string;
  component_id?: string;
  severity: 'info' | 'warning' | 'critical';
}

export interface SimulationResult {
  result_id: string;
  network_id: string;
  scenario_name: string;
  status: 'converged' | 'diverged';
  iterations: number;
  residual_norm: number;
  nodes: NodeResult[];
  edges: EdgeResult[];
  pumps: PumpResult[];
  valves: ValveResult[];
  tanks: TankResult[];
  system_metrics: SystemMetrics;
  warnings: SimulationWarning[];
}

export interface SimulationPreview {
  result_id: string;
  status: 'converged' | 'diverged';
  iterations: number;
  residual_norm: number;
  total_demand: number;
  min_pressure_m: number;
  max_pressure_m: number;
  warnings_count: number;
}

export interface PumpOverride {
  is_on?: boolean;
  speed_ratio?: number;
}

export interface ValveOverride {
  opening_fraction?: number;
  setting?: number;
}

export interface ScenarioOverrides {
  pumps: Record<string, PumpOverride>;
  valves: Record<string, ValveOverride>;
  demand_multipliers: Record<string, number>;
  global_demand_multiplier: number;
  tank_levels: Record<string, number>;
}

// For network graph visualization
export interface NodePosition {
  id: string;
  x: number;
  y: number;
  node_type: string;
  elevation: number;
  pressure_m?: number;
  demand?: number;
}

export interface EdgeLink {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  flow_lps?: number;
  velocity?: number;
  status?: string;
}

// Pump curve data for monitoring dashboard
export interface PumpCurvePoint {
  flow_lps: number;
  head: number;
  efficiency: number;
  power_kw: number;
  npsh_required: number;
}

export interface SpeedCurve {
  speed_ratio: number;
  label: string;
  is_current: boolean;
  points: PumpCurvePoint[];
}

export interface EfficiencyContourPoint {
  flow_lps: number;
  head: number;
}

export interface EfficiencyContour {
  efficiency: number;
  label: string;
  points: EfficiencyContourPoint[];
}

export interface PumpCurveData {
  pump_id: string;
  start_node: string;
  end_node: string;
  speed_ratio: number;
  is_on: boolean;
  rated_curve: PumpCurvePoint[];
  current_curve: PumpCurvePoint[];
  speed_curves: SpeedCurve[];
  efficiency_contours: EfficiencyContour[];
}

// AI analysis types
export interface AnalysisIssue {
  category: string;
  severity: 'critical' | 'warning' | 'info';
  component_id?: string;
  description: string;
  metric?: string;
}

export interface AnalysisRecommendation {
  title: string;
  action: string;
  expected_impact: string;
  priority: 1 | 2 | 3;
  component_id?: string;
}

export interface AIAnalysisResult {
  summary: string;
  health_score: number;
  issues: AnalysisIssue[];
  recommendations: AnalysisRecommendation[];
  overall_strategy: string;
}
