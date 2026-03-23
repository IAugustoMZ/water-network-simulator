"""
Realistic small-city water distribution network definition.

Network summary:
  - 62 nodes: 1 reservoir, 1 elevated tank, 60 junction nodes
  - 2 pump station internal nodes (PS_IN, PS_OUT)
  - 97 pipes + 4 pumps + 25 valves = 126 edges
  - Topography: 0–80 m elevation (valley, plateau, two hills)
  - Total demand: ~380 L/s
  - Main pumping station: 3 parallel centrifugal pumps
  - Booster pump for high-elevation zone (J51–J60)
  - 25 valves: 15 isolation, 6 PRV, 4 FCV
  - One aged pipe with high roughness (P_aged)

Coordinate layout (approximate, for visualisation only):
  Ring main nodes J01–J10 form a central loop.
  North residential district: J11–J30
  South commercial/industrial district: J31–J50
  Hill zone: J51–J60
"""
from __future__ import annotations

import copy
from typing import Dict, List, Tuple

from ..graph.models import (
    JunctionNode, ReservoirNode, TankNode,
    Pipe, Pump, Valve,
    PumpCurveData, ValveType,
    AnyNode, AnyEdge,
)
from ..physics.pump import PumpInterpolator

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
G = 9.81

# ---------------------------------------------------------------------------
# Pump curve data
# ---------------------------------------------------------------------------

# Main pumping station: KSB Multitec-style centrifugal pump
# 5-point curve: shutoff → 4 intermediate → runout
_MAIN_PUMP_CURVE = PumpCurveData(
    flows=      [0.000, 0.020, 0.035, 0.045, 0.060, 0.075, 0.085],   # m³/s
    heads=      [65.0,  62.0,  58.0,  52.0,  43.0,  35.0,  28.0],    # m
    efficiencies=[0.0,  0.62,  0.76,  0.82,  0.80,  0.72,  0.60],    # -
    npsh_required=[1.5,  1.8,   2.1,   2.5,   3.5,   5.5,   8.0],    # m
)

# Booster pump: smaller pump for hill zone
_BOOST_PUMP_CURVE = PumpCurveData(
    flows=      [0.000, 0.005, 0.010, 0.015, 0.020, 0.025, 0.028],   # m³/s
    heads=      [35.0,  33.0,  31.0,  28.0,  22.0,  15.0,  12.0],    # m
    efficiencies=[0.0,  0.55,  0.68,  0.76,  0.74,  0.65,  0.55],    # -
    npsh_required=[1.0,  1.2,   1.4,   1.7,   2.5,   4.0,   5.5],    # m
)


def _build_pump_interpolators() -> Dict[str, PumpInterpolator]:
    return {
        "PUMP1": PumpInterpolator(_MAIN_PUMP_CURVE),
        "PUMP2": PumpInterpolator(_MAIN_PUMP_CURVE),
        "PUMP3": PumpInterpolator(_MAIN_PUMP_CURVE),
        "BOOST1": PumpInterpolator(_BOOST_PUMP_CURVE),
    }


# ---------------------------------------------------------------------------
# Network definition
# ---------------------------------------------------------------------------

