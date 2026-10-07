"""Query root resolvers for the GraphQL schema.

All resolvers here are scan-and-filter operations that complete in milliseconds.
Compute-heavy operations (aggregation, similarity, change detection, correlation)
belong on a separate REST + async-job surface — mixing them into this schema is
the one thing to actively avoid as this grows.

Filters use entity.where(**filters) directly rather than AoI(...). For pure
attribute retrieval there is no AoI boundary to resolve — where() is entity-level
and needs only the entity's own static file, keeping every field a plain
predicate-pushdown filter with no geometry decode in the retrieval path.

Filter argument names (district, state, tehsil, ...) are the normalized
GraphQL-facing names. _to_real_columns translates them back to the real,
possibly differently-cased, parquet column names before passing to where().
"""

from __future__ import annotations

from typing import Any, Optional

from core_lens.entities.farms import FarmEntity
from core_lens.entities.mws import MWSEntity
from core_lens.entities.tehsil import TehsilEntity
from core_lens.entities.waterbody import WaterbodyEntity
from core_lens.utils.spatial import point_in_entities
from loguru import logger
import polars as pl
import polars.selectors as cs
from strawberry.types import Info

from src.app.graphql.utils import EntityFilterInput, EntityResult
from src.configs import settings

_SPATIAL_ENTITIES = [
    MWSEntity(settings.data_root, storage_options=settings.aws_storage_options),
    TehsilEntity(settings.data_root, storage_options=settings.aws_storage_options),
    WaterbodyEntity(settings.data_root, storage_options=settings.aws_storage_options),
]
# FarmEntity is intentionally excluded: farm boundaries are partitioned by
# state/district/block on disk (see resolve_farm_timeseries), so there is no
# single flat farms dataset to point-in-polygon scan against.


def _wants_geometry(info: Info, field_name: str = "geometry") -> bool:
    """Check whether the client's query selected the geometry field.

    Only runs Result.with_geometry() (a real parquet geometry column scan)
    when the client actually asked for that field.

    Args:
        info: Strawberry resolver info carrying the query's field selections.
        field_name: The field name to check for; defaults to "geometry".

    Returns:
        True if the client selected the field, False otherwise.
    """
    for selection in info.selected_fields:
        for field in selection.selections:
            if getattr(field, "name", None) == field_name:
                return True
    return False


def _to_real_columns(generated: Any, **kwargs: Any) -> dict[str, Any]:
    """Translate normalized GraphQL argument names to real parquet column names.

    Uses the same field_to_column map that built the type, so a filter argument
    and the field it constrains are guaranteed to reference the same column.

    Args:
        generated: The GeneratedType whose field_to_column map is used.
        **kwargs: Normalized GraphQL argument names and their values.

    Returns:
        A dict of real parquet column names to filter values, with None values dropped.
    """
    real: dict[str, Any] = {}
    for field_name, value in kwargs.items():
        if value is None:
            continue
        col = generated.field_to_column.get(field_name, field_name)
        real[col] = value
    return real


def resolve_entities(filter: EntityFilterInput) -> EntityResult:
    """Resolve the entity IDs containing a given coordinate point.

    Args:
        filter: Filter input carrying the latitude/longitude coordinates.

    Returns:
        EntityResult with the entity IDs (mws, tehsil, waterbody) at that point.
        Fields are None when the point falls outside all geometries of that entity.
    """
    latlon = {
        "lat": filter.coordinates.latitude,
        "lon": filter.coordinates.longitude,
    }
    result = point_in_entities(latlon, _SPATIAL_ENTITIES)
    logger.info("Fetched entity details for the coordinates")
    return EntityResult(
        mws=result.get("MWSEntity"),
        tehsil=result.get("TehsilEntity"),
        waterbody=result.get("WaterbodyEntity"),
        farm=result.get("FarmEntity"),
    )


