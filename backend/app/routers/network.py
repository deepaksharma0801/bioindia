from fastapi import APIRouter, HTTPException

from ..services.network import ecosystem_network, species_network


router = APIRouter(prefix="/v1/network", tags=["network"])


@router.get("/species/{species_id}")
def species_network_data(species_id: str) -> dict[str, object]:
    payload = species_network(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Species '{species_id}' was not found.")
    return payload


@router.get("/ecosystem/{region}")
def ecosystem_network_data(region: str) -> dict[str, object]:
    """Region is a state or union territory name, e.g. 'Assam'."""
    payload = ecosystem_network(region)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No occurrence records for region '{region}'.")
    return payload
