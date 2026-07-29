"""GraphQL schema and router for coordinate-based entity lookups."""

import strawberry
from strawberry.fastapi import GraphQLRouter

from core_lens.entities.mws import MWSEntity
from core_lens.entities.tehsil import TehsilEntity
from core_lens.entities.waterbody import WaterbodyEntity
from core_lens.utils.spatial import point_in_entities
from src.configs import settings

from src.app.graphql.utils import EntityFilterInput, EntityResult


_ENTITIES = [
    MWSEntity(settings.data_root),
    TehsilEntity(settings.data_root),
    WaterbodyEntity(settings.data_root),
]


@strawberry.type
class CoordinateDetails:
    @strawberry.field
    def entities(self, filter: EntityFilterInput) -> EntityResult:
        """Return entity IDs containing the supplied coordinate point."""
        latlon = {
            "lat": filter.coordinates.latitude,
            "lon": filter.coordinates.longitude,
        }
        result = point_in_entities(latlon, _ENTITIES)
        return EntityResult(
            mws=result.get("MWSEntity"),
            tehsil=result.get("TehsilEntity"),
            waterbody=result.get("WaterbodyEntity"),
        )


schema = strawberry.Schema(query=CoordinateDetails)
graphql_router = GraphQLRouter(
    schema,
    path="/utils",
    graphql_ide="graphiql",
)
