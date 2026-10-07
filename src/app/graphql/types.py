"""Dynamic Strawberry type generation from entity schema profiles.

Types are generated from each entity's real schema_profile + a parquet footer
read rather than hand-written. Hand-written types drift silently when a column
is added or renamed upstream; generated types break loudly instead.

Column casing in real data is inconsistent (mws_id vs TEHSIL vs District).
That inconsistency caused a real bug: a District= kwarg silently failing to
match a district column, widening a query's scope. Generating fields from
schema_profile controls naming exactly once via _normalize_field_name.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from typing import TYPE_CHECKING, Any, Optional

import polars as pl
import strawberry

from src.app.graphql.scalars import GeoJSON

if TYPE_CHECKING:
    from core_lens.base.entity import BaseEntity

_POLARS_TO_PYTHON: dict[type, type] = {
    pl.Utf8: str,
    pl.Int8: int,
    pl.Int16: int,
    pl.Int32: int,
    pl.Int64: int,
    pl.UInt8: int,
    pl.UInt16: int,
    pl.UInt32: int,
    pl.UInt64: int,
    pl.Float32: float,
    pl.Float64: float,
    pl.Boolean: bool,
    pl.Date: datetime.date,
    pl.Datetime: datetime.datetime,
}


def _python_type_for(dtype: pl.DataType) -> Any:
    return _POLARS_TO_PYTHON.get(type(dtype), strawberry.scalars.JSON)


def _normalize_field_name(col: str) -> str:
    """Map a real column name to the name exposed over GraphQL.

    Uses .lower() only — real columns are underscore_separated once lowercased.
    Extend this function for columns that need more than casing fixed (spaces,
    leading digits, reserved words); there is exactly one place to fix it.

    Args:
        col: The raw parquet column name.

    Returns:
        The normalized GraphQL field name.
    """
    name = col.lower()
    name = name.replace("%", "pct")
    name = re.sub(r"\W+", "_", name)
    name = name.strip("_")
    if name[0].isdigit():
        name = f"_{name}"
    return name


@dataclasses.dataclass
class GeneratedType:
    """A dynamically-built Strawberry type with the resolver's column name map.

    Attributes:
        strawberry_type: The generated Strawberry-annotated dataclass.
        field_to_column: Mapping of GraphQL field name to real parquet column name.
        key_cols: Normalized key column names.
    """

    strawberry_type: type
    field_to_column: dict[str, str]
    key_cols: list[str]


def build_graphql_type(entity: BaseEntity, type_name: str) -> GeneratedType:
    """Build a Strawberry type from one entity's schema_profile and real dtypes.

    Called once per entity at startup — schema_profile triggers a cached parquet
    footer read, and a GraphQL schema is meant to be static and introspectable.

    Key columns come first (no default) since dataclasses require non-default
    fields before defaulted ones. Attribute columns are Optional. Geometry is
    always Optional and always the GeoJSON scalar, fetched only when selected.

    Args:
        entity: The core_lens entity to generate a type for.
        type_name: The name of the generated Strawberry type.

    Returns:
        A GeneratedType wrapping the Strawberry-annotated dataclass.
    """
    profile = entity.schema_profile
    static_schema = pl.scan_parquet(
        entity._resolve(entity.static_path),
        storage_options=entity._storage_options or None,
    ).collect_schema()

    field_to_column: dict[str, str] = {}
    fields: list[tuple[str, Any] | tuple[str, Any, Any]] = []

    for col in profile.key_cols:
        name = _normalize_field_name(col)
        field_to_column[name] = col
        fields.append((name, _python_type_for(static_schema[col])))

    for col in profile.extra_static_cols:
        name = _normalize_field_name(col)
        if name in field_to_column:
            continue
        field_to_column[name] = col
        py_type = _python_type_for(static_schema[col])
        fields.append((name, Optional[py_type], dataclasses.field(default=None)))

    fields.append(("geometry", Optional[GeoJSON], dataclasses.field(default=None)))

    cls = dataclasses.make_dataclass(type_name, fields)
    return GeneratedType(
        strawberry_type=strawberry.type(cls),
        field_to_column=field_to_column,
        key_cols=[_normalize_field_name(c) for c in profile.key_cols],
    )


def build_temporal_graphql_type(
    entity: BaseEntity, type_name: str, resolution: str
) -> GeneratedType:
    """Build a Strawberry type from one entity's annual or sub_annual schema.

    Same approach as build_graphql_type, applied to a temporal grain instead
    of the static grain: key column(s) and the detected time column are
    required fields, every other real column is Optional. There is no
    geometry field at these grains.

    Args:
        entity: The core_lens entity to generate a type for.
        type_name: The name of the generated Strawberry type.
        resolution: Either "annual" or "sub_annual".

    Returns:
        A GeneratedType wrapping the Strawberry-annotated dataclass.
    """
    profile = entity.schema_profile
    if resolution == "annual":
        path = entity.annual_path
        time_col = profile.annual_time_col
        extra_cols = profile.extra_annual_cols
    else:
        path = entity.sub_annual_path
        time_col = profile.sub_annual_time_col
        extra_cols = profile.extra_sub_annual_cols

    assert path is not None, f"Entity has no {resolution}_path"
    schema = pl.scan_parquet(
        entity._resolve(path), storage_options=entity._storage_options or None
    ).collect_schema()

    field_to_column: dict[str, str] = {}
    fields: list[tuple[str, Any] | tuple[str, Any, Any]] = []

    for col in profile.key_cols:
        name = _normalize_field_name(col)
        field_to_column[name] = col
        fields.append((name, _python_type_for(schema[col])))

    if time_col is not None:
        name = _normalize_field_name(time_col)
        if name not in field_to_column:
            field_to_column[name] = time_col
            fields.append((name, _python_type_for(schema[time_col])))

    for col in extra_cols:
        name = _normalize_field_name(col)
        if name in field_to_column:
            continue
        field_to_column[name] = col
        py_type = _python_type_for(schema[col])
        fields.append((name, Optional[py_type], dataclasses.field(default=None)))

    cls = dataclasses.make_dataclass(type_name, fields)
    return GeneratedType(
        strawberry_type=strawberry.type(cls),
        field_to_column=field_to_column,
        key_cols=[_normalize_field_name(c) for c in profile.key_cols],
    )


def build_connection_type(item_strawberry_type: type, type_name: str) -> type:
    """Build a paginated connection type wrapping a dynamically-generated item type.

    Strawberry needs a concrete, named type for schema introspection — list[Any]
    does not work as a field type.

    Args:
        item_strawberry_type: The generated Strawberry type for individual items.
        type_name: The name of the generated connection type.

    Returns:
        A Strawberry-annotated dataclass with items, total_count, limit, offset.
    """
    fields = [
        ("items", list[item_strawberry_type]),  # type: ignore[valid-type]
        ("total_count", int),
        ("limit", int),
        ("offset", int),
    ]
    cls = dataclasses.make_dataclass(type_name, fields)
    return strawberry.type(cls)


def build_farm_timeseries_type(
    annual_item_type: type, monthly_item_type: type, type_name: str
) -> type:
    """Build the FarmTimeseries wrapper type around the generated annual/monthly types.

    farm_id/state/district/block are request-echo fields, not parquet columns,
    so they're declared directly rather than generated from a schema.

    Args:
        annual_item_type: The generated Strawberry type for one annual row.
        monthly_item_type: The generated Strawberry type for one monthly row.
        type_name: The name of the generated Strawberry type.

    Returns:
        A Strawberry-annotated dataclass with farm_id, state, district, block,
        annual, and monthly fields.
    """
    fields = [
        ("farm_id", str),
        ("state", str),
        ("district", str),
        ("block", str),
        ("annual", list[annual_item_type]),  # type: ignore[valid-type]
        ("monthly", list[monthly_item_type]),  # type: ignore[valid-type]
    ]
    cls = dataclasses.make_dataclass(type_name, fields)
    return strawberry.type(cls)
