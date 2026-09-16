"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from loguru import logger

from src.configs import settings
from src.routers.rest import meta
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """Lifespan event handler for the FastAPI application.

    Initializes logging, generates GraphQL types from entity schema profiles,
    assembles the schema, and mounts the GraphQL router before the first
    request is served.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control back to FastAPI for the duration of the application's life.
    """
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

    from src.app.graphql import generated as gql_generated
    from src.app.graphql.schema import build_schema
    from src.routers.graphql.entity import make_entity_router

    gql_generated.initialize(settings.data_root)
    logger.info("GraphQL types initialized")

    schema = build_schema()
    app.include_router(make_entity_router(schema), prefix="/graphql/v1")
    logger.info("Starting up")

    yield

    logger.info("Shutting down")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        # add your deployed frontend origin(s) here once known
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(meta.router, prefix="/api/v1")
