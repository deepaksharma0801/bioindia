from fastapi import APIRouter, HTTPException, Query

from ..services.prediction import model_info, model_performance, prediction_ranking, species_prediction


router = APIRouter(prefix="/v1", tags=["prediction"])

NO_MODEL = "No trained model is available; run scripts/phase14_train_risk_model.py."


@router.get("/prediction/ranking")
def ranking(limit: int = Query(default=20, ge=1, le=200),
            unlabelled_only: bool = Query(default=False, description="Only species not used in training (Data Deficient or no verified status).")) -> dict[str, object]:
    """Species ordered by model-predicted probability of threatened status (MODEL PREDICTION)."""
    payload = prediction_ranking(limit, unlabelled_only)
    if payload is None:
        raise HTTPException(status_code=503, detail=NO_MODEL)
    return payload


@router.get("/prediction/species/{species_id}")
def prediction(species_id: str) -> dict[str, object]:
    payload = species_prediction(species_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No prediction for species '{species_id}'.")
    return payload


@router.get("/prediction/species/{species_id}/explanation")
def prediction_explanation(species_id: str) -> dict[str, object]:
    payload = species_prediction(species_id, with_explanation=True)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No prediction for species '{species_id}'.")
    return payload


@router.get("/model-info")
def model_info_data() -> dict[str, object]:
    payload = model_info()
    if payload is None:
        raise HTTPException(status_code=503, detail=NO_MODEL)
    return payload


@router.get("/model-performance")
def model_performance_data() -> dict[str, object]:
    payload = model_performance()
    if payload is None:
        raise HTTPException(status_code=503, detail=NO_MODEL)
    return payload
