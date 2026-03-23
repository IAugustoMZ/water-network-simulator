"""
Water Network Hydraulic Simulator — FastAPI application entry point.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import network as network_router
from app.api.routers import simulation as simulation_router
from app.api.routers import results as results_router
from app.api.routers import analyze as analyze_router
from app.storage.stores import network_store
from app.solver.newton_raphson import SolverDivergenceError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_NETWORK_ID = "default-city-network"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: pre-load city network on startup."""
    logger.info("Starting Water Network Simulator...")
    try:
        from app.network.city_network import build_city_network
        from app.graph.network import NetworkGraph
        from app.physics.pump import PumpInterpolator

        nodes, edges, demands, pump_interpolators = build_city_network()
        network = NetworkGraph(nodes, edges)
        warnings = network.topological_validate()
        if warnings:
            for w in warnings:
                logger.warning(f"[City Network] {w}")

        await network_store.put(
            network,
            {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "pump_interpolators": pump_interpolators,
                "demands": demands,
            },
            store_id=DEFAULT_NETWORK_ID,
        )
        logger.info(
            f"City network pre-loaded: {len(nodes)} nodes, {len(edges)} edges, "
            f"{len(warnings)} validation warnings."
        )
    except Exception as exc:
        logger.error(f"Failed to pre-load city network: {exc}", exc_info=True)

    yield

    logger.info("Shutting down Water Network Simulator.")


app = FastAPI(
    title="Water Network Hydraulic Simulator",
    description=(
        "High-fidelity steady-state hydraulic simulation platform for water distribution networks. "
        "Implements Darcy-Weisbach friction, PCHIP pump curves, ISA valve models, "
        "and Newton-Raphson solver with sparse analytical Jacobian."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:80",
)
cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(network_router.router)
app.include_router(simulation_router.router)
app.include_router(results_router.router)
app.include_router(analyze_router.router)


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "water-network-simulator", "version": "1.0.0"}


@app.get("/scenarios", tags=["scenarios"])
async def list_scenarios():
    """Return all available pre-defined simulation scenarios."""
    from app.network.city_network import SCENARIOS
    return {
        name: {"description": sc.get("description", "")}
        for name, sc in SCENARIOS.items()
    }


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(SolverDivergenceError)
async def solver_divergence_handler(request: Request, exc: SolverDivergenceError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "solver_divergence",
            "message": str(exc),
            "iterations": exc.iterations,
            "residual": exc.residual,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. Check server logs for details.",
        },
    )
