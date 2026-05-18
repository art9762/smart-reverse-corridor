"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from .api import router as api_router
from .config import get_settings
from .engine import Engine


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.controller_log_level)
    log = structlog.get_logger("main")

    engine: Engine | None = None
    skip_engine = os.getenv("CONTROLLER_SKIP_ENGINE") == "1"
    if not skip_engine:
        engine = Engine(settings)
        await engine.start()
        app.state.engine = engine
        log.info("app.ready", port=settings.controller_port, mode=engine.state.mode)
    else:
        log.info("app.ready_no_engine")
    try:
        yield
    finally:
        if engine is not None:
            await engine.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Reverse Corridor — Controller",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()
