from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from loguru import logger

from src.routers.graphql import utils
from src.routers.rest import meta


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """Lifespan event handler for the FastAPI application."""
    LOG_DIR = Path(".logs")
    LOG_DIR.mkdir(exist_ok=True)

    logger.add(
        LOG_DIR / "core-lens-api.log",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        level="INFO",
        diagnose=False,
        enqueue=True,
        format="{time:YYYY-MM-DD HH:MM:ss} | {level} | {name}:{line} | {message}",
    )
    logger.info("Starting Up")
    yield
    logger.info("Shutting down")


app = FastAPI(lifespan=lifespan)
app.include_router(meta.router, prefix="/api/v1")
app.include_router(utils.graphql_router, prefix="/graphql/v1")
