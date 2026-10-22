from fastapi import APIRouter, HTTPException

from ..services.catalog import build_dataset_catalog, list_output_files, load_output_json


router = APIRouter(tags=["datasets"])


@router.get("/datasets/catalog")
def dataset_catalog() -> dict[str, object]:
    return build_dataset_catalog()


@router.get("/datasets/outputs")
def dataset_outputs() -> dict[str, object]:
    return {"outputs": list_output_files()}


@router.get("/datasets/outputs/{name}")
def dataset_output(name: str) -> object:
    payload = load_output_json(name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Output '{name}' was not found or is not JSON.")
    return payload
