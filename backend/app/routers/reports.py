from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.reports import ReportError, regional_report


router = APIRouter(prefix="/v1/reports", tags=["reports"])


class RegionalReportRequest(BaseModel):
    region: str = Field(max_length=80, description="State or union territory name, e.g. 'Kerala'.")


@router.post("/regional")
def regional(request: RegionalReportRequest) -> dict[str, object]:
    """Data-derived state report; every statement carries the figures it was built from."""
    try:
        return regional_report(request.region)
    except ReportError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
