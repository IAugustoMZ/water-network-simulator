"""
Sparse analytical Jacobian for the H-equation system.

J[i, j] = dF_i / dH_j   (free nodes only)

For each edge e connecting nodes s (start) and t (end):
  Q_e depends on ΔH = H_s - H_t  via the physics model.
  dQ_e/dH_s = +dQ_e/dΔH = +1 / (dh_e/dQ_e)
  dQ_e/dH_t = -dQ_e/dΔH = -1 / (dh_e/dQ_e)

Contribution to J:
  J[i_free(s), j_free(s)] += A[s,e] * (+dQ_e/dΔH)  if s is a free node
  J[i_free(s), j_free(t)] += A[s,e] * (-dQ_e/dΔH)  if t is a free node
  ...  (mirrored for the t-row)

This reduces to:
  For each free node i and each edge e incident to i:
    J[i, j] += A[i,e] * dQ_e/d(H_j) for each free node j

Since A[i,e] ∈ {+1, -1, 0} and dQ_e/dΔH = 1 / dh_dQ_e:
  J[i, free(s)] += +A[i,e] / dh_dQ_e   for edge e connecting s→t
  J[i, free(t)] += -A[i,e] / dh_dQ_e
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from typing import Dict, List

from .formulation import HydraulicFormulation
from ..physics.headloss import compute_headloss


class JacobianAssembler:
    """
    Builds the sparse n_free × n_free analytical Jacobian matrix.
    """

    REGULARISATION: float = 1e-8   # added to diagonal if near-zero

    def __init__(self, formulation: HydraulicFormulation) -> None:
        self.formulation = formulation

    def assemble(self, H_free: np.ndarray) -> csr_matrix:
        """
        Build the sparse Jacobian at the current iterate H_free.

        Parameters
        ----------
        H_free : np.ndarray  shape (n_free,)

        Returns
        -------
        J : scipy.sparse.csr_matrix  shape (n_free, n_free)
        """
        form = self.formulation
        n_free = form.n_free

        J = lil_matrix((n_free, n_free), dtype=np.float64)

        H_full = form.build_full_head_vector(H_free)
        network = form.network

        for e_idx, edge in enumerate(network.edges):
            s_global = network.node_index[edge.start_node]
            t_global = network.node_index[edge.end_node]

            dH = H_full[s_global] - H_full[t_global]

            # Reconstruct Q at current head (cheap single-edge inversion)
            Q = form._invert_headloss(edge, dH, e_idx)

            # Get dh/dQ from physics
            suction_heads = {}
            if edge.edge_type.value == "pump":
                suction_heads = {edge.id: H_full[s_global]}
            res = compute_headloss(edge, Q, form.pump_interpolators, suction_heads)
            dh_dQ = res.dh_dQ

            # dQ/dΔH = 1 / dh_dQ  (chain rule inversion of h(Q) = ΔH)
            if abs(dh_dQ) < 1e-30:
                dQ_dDH = 0.0
            else:
                dQ_dDH = 1.0 / dh_dQ

            # Determine which rows/cols of J are affected (free nodes only)
            s_free = form.global_to_free.get(s_global)
            t_free = form.global_to_free.get(t_global)

            # A[s_global, e_idx] = +1  (edge leaves s)
            # A[t_global, e_idx] = -1  (edge enters t)

            # Contribution to J from edge e at row s (if s is free):
            #   dF_s/dH_s = A[s,e] * dQ_e/dH_s = (+1) * (+dQ_dDH)
            #   dF_s/dH_t = A[s,e] * dQ_e/dH_t = (+1) * (-dQ_dDH)
            if s_free is not None:
                J[s_free, s_free] += dQ_dDH
                if t_free is not None:
                    J[s_free, t_free] -= dQ_dDH

            # Contribution to J from edge e at row t (if t is free):
            #   dF_t/dH_s = A[t,e] * dQ_e/dH_s = (-1) * (+dQ_dDH)
            #   dF_t/dH_t = A[t,e] * dQ_e/dH_t = (-1) * (-dQ_dDH)
            if t_free is not None:
                J[t_free, t_free] += dQ_dDH
                if s_free is not None:
                    J[t_free, s_free] -= dQ_dDH

        # Diagonal regularisation — prevent singular Jacobian at stagnant flows
        J_csr = J.tocsr()
        diag = J_csr.diagonal()
        for i in range(n_free):
            if abs(diag[i]) < self.REGULARISATION:
                J_csr[i, i] = self.REGULARISATION

        return J_csr
