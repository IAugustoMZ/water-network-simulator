"""GET /results/{result_id} — retrieve full simulation results."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import SimulationResultSchema
from ...storage.stores import result_store

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{result_id}", response_model=SimulationResultSchema)
async def get_results(result_id: str):
    """Retrieve the full simulation result by ID."""
    data = await result_store.get(result_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Result '{result_id}' not found or has expired (TTL: 2 hours)."
        )
    return data["object"]
