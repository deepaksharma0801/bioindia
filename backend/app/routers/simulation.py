from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.simulation import DEFAULT_THRESHOLD, SimulationError, extinction_cascade


router = APIRouter(prefix="/v1/simulation", tags=["simulation"])


class CascadeRequest(BaseModel):
    species_id: str = Field(max_length=120)
    region: str | None = Field(default=None, max_length=80, description="State or union territory; omit for the whole network.")
    threshold: float = Field(default=DEFAULT_THRESHOLD, gt=0, le=1, description="Share of documented resources lost that marks a taxon as potentially lost.")
    max_steps: int = Field(default=3, ge=1, le=10)


@router.post("/extinction-cascade")
def extinction_cascade_simulation(request: CascadeRequest) -> dict[str, object]:
    """SCENARIO SIMULATION of knock-on effects through documented dependencies; not a prediction."""
    try:
        return extinction_cascade(request.species_id, request.region, request.threshold, request.max_steps)
    except SimulationError as error:
        status = 404 if "not found" in str(error) or "No occurrence records" in str(error) else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
