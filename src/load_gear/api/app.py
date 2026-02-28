"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from load_gear.core.database import dispose_engine
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from load_gear.api.routes import admin, analysis, files, financial, forecasts, hpfc, ingest, jobs, pipeline, qa, weather

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LOAD-GEAR starting up")
    yield
    logger.info("LOAD-GEAR shutting down")
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LOAD-GEAR Energy Intelligence",
        version="0.1.0",
        description="Meter data processing, forecasting, and financial calculation",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler — always return JSON, never HTML/plaintext
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Interner Fehler: {exc}"},
        )

    # Register routers
    app.include_router(admin.router)
    app.include_router(jobs.router)
    app.include_router(files.router)
    app.include_router(ingest.router)
    app.include_router(qa.router)
    app.include_router(analysis.router)
    app.include_router(forecasts.router)
    app.include_router(hpfc.router)
    app.include_router(financial.router)
    app.include_router(weather.router)
    app.include_router(pipeline.router)

    # Serve frontend SPA
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()
