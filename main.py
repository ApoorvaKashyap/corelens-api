from fastapi import FastAPI

from src.routers.graphql.utils import graphql_router
from src.routers.rest import meta

app = FastAPI()
app.include_router(meta.router, prefix="/api/v1")
app.include_router(graphql_router, prefix="/graphql/v1")
