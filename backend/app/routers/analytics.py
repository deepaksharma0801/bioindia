from fastapi import APIRouter, HTTPException, Query

from typing import Literal

from ..services.concentration import biodiversity_concentration
from ..services.priority import concentration_zones, conservation_priority, threatened_species
from ..services.timeseries import biodiversity_observation_time_series


router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.get("/biodiversity-trends")
def biodiversity_trends() -> dict[str, object]:
    payload = biodiversity_observation_time_series()
    if payload is None:
        raise HTTPException(status_code=503, detail="Occurrence time-series data are not available.")
    return payload


@router.get("/biodiversity-concentration")
def biodiversity_concentration_data(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    payload = biodiversity_concentration(limit)
    if payload is None:
        raise HTTPException(status_code=503, detail="Occurrence concentration data are not available.")
    return payload


GRID_UNAVAILABLE = "Grid metrics are not available; run scripts/phase13_build_grid_metrics.py."


@router.get("/hotspots")
def hotspots(
    rank_by: Literal["observed_species", "threatened_species", "records", "records_within_10_km"] = "observed_species",
    limit: int = Query(default=25, ge=1, le=500),
) -> dict[str, object]:
    """Data-derived concentration zones (not officially recognised biodiversity hotspots)."""
    payload = concentration_zones(rank_by, limit)
    if payload is None:
        raise HTTPException(status_code=503, detail=GRID_UNAVAILABLE)
    return payload


@router.get("/conservation-priority")
def conservation_priority_data(
    min_threatened_species: int = Query(default=1, ge=0, le=50),
    max_wildlife_pa_pct: float = Query(default=10.0, ge=0, le=100, description="Cells at or below this wildlife protected-area cover count as gaps."),
    min_records_within_10_km: int = Query(default=0, ge=0, description="Require some precisely located records in the cell."),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, object]:
    """Protection-gap screen: threatened species present, little wildlife protected-area cover."""
    payload = conservation_priority(min_threatened_species, max_wildlife_pa_pct, min_records_within_10_km, limit)
    if payload is None:
        raise HTTPException(status_code=503, detail=GRID_UNAVAILABLE)
    return payload


@router.get("/threatened-species")
def threatened_species_data() -> dict[str, object]:
    return {
        "species": threatened_species(),
        "note": "Categories are source-reported unless category_verified is true. Protection percentages use only records located within 10 km.",
    }