def _build_nodes() -> List[AnyNode]:
    """Build all network nodes with realistic elevations."""
    nodes: List[AnyNode] = [
        # ----------------------------------------------------------------
        # Reservoir (source)
        # ----------------------------------------------------------------
        ReservoirNode(id="R1", elevation=55.0, total_head=75.0),

        # ----------------------------------------------------------------
        # Elevated tank
        # ----------------------------------------------------------------
        TankNode(id="T1", elevation=68.0, water_level=4.5,
                 min_level=1.0, max_level=7.0, diameter=14.0),

        # ----------------------------------------------------------------
        # Pump station internal nodes
        # ----------------------------------------------------------------
        JunctionNode(id="PS_IN",  elevation=2.0, base_demand=0.0),
        JunctionNode(id="PS_OUT", elevation=2.5, base_demand=0.0),

        # ----------------------------------------------------------------
        # Ring main nodes (J01–J10) — central trunk, elevation 5–20 m
        # ----------------------------------------------------------------
        JunctionNode(id="J01", elevation=5.0,  base_demand=0.003),
        JunctionNode(id="J02", elevation=8.0,  base_demand=0.004),
        JunctionNode(id="J03", elevation=12.0, base_demand=0.003),
        JunctionNode(id="J04", elevation=15.0, base_demand=0.004),
        JunctionNode(id="J05", elevation=18.0, base_demand=0.003),
        JunctionNode(id="J06", elevation=20.0, base_demand=0.004),
        JunctionNode(id="J07", elevation=16.0, base_demand=0.003),
        JunctionNode(id="J08", elevation=12.0, base_demand=0.003),
        JunctionNode(id="J09", elevation=8.0,  base_demand=0.004),
        JunctionNode(id="J10", elevation=5.0,  base_demand=0.003),

        # ----------------------------------------------------------------
        # North residential district (J11–J30) — elevation 20–45 m
        # Medium demand (residential)
        # ----------------------------------------------------------------
        JunctionNode(id="J11", elevation=22.0, base_demand=0.002),
        JunctionNode(id="J12", elevation=25.0, base_demand=0.002),
        JunctionNode(id="J13", elevation=28.0, base_demand=0.002),
        JunctionNode(id="J14", elevation=30.0, base_demand=0.002),
        JunctionNode(id="J15", elevation=32.0, base_demand=0.002),
        JunctionNode(id="J16", elevation=35.0, base_demand=0.001),
        JunctionNode(id="J17", elevation=38.0, base_demand=0.001),
        JunctionNode(id="J18", elevation=40.0, base_demand=0.001),
        JunctionNode(id="J19", elevation=42.0, base_demand=0.001),
        JunctionNode(id="J20", elevation=44.0, base_demand=0.001),
        JunctionNode(id="J21", elevation=25.0, base_demand=0.002),
        JunctionNode(id="J22", elevation=27.0, base_demand=0.002),
        JunctionNode(id="J23", elevation=30.0, base_demand=0.002),
        JunctionNode(id="J24", elevation=33.0, base_demand=0.001),
        JunctionNode(id="J25", elevation=36.0, base_demand=0.001),
        JunctionNode(id="J26", elevation=23.0, base_demand=0.002),
        JunctionNode(id="J27", elevation=26.0, base_demand=0.002),
        JunctionNode(id="J28", elevation=29.0, base_demand=0.002),
        JunctionNode(id="J29", elevation=32.0, base_demand=0.001),
        JunctionNode(id="J30", elevation=35.0, base_demand=0.001),

        # ----------------------------------------------------------------
        # South commercial/industrial district (J31–J50) — elevation 3–30 m
        # Higher demand (commercial)
        # ----------------------------------------------------------------
        JunctionNode(id="J31", elevation=8.0,  base_demand=0.006),
        JunctionNode(id="J32", elevation=6.0,  base_demand=0.007),
        JunctionNode(id="J33", elevation=5.0,  base_demand=0.008),
        JunctionNode(id="J34", elevation=7.0,  base_demand=0.006),
        JunctionNode(id="J35", elevation=10.0, base_demand=0.005),
        JunctionNode(id="J36", elevation=12.0, base_demand=0.004),
        JunctionNode(id="J37", elevation=15.0, base_demand=0.003),
        JunctionNode(id="J38", elevation=18.0, base_demand=0.004),
        JunctionNode(id="J39", elevation=20.0, base_demand=0.003),
        JunctionNode(id="J40", elevation=22.0, base_demand=0.003),
        JunctionNode(id="J41", elevation=6.0,  base_demand=0.007),
        JunctionNode(id="J42", elevation=4.0,  base_demand=0.008),
        JunctionNode(id="J43", elevation=3.0,  base_demand=0.007),
        JunctionNode(id="J44", elevation=5.0,  base_demand=0.005),
        JunctionNode(id="J45", elevation=8.0,  base_demand=0.004),  # booster suction
        JunctionNode(id="J46", elevation=10.0, base_demand=0.003),  # booster discharge
        JunctionNode(id="J47", elevation=14.0, base_demand=0.003),
        JunctionNode(id="J48", elevation=17.0, base_demand=0.002),
        JunctionNode(id="J49", elevation=20.0, base_demand=0.002),
        JunctionNode(id="J50", elevation=25.0, base_demand=0.002),

        # ----------------------------------------------------------------
        # High-elevation hill zone (J51–J60) — elevation 50–80 m
        # Low demand but pressure-critical
        # ----------------------------------------------------------------
        JunctionNode(id="J51", elevation=50.0, base_demand=0.002),
        JunctionNode(id="J52", elevation=55.0, base_demand=0.002),
        JunctionNode(id="J53", elevation=58.0, base_demand=0.002),
        JunctionNode(id="J54", elevation=62.0, base_demand=0.001),
        JunctionNode(id="J55", elevation=65.0, base_demand=0.001),
        JunctionNode(id="J56", elevation=68.0, base_demand=0.001),
        JunctionNode(id="J57", elevation=72.0, base_demand=0.001),
        JunctionNode(id="J58", elevation=75.0, base_demand=0.001),
        JunctionNode(id="J59", elevation=78.0, base_demand=0.001),
        JunctionNode(id="J60", elevation=80.0, base_demand=0.001),
    ]
    return nodes


