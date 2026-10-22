from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..services.gis import STATE_BOUNDARIES_FILE, hotspot_geojson, occurrence_geojson, state_boundaries_info


router = APIRouter(prefix="/v1/gis", tags=["gis"])
# The roadmap's /api/v1/map/* paths; same handlers as /api/v1/gis/*.
map_router = APIRouter(prefix="/v1/map", tags=["map"])


@router.get("/hotspots")
@map_router.get("/hotspots")
def hotspots() -> dict[str, object]:
    payload = hotspot_geojson()
    if payload is None:
        raise HTTPException(status_code=503, detail="Hotspot output is not available.")
    return payload


@router.get("/state-boundaries/info")
def state_boundaries_metadata() -> dict[str, object]:
    payload = state_boundaries_info()
    if payload is None:
        raise HTTPException(status_code=503, detail="State boundary layer is not available.")
    return payload


@router.get("/state-boundaries")
def state_boundaries() -> FileResponse:
    if not STATE_BOUNDARIES_FILE.exists():
        raise HTTPException(status_code=503, detail="State boundary layer is not available.")
    return FileResponse(STATE_BOUNDARIES_FILE, media_type="application/geo+json")


@router.get("/occurrences")
@map_router.get("/occurrences")
def occurrences(
    species_id: str | None = Query(default=None, max_length=120),
    west: float | None = Query(default=None, ge=-180, le=180),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    north: float | None = Query(default=None, ge=-90, le=90),
    limit: int = Query(default=1000, ge=1, le=5000),
    state: str | None = Query(default=None, max_length=80),
    year_from: int | None = Query(default=None, ge=1700, le=2100),
    year_to: int | None = Query(default=None, ge=1700, le=2100),
    iucn_category: str | None = Query(default=None, pattern="^(?i)(EX|EW|CR|EN|VU|NT|LC|DD)$"),
    within_10_km_only: bool = Query(default=False, description="Only records with stated coordinate uncertainty of at most 10 km."),
) -> dict[str, object]:
    try:
        return occurrence_geojson(
            species_id, west, south, east, north, limit,
            state=state, year_from=year_from, year_to=year_to,
            iucn_category=iucn_category, within_10_km_only=within_10_km_only,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
