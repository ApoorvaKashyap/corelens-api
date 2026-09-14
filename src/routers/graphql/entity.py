"""GraphQL router factory for the entity retrieval API."""

from __future__ import annotations

import strawberry
from strawberry.fastapi import GraphQLRouter

from src.app.graphql.context import get_context


def make_entity_router(schema: strawberry.Schema) -> GraphQLRouter:
    """Create the GraphQL router for entity retrieval queries.

    Args:
        schema: The assembled Strawberry schema, built during lifespan.

    Returns:
        A GraphQLRouter ready to be mounted on the FastAPI app.
    """
    return GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql")