def _build_pipes() -> List[Pipe]:
    """Build all pipe edges with realistic diameters, lengths, roughness."""

    # Pipe helper: diameter in mm → m, roughness in mm → m
    def P(pid, s, e, D_mm, L, eps_mm=0.05, K=0.0):
        return Pipe(id=pid, start_node=s, end_node=e,
                    length=L, diameter=D_mm / 1000.0,
                    roughness=eps_mm / 1000.0, minor_loss_coeff=K)

    pipes = [
        # ----------------------------------------------------------------
        # Trunk: reservoir → pump station → ring main
        # ----------------------------------------------------------------
        P("P_R1_PS",   "R1",    "PS_IN",  500, 250.0, 0.05),
        P("P_PS_J01",  "PS_OUT","J01",    400, 200.0, 0.05),
        P("P_J01_J10", "J01",   "J10",    400, 350.0, 0.05),
        P("P_T1_J05",  "T1",    "J05",    300, 180.0, 0.05),

        # ----------------------------------------------------------------
        # Ring main (J01–J10): trunk loop
        # ----------------------------------------------------------------
        P("P01",  "J01", "J02", 350, 400.0, 0.05),
        P("P02",  "J02", "J03", 350, 380.0, 0.05),
        P("P03",  "J03", "J04", 300, 420.0, 0.05),
        P("P04",  "J04", "J05", 300, 350.0, 0.05),
        P("P05",  "J05", "J06", 250, 300.0, 0.08),
        P("P06",  "J06", "J07", 250, 320.0, 0.08),
        P("P07",  "J07", "J08", 300, 280.0, 0.05),
        P("P08",  "J08", "J09", 300, 360.0, 0.05),
        P("P09",  "J09", "J10", 350, 400.0, 0.05),
        P("P10",  "J10", "J01", 350, 380.0, 0.05),   # closes ring

        # Cross-connections inside ring
        P("P11",  "J02", "J09", 250, 500.0, 0.08),
        P("P12",  "J04", "J07", 200, 450.0, 0.10),
        P("P13",  "J03", "J08", 200, 480.0, 0.10),

        # ----------------------------------------------------------------
        # North residential district feeders (from ring J04–J07)
        # ----------------------------------------------------------------
        P("P14",  "J04", "J11", 250, 350.0, 0.10),
        P("P15",  "J11", "J12", 200, 280.0, 0.10),
        P("P16",  "J12", "J13", 200, 300.0, 0.10),
        P("P17",  "J13", "J14", 200, 320.0, 0.10),
        P("P18",  "J14", "J15", 150, 280.0, 0.15),
        P("P19",  "J15", "J16", 150, 300.0, 0.15),
        P("P20",  "J16", "J17", 150, 320.0, 0.15),
        P("P21",  "J17", "J18", 125, 250.0, 0.20),
        P("P22",  "J18", "J19", 125, 260.0, 0.20),
        P("P23",  "J19", "J20", 100, 200.0, 0.20),

        P("P24",  "J05", "J21", 200, 350.0, 0.10),
        P("P25",  "J21", "J22", 200, 280.0, 0.10),
        P("P26",  "J22", "J23", 150, 300.0, 0.15),
        P("P27",  "J23", "J24", 150, 320.0, 0.15),
        P("P28",  "J24", "J25", 125, 280.0, 0.20),

        P("P29",  "J06", "J26", 200, 320.0, 0.10),
        P("P30",  "J26", "J27", 200, 280.0, 0.10),
        P("P31",  "J27", "J28", 150, 300.0, 0.15),
        P("P32",  "J28", "J29", 150, 320.0, 0.15),
        P("P33",  "J29", "J30", 125, 280.0, 0.20),

        # North district cross-connections (creates loops)
        P("P34",  "J12", "J21", 150, 400.0, 0.15),
        P("P35",  "J14", "J22", 150, 380.0, 0.15),
        P("P36",  "J16", "J24", 125, 350.0, 0.20),
        P("P37",  "J21", "J26", 200, 300.0, 0.10),
        P("P38",  "J23", "J28", 150, 320.0, 0.15),

        # ----------------------------------------------------------------
        # South commercial district feeders (from ring J01–J03, J08–J10)
        # ----------------------------------------------------------------
        P("P39",  "J01", "J31", 300, 300.0, 0.08),
        P("P40",  "J31", "J32", 250, 260.0, 0.08),
        P("P41",  "J32", "J33", 250, 280.0, 0.08),
        P("P42",  "J33", "J34", 200, 300.0, 0.10),
        P("P43",  "J34", "J35", 200, 280.0, 0.10),
        P("P44",  "J35", "J36", 200, 300.0, 0.10),
        P("P45",  "J36", "J37", 150, 280.0, 0.15),
        P("P46",  "J37", "J38", 150, 300.0, 0.15),
        P("P47",  "J38", "J39", 150, 280.0, 0.15),
        P("P48",  "J39", "J40", 125, 250.0, 0.20),

        P("P49",  "J10", "J41", 250, 280.0, 0.08),
        P("P50",  "J41", "J42", 250, 260.0, 0.08),
        P("P51",  "J42", "J43", 200, 280.0, 0.10),
        P("P52",  "J43", "J44", 200, 300.0, 0.10),
        P("P53",  "J44", "J45", 200, 280.0, 0.10),

        # Aged pipe (high roughness — fouled cement lining)
        P("P_aged","J09","J44", 150, 650.0, 2.0, 0.5),   # eps=2.0mm, K=0.5

        # South district cross-connections
        P("P54",  "J31", "J41", 250, 300.0, 0.08),
        P("P55",  "J32", "J42", 200, 320.0, 0.10),
        P("P56",  "J33", "J43", 200, 300.0, 0.10),
        P("P57",  "J35", "J38", 150, 400.0, 0.15),
        P("P58",  "J36", "J39", 150, 380.0, 0.15),

        # ----------------------------------------------------------------
        # Booster pump connections and hill zone pipes (J46–J60)
        # ----------------------------------------------------------------
        # J45 → (booster) → J46 handled as pump edge BOOST1
        P("P59",  "J46", "J47", 150, 300.0, 0.15),
        P("P60",  "J47", "J48", 125, 280.0, 0.20),
        P("P61",  "J48", "J49", 125, 300.0, 0.20),
        P("P62",  "J49", "J50", 100, 280.0, 0.20),

        P("P63",  "J46", "J51", 150, 350.0, 0.15),
        P("P64",  "J51", "J52", 125, 300.0, 0.20),
        P("P65",  "J52", "J53", 125, 280.0, 0.20),
        P("P66",  "J53", "J54", 100, 300.0, 0.20),
        P("P67",  "J54", "J55", 100, 280.0, 0.20),
        P("P68",  "J55", "J56", 100, 300.0, 0.20),
        P("P69",  "J56", "J57", 100, 280.0, 0.20),
        P("P70",  "J57", "J58", 100, 300.0, 0.20),
        P("P71",  "J58", "J59", 100, 280.0, 0.20),
        P("P72",  "J59", "J60", 100, 300.0, 0.20),

        # Hill zone loop
        P("P73",  "J51", "J55", 100, 500.0, 0.20),
        P("P74",  "J53", "J57", 100, 480.0, 0.20),

        # Connection south district to hill zone feeder
        P("P75",  "J47", "J51", 125, 350.0, 0.15),
        P("P76",  "J48", "J53", 100, 380.0, 0.20),

        # Tank feeds ring main
        P("P_T1_J06", "T1", "J06", 300, 220.0, 0.05),
    ]
    return pipes


