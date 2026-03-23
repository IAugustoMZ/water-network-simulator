"""
Newton-Raphson solver for the steady-state hydraulic H-equation system.

Algorithm:
  H₀ = initial_guess()
  for k = 0, 1, ..., max_iter:
    F_k = assemble_residuals(H_k)
    if ‖F_k‖∞ < tol_abs:  CONVERGED
    J_k = assemble_jacobian(H_k)
    dH  = spsolve(J_k, -F_k)
    α   = armijo_line_search(H_k, dH, F_k)
    H_{k+1} = H_k + α·dH

Line search: Armijo backtracking (sufficient decrease condition).
Recovery: 3 attempts with randomised perturbation on failure.
"""
from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass, field
from scipy.sparse.linalg import spsolve
from typing import List, Optional

from .formulation import HydraulicFormulation
from .jacobian import JacobianAssembler
from ..physics.headloss import PhysicsResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration and result types
# ---------------------------------------------------------------------------

@dataclass
class SolverConfig:
    max_iterations: int = 100
    tolerance_abs: float = 1e-6        # ‖F‖∞ convergence threshold (m³/s)
    tolerance_rel: float = 1e-8        # relative residual drop
    line_search_c1: float = 1e-4       # Armijo constant
    line_search_max_steps: int = 25    # max backtracking halvings
    min_alpha: float = 1e-10           # minimum step length before giving up
    max_recovery_attempts: int = 3     # number of retry attempts
    perturbation_sigma: float = 5.0    # m — std-dev for random perturbation


@dataclass
class SolverResult:
    converged: bool
    iterations: int
    residual_norm: float                    # ‖F‖∞ at termination
    H_free: np.ndarray                      # converged free-node heads (m)
    edge_flows: np.ndarray                  # final edge flows Q (m³/s)
    physics_results: List[PhysicsResult]    # per-edge physics
    convergence_history: List[float] = field(default_factory=list)  # ‖F‖∞ per iteration
    warnings: List[str] = field(default_factory=list)


