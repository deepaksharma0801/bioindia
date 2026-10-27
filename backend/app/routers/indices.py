from fastapi import APIRouter, HTTPException, Query

from ..services.indices import IndexError_, cipi, ibvci


router = APIRouter(prefix="/v1/indices", tags=["indices"])

WEIGHTS_HELP = "Optional weights as component:value pairs, e.g. 'extinction_vulnerability:2,protection_deficit:1'."
NO_DATA = "Index inputs are not available; train the risk model and build the grid metrics first."


def _run(function, *args):
    try:
        payload = function(*args)
    except IndexError_ as error:
        raise HTTPException(status_code=404 if "not found" in str(error) else 422, detail=str(error)) from error
    if payload is None:
        raise HTTPException(status_code=503, detail=NO_DATA)
    return payload


@router.get("/ibvci")
def ibvci_ranking(weights: str | None = Query(default=None, max_length=400, description=WEIGHTS_HELP),
                  limit: int = Query(default=50, ge=1, le=500)) -> dict[str, object]:
    """EXPERIMENTAL Indian Biodiversity Vulnerability and Cascade Index, per species."""
    return _run(ibvci, weights, limit)


@router.get("/ibvci/{species_id}")
def ibvci_species(species_id: str, weights: str | None = Query(default=None, max_length=400, description=WEIGHTS_HELP)) -> dict[str, object]:
    return _run(ibvci, weights, 1, species_id)


@router.get("/cipi")
def cipi_ranking(weights: str | None = Query(default=None, max_length=400, description=WEIGHTS_HELP),
                 limit: int = Query(default=50, ge=1, le=500),
                 state: str | None = Query(default=None, max_length=80)) -> dict[str, object]:
    """EXPERIMENTAL Conservation Intervention Priority Index, per grid cell."""
    return _run(cipi, weights, limit, state)