def resolve_mws(
    info: Info,
    district: Optional[str] = None,
    state: Optional[str] = None,
    tehsil: Optional[str] = None,
    mws_id: Optional[list[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Resolve a paginated list of MWS units with optional attribute filters.

    Slices after full materialisation — fine for current traffic, but if filters
    are empty or match a huge admin area, this reads the whole static file before
    paginating. Worth pushing limit/offset into the underlying scan once retrieval
    traffic is real (needs a small core_lens change: a View.static variant that
    accepts a row limit before .collect()).

    Args:
        info: Strawberry resolver info for field selection inspection.
        district: Optional district filter.
        state: Optional state filter.
        tehsil: Optional tehsil filter.
        mws_id: Optional list of MWS IDs to filter by.
        limit: Maximum number of items to return.
        offset: Number of items to skip.

    Returns:
        An MWSConnection with items, total_count, limit, and offset.
    """
    from src.app.graphql.generated import MWS_GENERATED, MWSConnection, row_to_instance

    assert MWS_GENERATED is not None
    assert MWSConnection is not None

    filters = _to_real_columns(
        MWS_GENERATED, district=district, state=state, tehsil=tehsil, mws_id=mws_id
    )

    entity = MWSEntity(
        data_root=settings.data_root, storage_options=settings.aws_storage_options
    )
    view = entity.where(**filters) if filters else entity.where()
    result = view.static

    if _wants_geometry(info):
        result = result.with_geometry()

    df: pl.DataFrame = result.data.collect().with_columns(cs.float().fill_nan(None))
    total = df.height
    page = df.slice(offset, limit)

    geom_present = "geometry" in page.columns
    items = [
        row_to_instance(
            row, MWS_GENERATED, geometry=row.get("geometry") if geom_present else None
        )
        for row in page.iter_rows(named=True)
    ]
    return MWSConnection(items=items, total_count=total, limit=limit, offset=offset)


def resolve_tehsils(
    info: Info,
    district: Optional[str] = None,
    state: Optional[str] = None,
    tehsil_id: Optional[list[str]] = None,
) -> list[Any]:
    """Resolve a list of tehsils with optional attribute filters.

    Args:
        info: Strawberry resolver info for field selection inspection.
        district: Optional district filter.
        state: Optional state filter.
        tehsil_id: Optional list of tehsil IDs to filter by.

    Returns:
        A list of generated Tehsil instances.
    """
    from src.app.graphql.generated import TEHSIL_GENERATED, row_to_instance

    assert TEHSIL_GENERATED is not None

    filters = _to_real_columns(
        TEHSIL_GENERATED, district=district, state=state, tehsil_id=tehsil_id
    )

    entity = TehsilEntity(
        data_root=settings.data_root, storage_options=settings.aws_storage_options
    )
    view = entity.where(**filters) if filters else entity.where()
    result = view.static

    if _wants_geometry(info):
        result = result.with_geometry()

    df: pl.DataFrame = result.data.collect().with_columns(cs.float().fill_nan(None))
    geom_present = "geometry" in df.columns
    return [
        row_to_instance(
            row,
            TEHSIL_GENERATED,
            geometry=row.get("geometry") if geom_present else None,
        )
        for row in df.iter_rows(named=True)
    ]


def resolve_waterbody(
    info: Info,
    district: Optional[str] = None,
    state: Optional[str] = None,
    waterbody_id: Optional[list[str]] = None,
) -> list[Any]:
    """Resolve a list of waterbodies with optional attribute filters."""
    from src.app.graphql.generated import WATERBODY_GENERATED, row_to_instance

    assert WATERBODY_GENERATED is not None

    filters = _to_real_columns(
        WATERBODY_GENERATED, district=district, state=state, waterbody_id=waterbody_id
    )

    entity = WaterbodyEntity(
        data_root=settings.data_root, storage_options=settings.aws_storage_options
    )
    view = entity.where(**filters) if filters else entity.where()
    result = view.static

    if _wants_geometry(info):
        result = result.with_geometry()

    df: pl.DataFrame = result.data.collect().with_columns(cs.float().fill_nan(None))
    geom_present = "geometry" in df.columns
    return [
        row_to_instance(
            row,
            WATERBODY_GENERATED,
            geometry=row.get("geometry") if geom_present else None,
        )
        for row in df.iter_rows(named=True)
    ]


def resolve_farm_timeseries(state: str, district: str, block: str, farm_id: str) -> Any:
    """Resolve annual + monthly time series for one farm.

    Farm boundary data is partitioned on disk as
    ``<farm_data_root>/<state>/<district>/<block>/`` (each block folder is its
    own FarmEntity data_root, per whatever static/annual/sub_annual filenames
    the installed core_lens FarmEntity declares) rather than living under one
    flat data_root like the other entities, so a fresh FarmEntity is built per
    request from the caller-supplied location.

    Args:
        state: State name, matching the partition folder name (e.g. "rajasthan").
        district: District name, matching the partition folder name.
        block: Block/tehsil name, matching the partition folder name.
        farm_id: The farm's unique id, as found in the static file.

    Returns:
        A FarmTimeseries (generated type) with the annual and monthly rows for
        that farm_id. Both lists are empty if the farm_id has no matching rows.
    """
    from src.app.graphql.generated import (
        FARM_ANNUAL_GENERATED,
        FARM_MONTHLY_GENERATED,
        FarmTimeseriesType,
        row_to_instance,
    )

    assert FARM_ANNUAL_GENERATED is not None
    assert FARM_MONTHLY_GENERATED is not None
    assert FarmTimeseriesType is not None

    block_dir = f"{settings.farm_data_root.rstrip('/')}/{state}/{district}/{block}"
    entity = FarmEntity(
        data_root=block_dir, storage_options=settings.aws_storage_options
    )
    view = entity.where(farm_id=farm_id)

    annual_df = view.annual.df()

    # The sub_annual file carries both a "year" (int) and a "date" (datetime)
    # column. core_lens's sub_annual time-column auto-detection matches "year"
    # first and then treats it as a date, which crashes. Scan directly instead
    # of going through view.sub_annual until that detection is fixed upstream.
    monthly_df = (
        pl.scan_parquet(
            entity._resolve(entity.sub_annual_path),
            storage_options=settings.aws_storage_options,
        )
        .filter(pl.col("farm_id") == farm_id)
        .collect()
    )

    annual = [
        row_to_instance(row, FARM_ANNUAL_GENERATED)
        for row in annual_df.iter_rows(named=True)
    ]
    monthly = [
        row_to_instance(row, FARM_MONTHLY_GENERATED)
        for row in monthly_df.iter_rows(named=True)
    ]

    logger.info(
        "Fetched farm timeseries for {} ({} annual rows, {} monthly rows)",
        farm_id,
        len(annual),
        len(monthly),
    )

    return FarmTimeseriesType(
        farm_id=farm_id,
        state=state,
        district=district,
        block=block,
        annual=annual,
        monthly=monthly,
    )
