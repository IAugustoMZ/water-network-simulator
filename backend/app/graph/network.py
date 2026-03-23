"""
NetworkGraph: assembles nodes and edges into an indexed graph structure.
Provides incidence matrix, node queries, and topological validation.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix

from .models import (
    AnyEdge, AnyNode, EdgeType, JunctionNode, NodeType, Pipe, Pump,
    ReservoirNode, TankNode, Valve,
)


class NetworkGraph:
    """
    Indexed hydraulic network graph.

    Nodes and edges are stored in insertion order.  Indices are stable for the
    lifetime of the object; never mutate the lists after construction.
    """

    def __init__(self, nodes: List[AnyNode], edges: List[AnyEdge]) -> None:
        if not nodes:
            raise ValueError("Network must contain at least one node.")
        if not edges:
            raise ValueError("Network must contain at least one edge.")

        self._nodes: List[AnyNode] = list(nodes)
        self._edges: List[AnyEdge] = list(edges)

        # Build id → integer index maps
        self._node_index: Dict[str, int] = {n.id: i for i, n in enumerate(self._nodes)}
        self._edge_index: Dict[str, int] = {e.id: i for i, e in enumerate(self._edges)}

        # Validate uniqueness
        if len(self._node_index) != len(self._nodes):
            raise ValueError("Duplicate node IDs detected.")
        if len(self._edge_index) != len(self._edges):
            raise ValueError("Duplicate edge IDs detected.")

        # Validate that every edge references existing nodes
        for edge in self._edges:
            for nid in (edge.start_node, edge.end_node):
                if nid not in self._node_index:
                    raise ValueError(
                        f"Edge '{edge.id}' references unknown node '{nid}'."
                    )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_nodes(self) -> int:
        return len(self._nodes)

    @property
    def n_edges(self) -> int:
        return len(self._edges)

    @property
    def nodes(self) -> List[AnyNode]:
        return self._nodes

    @property
    def edges(self) -> List[AnyEdge]:
        return self._edges

    @property
    def node_index(self) -> Dict[str, int]:
        return self._node_index

    @property
    def edge_index(self) -> Dict[str, int]:
        return self._edge_index

    # ------------------------------------------------------------------
    # Node / edge accessors
    # ------------------------------------------------------------------

    def get_node_by_id(self, node_id: str) -> AnyNode:
        idx = self._node_index.get(node_id)
        if idx is None:
            raise KeyError(f"Node '{node_id}' not found.")
        return self._nodes[idx]

    def get_edge_by_id(self, edge_id: str) -> AnyEdge:
        idx = self._edge_index.get(edge_id)
        if idx is None:
            raise KeyError(f"Edge '{edge_id}' not found.")
        return self._edges[idx]

    # ------------------------------------------------------------------
    # Fixed / free node classification
    # ------------------------------------------------------------------

    def get_fixed_head_nodes(self) -> List[int]:
        """
        Indices of nodes whose hydraulic head is a known boundary condition:
        reservoirs (fixed total head) and tanks (head = elevation + level).
        """
        return [
            i
            for i, n in enumerate(self._nodes)
            if n.node_type in (NodeType.RESERVOIR, NodeType.TANK)
        ]

    def get_free_nodes(self) -> List[int]:
        """
        Indices of junction nodes — the unknowns of the H-equation system.
        """
        return [
            i for i, n in enumerate(self._nodes) if n.node_type == NodeType.JUNCTION
        ]

    def get_fixed_head_values(self) -> np.ndarray:
        """
        Returns a dict mapping fixed-node global index → head value (m).
        """
        result = {}
        for i, node in enumerate(self._nodes):
            if isinstance(node, ReservoirNode):
                result[i] = node.total_head
            elif isinstance(node, TankNode):
                result[i] = node.total_head
        return result

    # ------------------------------------------------------------------
    # Incidence matrix
    # ------------------------------------------------------------------

    def build_incidence_matrix(self) -> csr_matrix:
        """
        Build the node–edge incidence matrix A of shape (n_nodes, n_edges).

        Convention:
          A[i, e] = +1  if edge e *leaves*  node i  (start_node)
          A[i, e] = -1  if edge e *enters* node i  (end_node)
          A[i, e] =  0  otherwise

        With this convention, for a flow vector Q (positive in edge direction):
          nodal_inflows = -A @ Q   (positive = flow entering the node)
          continuity residual: A @ Q - D = 0  (D = demand, positive = consumption)
        """
        A = lil_matrix((self.n_nodes, self.n_edges), dtype=np.float64)
        for e_idx, edge in enumerate(self._edges):
            s = self._node_index[edge.start_node]
            t = self._node_index[edge.end_node]
            A[s, e_idx] = +1.0
            A[t, e_idx] = -1.0
        return A.tocsr()

    # ------------------------------------------------------------------
    # Topological validation
    # ------------------------------------------------------------------

    def topological_validate(self) -> List[str]:
        """
        Check network topology for common modelling errors.

        Returns a list of warning/error strings (empty = all OK).
        Does not raise; callers decide whether warnings are fatal.
        """
        warnings: List[str] = []

        # 1. Must have at least one fixed-head node
        fixed = self.get_fixed_head_nodes()
        if not fixed:
            warnings.append(
                "CRITICAL: No reservoir or tank node found. "
                "The system has no fixed-head boundary — it is ill-posed."
            )

        # 2. All nodes must be reachable from a fixed-head node (connectivity check)
        if fixed:
            reachable = self._bfs_reachable(fixed[0])
            for i, node in enumerate(self._nodes):
                if i not in reachable:
                    warnings.append(
                        f"WARNING: Node '{node.id}' is not connected to the "
                        "main network (isolated)."
                    )

        # 3. Detect self-loops
        for edge in self._edges:
            if edge.start_node == edge.end_node:
                warnings.append(
                    f"WARNING: Edge '{edge.id}' is a self-loop "
                    f"(start == end == '{edge.start_node}')."
                )

        # 4. Detect nodes with no connected edges (dangling)
        connected_nodes: set = set()
        for edge in self._edges:
            connected_nodes.add(edge.start_node)
            connected_nodes.add(edge.end_node)
        for node in self._nodes:
            if node.id not in connected_nodes:
                warnings.append(
                    f"WARNING: Node '{node.id}' has no connected edges (dangling)."
                )

        # 5. Junction nodes must have non-negative demand
        for node in self._nodes:
            if isinstance(node, JunctionNode) and node.base_demand < 0:
                warnings.append(
                    f"INFO: Junction '{node.id}' has negative demand "
                    f"({node.base_demand:.4f} m³/s) — treated as local source."
                )

        # 6. Pipes: sanity check on diameter and roughness
        for edge in self._edges:
            if edge.edge_type.value == "pipe":
                pipe: Pipe = edge  # type: ignore[assignment]
                if pipe.diameter < 0.01:
                    warnings.append(
                        f"WARNING: Pipe '{pipe.id}' diameter {pipe.diameter*1000:.1f} mm "
                        "is very small (< 10 mm). Check units."
                    )
                if pipe.roughness > pipe.diameter * 0.1:
                    warnings.append(
                        f"WARNING: Pipe '{pipe.id}' relative roughness "
                        f"{pipe.relative_roughness:.3f} > 0.1 — extremely rough pipe."
                    )

        return warnings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bfs_reachable(self, start_node_idx: int) -> set:
        """BFS on undirected adjacency (ignoring flow direction)."""
        # Build undirected adjacency list
        adj: Dict[int, List[int]] = {i: [] for i in range(self.n_nodes)}
        for edge in self._edges:
            s = self._node_index[edge.start_node]
            t = self._node_index[edge.end_node]
            adj[s].append(t)
            adj[t].append(s)

        visited = set()
        queue = [start_node_idx]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(adj[current])
        return visited