class SolverDivergenceError(Exception):
    def __init__(self, message: str, iterations: int, residual: float):
        super().__init__(message)
        self.iterations = iterations
        self.residual = residual


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class NewtonRaphsonSolver:
    """
    Newton-Raphson solver with Armijo backtracking and recovery heuristics.
    """

    def __init__(
        self,
        formulation: HydraulicFormulation,
        config: Optional[SolverConfig] = None,
    ) -> None:
        self.formulation = formulation
        self.config = config or SolverConfig()
        self.jacobian_assembler = JacobianAssembler(formulation)
        self._warm_start: Optional[np.ndarray] = None

    def solve(
        self,
        demands: np.ndarray,
        initial_guess: Optional[np.ndarray] = None,
    ) -> SolverResult:
        """
        Solve the hydraulic network equations.

        Parameters
        ----------
        demands : np.ndarray  shape (n_free,)
            Demand at each free node (m³/s, positive = consumption).
        initial_guess : np.ndarray, optional
            Initial free-node head vector.  Uses warm start or heuristic if None.

        Returns
        -------
        SolverResult
        """
        cfg = self.config

        # Initial guess selection
        if initial_guess is not None:
            H = initial_guess.copy()
        elif self._warm_start is not None:
            H = self._warm_start.copy()
        else:
            H = self._initial_guess()

        warnings: List[str] = []
        last_result: Optional[SolverResult] = None

        for attempt in range(cfg.max_recovery_attempts + 1):
            try:
                result = self._nr_loop(H, demands, warnings)
                if result.converged:
                    self._warm_start = result.H_free.copy()
                else:
                    warnings.append(
                        f"Solver did not converge in {cfg.max_iterations} iterations "
                        f"(residual = {result.residual_norm:.3e})."
                    )
                return result
            except np.linalg.LinAlgError as e:
                logger.warning(f"Attempt {attempt}: linear algebra error: {e}")
                H = self._recovery_guess(H, attempt)
            except Exception as e:
                logger.warning(f"Attempt {attempt}: unexpected error: {e}")
                H = self._recovery_guess(H, attempt)

        # All attempts exhausted
        raise SolverDivergenceError(
            f"Solver diverged after {cfg.max_recovery_attempts + 1} attempts.",
            iterations=cfg.max_iterations,
            residual=float("inf"),
        )

    # ------------------------------------------------------------------
    # Core Newton-Raphson loop
    # ------------------------------------------------------------------

    def _nr_loop(
        self,
        H0: np.ndarray,
        demands: np.ndarray,
        warnings: List[str],
    ) -> SolverResult:
        cfg = self.config
        H = H0.copy()
        history: List[float] = []

        F, Q_vec, physics_results = self.formulation.assemble_residuals_with_physics(H, demands)
        F_norm = float(np.max(np.abs(F)))
        history.append(F_norm)

        logger.debug(f"NR start: ‖F‖∞ = {F_norm:.4e}")

        for k in range(cfg.max_iterations):
            # Convergence check
            if F_norm < cfg.tolerance_abs:
                logger.debug(f"NR converged at iteration {k}: ‖F‖∞ = {F_norm:.4e}")
                return SolverResult(
                    converged=True,
                    iterations=k,
                    residual_norm=F_norm,
                    H_free=H,
                    edge_flows=Q_vec,
                    physics_results=physics_results,
                    convergence_history=history,
                    warnings=warnings,
                )

            # Jacobian
            J = self.jacobian_assembler.assemble(H)

            # Solve J · dH = -F
            try:
                dH = spsolve(J, -F)
            except Exception as e:
                logger.warning(f"  spsolve failed at iteration {k}: {e}")
                raise np.linalg.LinAlgError(str(e))

            if not np.all(np.isfinite(dH)):
                logger.warning(f"  Non-finite dH at iteration {k}")
                raise np.linalg.LinAlgError("Non-finite Newton step.")

            # Line search
            alpha = self._armijo_line_search(H, dH, F, F_norm, demands)

            # Update
            H_new = H + alpha * dH

            # Evaluate at new point
            F_new, Q_vec_new, physics_new = self.formulation.assemble_residuals_with_physics(
                H_new, demands
            )
            F_norm_new = float(np.max(np.abs(F_new)))
            history.append(F_norm_new)

            logger.debug(
                f"  iter {k:3d}: ‖F‖∞ = {F_norm_new:.4e}, α = {alpha:.3f}"
            )

            H = H_new
            F = F_new
            Q_vec = Q_vec_new
            physics_results = physics_new
            F_norm = F_norm_new

        # Max iterations reached — return partial result
        logger.warning(f"NR reached max iterations ({cfg.max_iterations}). ‖F‖∞ = {F_norm:.4e}")
        return SolverResult(
            converged=False,
            iterations=cfg.max_iterations,
            residual_norm=F_norm,
            H_free=H,
            edge_flows=Q_vec,
            physics_results=physics_results,
            convergence_history=history,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Line search
    # ------------------------------------------------------------------

    def _armijo_line_search(
        self,
        H: np.ndarray,
        dH: np.ndarray,
        F: np.ndarray,
        F_norm: float,
        demands: np.ndarray,
    ) -> float:
        """
        Armijo backtracking line search.

        Uses ‖F‖∞ comparison (max-norm) rather than squared 2-norm
        to better handle hydraulic networks where a few nodes dominate.

        Also bounds the maximum step to 10 m per iteration to prevent
        large oscillations in the head vector.
        """
        cfg = self.config

        # Bound step size: never move more than MAX_STEP_M metres per node
        MAX_STEP_M = 10.0
        max_dH = float(np.max(np.abs(dH)))
        if max_dH > MAX_STEP_M:
            dH = dH * (MAX_STEP_M / max_dH)

        alpha = 1.0
        F_inf = float(np.max(np.abs(F)))
        c1 = cfg.line_search_c1

        for step in range(cfg.line_search_max_steps):
            H_trial = H + alpha * dH
            F_trial = self.formulation.assemble_residuals(H_trial, demands)
            F_trial_inf = float(np.max(np.abs(F_trial)))

            # Accept if sufficient decrease
            if F_trial_inf <= F_inf * (1.0 - c1 * alpha):
                return alpha

            # Accept even a small improvement to avoid stagnation
            if F_trial_inf < F_inf and step >= 5:
                return alpha

            alpha *= 0.5
            if alpha < cfg.min_alpha:
                # Last resort: return smallest alpha that gives any decrease
                H_min = H + cfg.min_alpha * dH
                F_min = self.formulation.assemble_residuals(H_min, demands)
                if float(np.max(np.abs(F_min))) < F_inf:
                    return cfg.min_alpha
                return cfg.min_alpha

        return alpha

    # ------------------------------------------------------------------
    # Initial / recovery guesses
    # ------------------------------------------------------------------

    def _initial_guess(self) -> np.ndarray:
        """
        Heuristic initial guess based on node elevations.

        Assumes service pressure of ~30 m everywhere, so:
            H_i ≈ elevation_i + 30 m

        This creates a realistic pressure gradient from the start,
        preventing the degenerate flat-head stagnation that occurs
        when all nodes start at the same head (all dH=0 → all Q=0).
        """
        network = self.formulation.network
        free_idx = self.formulation.free_indices
        fixed_heads = self.formulation.get_fixed_heads()
        mean_fixed = float(np.mean(fixed_heads)) if len(fixed_heads) > 0 else 50.0

        H0 = np.zeros(self.formulation.n_free)
        for f, g in enumerate(free_idx):
            node = network.nodes[g]
            elev = node.elevation
            # Interpolate between fixed head and elevation+service_pressure
            H0[f] = min(mean_fixed, elev + 35.0)

        return H0

    def _recovery_guess(self, H_prev: np.ndarray, attempt: int) -> np.ndarray:
        """
        Recovery heuristics (3 tiers):
          0 → random perturbation ±σ around previous H
          1 → reset to fresh initial guess + perturbation
          2 → set all heads to a flat profile at the mean fixed head
        """
        cfg = self.config
        rng = np.random.default_rng(seed=attempt * 42)

        if attempt == 0:
            noise = rng.normal(0.0, cfg.perturbation_sigma, size=H_prev.shape)
            H_new = H_prev + noise
        elif attempt == 1:
            H_new = self._initial_guess()
            noise = rng.normal(0.0, cfg.perturbation_sigma * 0.5, size=H_new.shape)
            H_new = H_new + noise
        else:
            fixed_heads = self.formulation.get_fixed_heads()
            mean_fixed = float(np.mean(fixed_heads)) if len(fixed_heads) > 0 else 30.0
            H_new = np.full(self.formulation.n_free, mean_fixed)

        logger.info(f"Recovery attempt {attempt + 1}: new initial guess computed.")
        return H_new