def _build_pumps() -> List[Pump]:
    """3 parallel main pumps + 1 booster pump."""
    return [
        Pump(id="PUMP1", start_node="PS_IN", end_node="PS_OUT",
             curve=_MAIN_PUMP_CURVE, speed_ratio=1.0, is_on=True, suction_elevation=2.0),
        Pump(id="PUMP2", start_node="PS_IN", end_node="PS_OUT",
             curve=_MAIN_PUMP_CURVE, speed_ratio=1.0, is_on=True, suction_elevation=2.0),
        Pump(id="PUMP3", start_node="PS_IN", end_node="PS_OUT",
             curve=_MAIN_PUMP_CURVE, speed_ratio=1.0, is_on=True, suction_elevation=2.0),
        Pump(id="BOOST1", start_node="J45", end_node="J46",
             curve=_BOOST_PUMP_CURVE, speed_ratio=1.0, is_on=True, suction_elevation=8.0),
    ]


def _build_valves() -> List[Valve]:
    """
    25 valves:
      15 isolation valves (default: fully open)
       6 PRV (pressure reducing valves at zone boundaries)
       4 FCV (flow control valves on main branches)
    """
    def ISO(vid, s, e, cv=5000.0):
        return Valve(id=vid, start_node=s, end_node=e,
                     valve_type=ValveType.ISOLATION, cv_max=cv,
                     opening_fraction=1.0, setting=0.0)

    def PRV(vid, s, e, setpoint_m, cv=2000.0):
        return Valve(id=vid, start_node=s, end_node=e,
                     valve_type=ValveType.PRV, cv_max=cv,
                     opening_fraction=1.0, setting=setpoint_m)

    def FCV(vid, s, e, flow_m3s, cv=3000.0):
        return Valve(id=vid, start_node=s, end_node=e,
                     valve_type=ValveType.FCV, cv_max=cv,
                     opening_fraction=1.0, setting=flow_m3s)

    return [
        # Isolation valves at key intersections
        ISO("ISO01", "J02", "J11"),
        ISO("ISO02", "J05", "J12"),
        ISO("ISO03", "J07", "J14"),
        ISO("ISO04", "J08", "J31"),
        ISO("ISO05", "J09", "J32"),
        ISO("ISO06", "J03", "J34"),
        ISO("ISO07", "J02", "J35"),
        ISO("ISO08", "J22", "J27"),
        ISO("ISO09", "J36", "J39"),
        ISO("ISO10", "J40", "J50"),
        ISO("ISO11", "J44", "J48"),
        ISO("ISO12", "J49", "J56"),
        ISO("ISO13", "J15", "J20"),
        ISO("ISO14", "J25", "J30"),
        ISO("ISO15", "J38", "J44"),

        # PRVs at zone boundaries (setpoints in metres of head)
        PRV("PRV01", "J11", "J16",  setpoint_m=45.0),  # North zone high-pressure limit
        PRV("PRV02", "J21", "J25",  setpoint_m=42.0),  # North-mid zone
        PRV("PRV03", "J31", "J36",  setpoint_m=55.0),  # South zone (low elevation)
        PRV("PRV04", "J41", "J44",  setpoint_m=52.0),  # South-industrial
        PRV("PRV05", "J46", "J53",  setpoint_m=30.0),  # Hill zone entry
        PRV("PRV06", "J26", "J29",  setpoint_m=40.0),  # North-west zone

        # FCVs on main distribution branches
        FCV("FCV01", "J03", "J13",  flow_m3s=0.020),   # North feeder A
        FCV("FCV02", "J08", "J37",  flow_m3s=0.025),   # South feeder A
        FCV("FCV03", "J07", "J47",  flow_m3s=0.015),   # Hill zone feeder
        FCV("FCV04", "J02", "J26",  flow_m3s=0.018),   # North-west feeder
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_city_network() -> Tuple[
    List[AnyNode], List[AnyEdge], Dict[str, float], Dict[str, PumpInterpolator]
]:
    """
    Build the complete city network.

    Returns
    -------
    nodes : list of AnyNode
    edges : list of AnyEdge  (pipes + pumps + valves)
    demands : dict  node_id → demand (m³/s)  for all junction nodes
    pump_interpolators : dict  pump_id → PumpInterpolator
    """
    nodes = _build_nodes()
    pipes = _build_pipes()
    pumps = _build_pumps()
    valves = _build_valves()
    edges: List[AnyEdge] = pipes + pumps + valves  # type: ignore[assignment]

    demands = {
        node.id: node.base_demand
        for node in nodes
        if hasattr(node, "base_demand")
    }

    pump_interpolators = _build_pump_interpolators()

    return nodes, edges, demands, pump_interpolators


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, Dict] = {
    "baseline": {
        "description": "Normal operation — all pumps on, all valves fully open.",
        "pump_overrides": {},
        "valve_overrides": {},
        "demand_multipliers": {},
        "global_demand_multiplier": 1.0,
    },
    "valve_restriction": {
        "description": "Close 3 strategic isolation valves to test flow redistribution.",
        "pump_overrides": {},
        "valve_overrides": {
            "ISO04": {"opening_fraction": 0.0},
            "ISO07": {"opening_fraction": 0.0},
            "ISO12": {"opening_fraction": 0.0},
        },
        "demand_multipliers": {},
        "global_demand_multiplier": 1.0,
    },
    "pump_speed_reduction": {
        "description": "Main pumps operating at 80% speed (affinity law scaling).",
        "pump_overrides": {
            "PUMP1": {"speed_ratio": 0.80},
            "PUMP2": {"speed_ratio": 0.80},
            "PUMP3": {"speed_ratio": 0.80},
        },
        "valve_overrides": {},
        "demand_multipliers": {},
        "global_demand_multiplier": 1.0,
    },
    "pump_failure": {
        "description": "PUMP1 fails — 2 of 3 parallel pumps remain online.",
        "pump_overrides": {
            "PUMP1": {"is_on": False},
        },
        "valve_overrides": {},
        "demand_multipliers": {},
        "global_demand_multiplier": 1.0,
    },
    "demand_increase": {
        "description": "Peak demand scenario — all demands increased by 20%.",
        "pump_overrides": {},
        "valve_overrides": {},
        "demand_multipliers": {},
        "global_demand_multiplier": 1.2,
    },
    "high_elevation_stress": {
        "description": (
            "Booster pump offline + 50% demand surge in hill zone. "
            "Tests low-pressure risk in J51–J60."
        ),
        "pump_overrides": {
            "BOOST1": {"is_on": False},
        },
        "valve_overrides": {},
        "demand_multipliers": {
            "J51": 1.5, "J52": 1.5, "J53": 1.5,
            "J54": 1.5, "J55": 1.5, "J56": 1.5,
            "J57": 1.5, "J58": 1.5, "J59": 1.5, "J60": 1.5,
        },
        "global_demand_multiplier": 1.0,
    },
}


