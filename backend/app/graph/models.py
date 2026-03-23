"""
Hydraulic network data models.
All units are SI: meters (m), cubic meters per second (m³/s), Pascals (Pa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class NodeType(str, Enum):
    JUNCTION = "junction"
    RESERVOIR = "reservoir"
    TANK = "tank"


class EdgeType(str, Enum):
    PIPE = "pipe"
    PUMP = "pump"
    VALVE = "valve"


class ValveType(str, Enum):
    ISOLATION = "isolation"
    PRV = "prv"   # Pressure Reducing Valve
    FCV = "fcv"   # Flow Control Valve


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

@dataclass
class JunctionNode:
    """Demand node with no fixed head constraint."""
    id: str
    elevation: float          # m above datum
    base_demand: float        # m³/s (positive = consumption)
    node_type: NodeType = field(default=NodeType.JUNCTION, init=False)

    def __post_init__(self):
        self.node_type = NodeType.JUNCTION


@dataclass
class ReservoirNode:
    """Fixed-head boundary node (infinite source/sink)."""
    id: str
    elevation: float          # m (reference elevation)
    total_head: float         # m (fixed hydraulic head, constant)
    node_type: NodeType = field(default=NodeType.RESERVOIR, init=False)

    def __post_init__(self):
        self.node_type = NodeType.RESERVOIR


@dataclass
class TankNode:
    """Variable-head storage node. Head = elevation + water_level."""
    id: str
    elevation: float          # m (base of tank, i.e. invert elevation)
    water_level: float        # m (depth of water currently in tank)
    min_level: float          # m (minimum allowable water depth)
    max_level: float          # m (maximum allowable water depth)
    diameter: float           # m (internal diameter, assumed circular)
    node_type: NodeType = field(default=NodeType.TANK, init=False)

    def __post_init__(self):
        self.node_type = NodeType.TANK

    @property
    def total_head(self) -> float:
        """Hydraulic head at tank: elevation of tank base + water depth."""
        return self.elevation + self.water_level

    @property
    def volume(self) -> float:
        """Current stored volume (m³)."""
        return math.pi * (self.diameter / 2.0) ** 2 * self.water_level


# Union type for type hints
AnyNode = JunctionNode | ReservoirNode | TankNode


# ---------------------------------------------------------------------------
# Pump curve data
# ---------------------------------------------------------------------------

@dataclass
class PumpCurveData:
    """
    Discrete manufacturer pump curve data for PCHIP interpolation.
    All lists must have the same length and be ordered by increasing flow.
    """
    flows: List[float]           # m³/s — operating flow points
    heads: List[float]           # m    — total dynamic head at each flow
    efficiencies: List[float]    # dimensionless [0, 1] — hydraulic efficiency
    npsh_required: List[float]   # m    — NPSHr at each flow point

    def __post_init__(self):
        n = len(self.flows)
        if not (n == len(self.heads) == len(self.efficiencies) == len(self.npsh_required)):
            raise ValueError("All pump curve lists must have the same length.")
        if n < 3:
            raise ValueError("At least 3 curve points required for PCHIP interpolation.")
        if any(self.flows[i] >= self.flows[i + 1] for i in range(n - 1)):
            raise ValueError("Pump curve flows must be strictly increasing.")


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

@dataclass
class Pipe:
    """Pressure conduit. Head loss via Darcy-Weisbach + Colebrook-White."""
    id: str
    start_node: str
    end_node: str
    length: float              # m
    diameter: float            # m (internal)
    roughness: float           # m (absolute roughness ε)
    minor_loss_coeff: float = 0.0   # Σ K for fittings (dimensionless)
    edge_type: EdgeType = field(default=EdgeType.PIPE, init=False)

    def __post_init__(self):
        self.edge_type = EdgeType.PIPE
        if self.length <= 0:
            raise ValueError(f"Pipe {self.id}: length must be positive.")
        if self.diameter <= 0:
            raise ValueError(f"Pipe {self.id}: diameter must be positive.")
        if self.roughness <= 0:
            raise ValueError(f"Pipe {self.id}: roughness must be positive.")

    @property
    def area(self) -> float:
        """Cross-sectional flow area (m²)."""
        return math.pi * (self.diameter / 2.0) ** 2

    @property
    def relative_roughness(self) -> float:
        """ε/D dimensionless."""
        return self.roughness / self.diameter


@dataclass
class Pump:
    """
    Centrifugal pump. Adds head to the flow.
    Supports variable speed via affinity laws.
    Multiple pumps in parallel are modeled as separate edges.
    """
    id: str
    start_node: str           # suction node
    end_node: str             # discharge node
    curve: PumpCurveData
    speed_ratio: float = 1.0          # n/n₀ (1.0 = rated speed)
    is_on: bool = True
    suction_elevation: float = 0.0    # m — elevation of pump centreline (for NPSHa)
    edge_type: EdgeType = field(default=EdgeType.PUMP, init=False)

    def __post_init__(self):
        self.edge_type = EdgeType.PUMP
        if not (0.0 < self.speed_ratio <= 2.0):
            raise ValueError(f"Pump {self.id}: speed_ratio must be in (0, 2].")


@dataclass
class Valve:
    """
    Control or isolation valve using ISA Cv-based formulation.
    Equal-percentage inherent flow characteristic.
    """
    id: str
    start_node: str
    end_node: str
    valve_type: ValveType
    cv_max: float             # US gpm / √psi (manufacturer rating)
    opening_fraction: float = 1.0     # 0 = fully closed, 1 = fully open
    setting: float = 0.0
    # PRV: downstream head setpoint (m)
    # FCV: target flow setpoint (m³/s)
    # ISOLATION: unused
    rangeability: float = 50.0        # R for equal-percentage characteristic
    edge_type: EdgeType = field(default=EdgeType.VALVE, init=False)

    def __post_init__(self):
        self.edge_type = EdgeType.VALVE
        if not (0.0 <= self.opening_fraction <= 1.0):
            raise ValueError(f"Valve {self.id}: opening_fraction must be in [0, 1].")
        if self.cv_max <= 0:
            raise ValueError(f"Valve {self.id}: cv_max must be positive.")


# Union type for type hints
AnyEdge = Pipe | Pump | Valve
