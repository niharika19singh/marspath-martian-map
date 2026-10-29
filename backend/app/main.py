from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.api.v1.data_status import router as data_status_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.layers import router as layers_router
from backend.app.api.v1.routes import router as routes_router
from backend.app.core.config import get_settings
from backend.app.core.exceptions import MarsPathError
from backend.app.core.logging import setup_logging

settings = get_settings()
logger = setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Planetary Route Intelligence and Science Planner for Mars Exploration (Jezero Crater Pilot)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    }