def apply_scenario(
    nodes: List[AnyNode],
    edges: List[AnyEdge],
    demands: Dict[str, float],
    scenario_name: str,
) -> Tuple[List[AnyNode], List[AnyEdge], Dict[str, float]]:
    """
    Apply a named scenario to deep copies of the network objects.

    Returns modified (nodes_copy, edges_copy, demands_copy).
    Does NOT modify the originals.
    """
    if scenario_name not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. "
            f"Available: {list(SCENARIOS.keys())}"
        )

    scenario = SCENARIOS[scenario_name]
    nodes_copy = copy.deepcopy(nodes)
    edges_copy = copy.deepcopy(edges)
    demands_copy = copy.deepcopy(demands)

    pump_overrides: Dict = scenario.get("pump_overrides", {})
    valve_overrides: Dict = scenario.get("valve_overrides", {})
    demand_multipliers: Dict = scenario.get("demand_multipliers", {})
    global_mult: float = scenario.get("global_demand_multiplier", 1.0)

    # Apply pump overrides
    for edge in edges_copy:
        if edge.edge_type.value == "pump" and edge.id in pump_overrides:
            ov = pump_overrides[edge.id]
            if "is_on" in ov:
                edge.is_on = ov["is_on"]
            if "speed_ratio" in ov:
                edge.speed_ratio = ov["speed_ratio"]

    # Apply valve overrides
    for edge in edges_copy:
        if edge.edge_type.value == "valve" and edge.id in valve_overrides:
            ov = valve_overrides[edge.id]
            if "opening_fraction" in ov:
                edge.opening_fraction = ov["opening_fraction"]
            if "setting" in ov:
                edge.setting = ov["setting"]

    # Apply demand multipliers
    for node_id, mult in demand_multipliers.items():
        if node_id in demands_copy:
            demands_copy[node_id] *= mult

    # Apply global multiplier
    if global_mult != 1.0:
        demands_copy = {k: v * global_mult for k, v in demands_copy.items()}

    return nodes_copy, edges_copy, demands_copy
