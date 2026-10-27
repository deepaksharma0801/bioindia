from fastapi import APIRouter, HTTPException

from ..services.land_pressure import state_land_use


router = APIRouter(prefix="/v1/land-use", tags=["land-use"])

NO_DATA = "Land-use grid is not available; run scripts/phase10_build_land_use_grid.py."


@router.get("/states")
def states() -> dict[str, object]:
    """Forest cover (2000), tree-cover loss 2001-2024, fragmentation and human pressure per state."""
    payload = state_land_use()
    if payload is None:
        raise HTTPException(status_code=503, detail=NO_DATA)
    return payload


@router.get("/states/{state}")
def state(state: str) -> dict[str, object]:
    """One state's land-use summary with yearly forest loss."""
    payload = state_land_use(state)
    if payload is None:
        if state_land_use() is None:
            raise HTTPException(status_code=503, detail=NO_DATA)
        raise HTTPException(status_code=404, detail=f"State '{state}' was not found in the land-use grid.")
    return payload
