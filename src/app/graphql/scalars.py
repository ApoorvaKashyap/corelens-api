"""Custom scalar types for the GraphQL schema.

core_lens returns geometry as shapely objects via Result.with_geometry().
GraphQL has no native geometry type, so this serializes to a GeoJSON dict —
the shape every mapping library (Leaflet, Mapbox GL, deck.gl) already expects.
"""

from typing import Any, NewType, cast

import shapely
import strawberry


def _serialize_geometry(value: Any) -> dict[str, Any]:
    """Convert a geometry value to a GeoJSON-compatible dict.

    Handles three cases:
    - raw WKB bytes (what Result.with_geometry() returns from the static parquet)
    - an already-decoded shapely geometry object
    - an already-GeoJSON-shaped dict (future-proofing)

    Args:
        value: The geometry value to serialize.

    Returns:
        A GeoJSON geometry dict.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = shapely.from_wkb(value)
    return cast(dict[str, Any], shapely.geometry.mapping(value))


def _parse_geometry(value: dict[str, Any]) -> Any:
    """Parse a GeoJSON dict into a shapely geometry.

    Args:
        value: A GeoJSON geometry dict.

    Returns:
        A shapely geometry object.
    """
    return shapely.geometry.shape(value)


GeoJSON = strawberry.scalar(
    cast(type, NewType("GeoJSON", dict)),
    name="GeoJSON",
    serialize=_serialize_geometry,
    parse_value=_parse_geometry,
    description="A geometry serialized as a GeoJSON geometry object.",
)
