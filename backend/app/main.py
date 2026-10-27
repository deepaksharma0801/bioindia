from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS
from .routers import analytics, datasets, gis, health, network, pipeline, prediction, species
from .services.db import DatabaseUnavailable


app = FastAPI(
    title="BioIndia API",
    version="0.1.0",
    description="Phase 1 foundation API for the BioIndia biodiversity project.",
)

# The API is read-only and uses no cookies, so credentials are not allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseUnavailable)
def database_unavailable(_: Request, error: DatabaseUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"Species database is not available: {error}"})


app.include_router(health.router, prefix="/api")
app.include_router(datasets.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(species.router, prefix="/api")
app.include_router(gis.router, prefix="/api")
app.include_router(gis.map_router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(network.router, prefix="/api")
app.include_router(prediction.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "BioIndia Phase 1 API is running.",
        "docs": "/docs",
        "health": "/api/health",
    }
