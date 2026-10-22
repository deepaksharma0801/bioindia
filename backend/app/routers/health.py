from fastapi import APIRouter

from ..config import HTML_FILE, PROJECT_ROOT


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "project_root": str(PROJECT_ROOT),
        "html_present": HTML_FILE.exists(),
    }
