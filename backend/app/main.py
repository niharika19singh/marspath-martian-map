from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1.data_status import router as data_status_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.intelligence import router as intelligence_router
from backend.app.api.v1.layers import router as layers_router
from backend.app.api.v1.routes import router as routes_router
from backend.app.core.config import Settings, get_settings, validate_cors_origins
from backend.app.core.exceptions import MarsPathError
from backend.app.core.logging import setup_logging


def configure_cors(target_app: FastAPI, app_settings: Settings | None = None) -> list[str]:
    """
    Configures CORSMiddleware on the given FastAPI application using validated,
    fail-closed explicit origins from MARSPath Settings. Never falls back to wildcard.
    """
    active_settings = app_settings or get_settings()
    origins = validate_cors_origins(active_settings.cors_origin_list)
    target_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return origins


settings = get_settings()
logger = setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Planetary Route Intelligence and Science Planner for Mars Exploration (Jezero Crater Pilot)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration (fail-closed; no wildcard fallback)
origins = configure_cors(app, settings)


# Custom exception handler
@app.exception_handler(MarsPathError)
async def marspath_exception_handler(request: Request, exc: MarsPathError):
    logger.warning("MarsPath error on %s: %s", request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )


# Mount routers
app.include_router(health_router)
app.include_router(layers_router)
app.include_router(data_status_router)
app.include_router(routes_router)
app.include_router(intelligence_router)


@app.get("/", summary="Root landing index")
def root_index():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "health_check": "/health",
        "api_v1_layers": "/api/v1/layers",
        "api_v1_data_status": "/api/v1/data/status",
        "api_v1_route_plan": "/api/v1/routes/plan",
        "api_v1_intelligence_status": "/api/v1/intelligence/status",
        "api_v1_intelligence_spacecraft": "/api/v1/intelligence/spacecraft",
        "api_v1_intelligence_rovers": "/api/v1/intelligence/rovers",
        "api_v1_intelligence_observations": "/api/v1/intelligence/observations",
        "api_v1_intelligence_timeline": "/api/v1/intelligence/timeline",
    }
