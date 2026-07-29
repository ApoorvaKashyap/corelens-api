import strawberry


@strawberry.input
class CoordinatesInput:
    """Lat/lon pair."""

    latitude: float
    longitude: float


@strawberry.input
class EntityFilterInput:
    """Filter wrapper — matches spec's `filter: {coordinates: {...}}`."""

    coordinates: CoordinatesInput


@strawberry.type
class EntityResult:
    """IDs for every entity type at the queried point. None = point outside."""

    mws: str | None
    tehsil: str | None
    waterbody: str | None
