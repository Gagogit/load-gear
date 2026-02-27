"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from load_gear.core.database import dispose_engine
from load_gear.api.routes import admin, analysis, files, financial, forecasts, hpfc, ingest, jobs, qa, weather

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

    return app


app = create_app()
