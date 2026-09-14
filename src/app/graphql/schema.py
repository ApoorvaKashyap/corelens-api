"""GraphQL schema assembly.

build_schema() is called during FastAPI lifespan after generated.initialize()
has populated the generated types. Defining Query inside build_schema() ensures
the dynamically-built MWSConnection and Tehsil types are available when
Strawberry inspects the class annotations.
"""

from __future__ import annotations

import strawberry

from src.app.graphql import generated as gql_generated
from src.app.graphql.utils import EntityResult


def build_schema() -> strawberry.Schema:
    """Assemble and return the Strawberry schema with all queries.

    Must be called after generated.initialize() — the generated types
    (MWSConnection, TEHSIL_GENERATED) must be populated before this function
    runs.

    Returns:
        A Strawberry schema with the merged Query type.

    Raises:
        AssertionError: If generated.initialize() was not called first.
    """
    from src.app.graphql.resolvers import (
        resolve_entities,
        resolve_farms,
        resolve_mws,
        resolve_tehsils,
        resolve_waterbody,
    )

    assert gql_generated.MWS_GENERATED is not None, (
        "Call generated.initialize() before build_schema()"
    )
    assert gql_generated.TEHSIL_GENERATED is not None
    assert gql_generated.MWSConnection is not None
    assert gql_generated.FARM_GENERATED is not None

    @strawberry.type
    class Query:
        entities: EntityResult = strawberry.field(resolver=resolve_entities)
        mws: gql_generated.MWSConnection = strawberry.field(resolver=resolve_mws)  # type: ignore[valid-type]
        tehsils: list[gql_generated.TEHSIL_GENERATED.strawberry_type] = (
            strawberry.field(  # type: ignore[name-defined]
                resolver=resolve_tehsils
            )
        )
        waterbody: list[gql_generated.WATERBODY_GENERATED.strawberry_type] = (
            strawberry.field(  # type: ignore[name-defined]
                resolver=resolve_waterbody
            )
        )
        farms: list[gql_generated.FARM_GENERATED.strawberry_type] = strawberry.field(  # type: ignore[name-defined]
            resolver=resolve_farms
        )

    return strawberry.Schema(query=Query)
