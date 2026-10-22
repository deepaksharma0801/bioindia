from fastapi import APIRouter

from ..services.catalog import build_phase_summary


router = APIRouter(tags=["pipeline"])


@router.get("/phase-1/summary")
def phase_summary() -> dict[str, object]:
    return build_phase_summary()
