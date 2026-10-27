import os

from fastapi import APIRouter, HTTPException, Query

from ..services.species import get_species, list_species, species_conservation_status, species_environment_profile, species_intelligence, species_land_pressure_profile, species_occurrences, species_protection_profile, species_trend, state_profiles
from ..services.timeseries import species_observation_time_series


router = APIRouter(prefix="/v1/species", tags=["species"])


@router.get("")
def species_list(
    query: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, min_length=2, max_length=2),
) -> dict[str, object]:
    return {"species": list_species(query=query, status=status)}


@router.get("/search")
def species_search(query: str = Query(min_length=1, max_length=120)) -> dict[str, object]:
    return {"species": list_species(query=query)}


@router.get("/state-profiles")
def state_profile_data() -> object:
    return state_profiles()


@router.get("/occurrences")
def occurrence_map_data(all_species: bool = Query(default=False, description="Return every species instead of the five flagships.")) -> dict[str, object]:
    payload = species_occurrences(all_species=all_species)
    if payload is None:
        raise HTTPException(status_code=503, detail="Occurrence output is not available.")
    return payload


@router.get("/{species_id}")
def species_detail(species_id: str) -> dict[str, object]:
    species = get_species(species_id)
    if species is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    return species


@router.get("/{species_id}/occurrences")
def species_occurrence_data(species_id: str) -> dict[str, object]:
    payload = species_occurrences(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Occurrence data for '{species_id}' was not found.")
    return payload


@router.get("/{species_id}/trend")
def species_trend_data(species_id: str) -> dict[str, object]:
    payload = species_trend(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Trend data for '{species_id}' was not found.")
    return payload


@router.get("/{species_id}/observation-time-series")
def species_observation_time_series_data(species_id: str) -> dict[str, object]:
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Occurrence time-series data are not available.")
    if get_species(species_id) is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    payload = species_observation_time_series(species_id)
    if payload is None:
        raise HTTPException(status_code=503, detail="Occurrence time-series data are not available.")
    return payload


@router.get("/{species_id}/intelligence")
def species_intelligence_data(species_id: str) -> dict[str, object]:
    payload = species_intelligence(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Intelligence profile for '{species_id}' was not found.")
    return payload


@router.get("/{species_id}/conservation")
def species_conservation_data(species_id: str) -> dict[str, object]:
    payload = species_conservation_status(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Conservation data for '{species_id}' was not found.")
    return payload


@router.get("/{species_id}/environment")
def species_environment_data(species_id: str) -> dict[str, object]:
    if get_species(species_id) is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    payload = species_environment_profile(species_id)
    if payload is None:
        raise HTTPException(status_code=503, detail="Climate profile output is not available.")
    return payload


@router.get("/{species_id}/land-pressure")
def species_land_pressure_data(species_id: str) -> dict[str, object]:
    if get_species(species_id) is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    payload = species_land_pressure_profile(species_id)
    if payload is None:
        raise HTTPException(status_code=503, detail="Land-cover and forest-change data are not available for this species.")
    return payload


@router.get("/{species_id}/protection")
def species_protection_data(species_id: str) -> dict[str, object]:
    if get_species(species_id) is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    payload = species_protection_profile(species_id)
    if payload is None:
        raise HTTPException(status_code=503, detail="Protected-area intersection data are not available for this species.")
    return payload
