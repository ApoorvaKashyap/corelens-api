"""Runtime type registry for GraphQL schema generation.

Types are generated once during FastAPI lifespan via initialize() rather than
at import time. Lifespan is the right place: it is the earliest point where
settings are confirmed correct, failures surface as startup errors (not import
errors), and the cost of parquet footer reads is paid once before any request
arrives.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.app.graphql.types import GeneratedType

MWS_GENERATED: GeneratedType | None = None
TEHSIL_GENERATED: GeneratedType | None = None
WATERBODY_GENERATED: GeneratedType | None = None
FARM_ANNUAL_GENERATED: GeneratedType | None = None
FARM_MONTHLY_GENERATED: GeneratedType | None = None

MWSConnection: type | None = None
FarmTimeseriesType: type | None = None


def initialize(data_root: str) -> None:
    """Generate and register GraphQL types for all supported entities.

    Reads each entity's schema_profile and a parquet footer (metadata-only,
    no row data). Must be called exactly once during application lifespan
    before any GraphQL request is served.

    Farm annual/monthly types are generated the same way, from one sampled
    block (settings.farm_schema_sample_block) rather than from data_root —
    farm data has no single flat file, it's partitioned per state/district/
    block, so one representative block stands in for "the" schema. Every
    block is expected to share that schema; startup fails loudly if the
    sample block itself doesn't exist, same as any other missing data file.

    Args:
        data_root: Filesystem path to the core_lens data root directory.
    """
    global \
        MWS_GENERATED, \
        TEHSIL_GENERATED, \
        WATERBODY_GENERATED, \
        FARM_ANNUAL_GENERATED, \
        FARM_MONTHLY_GENERATED, \
        MWSConnection, \
        FarmTimeseriesType

    from core_lens.entities.farms import FarmEntity
    from core_lens.entities.mws import MWSEntity
    from core_lens.entities.tehsil import TehsilEntity
    from core_lens.entities.waterbody import WaterbodyEntity

    from src.app.graphql.types import (
        build_connection_type,
        build_farm_timeseries_type,
        build_graphql_type,
        build_temporal_graphql_type,
    )
    from src.configs import settings

    storage_options = settings.aws_storage_options

    MWS_GENERATED = build_graphql_type(
        MWSEntity(data_root=data_root, storage_options=storage_options), "MWS"
    )
    TEHSIL_GENERATED = build_graphql_type(
        TehsilEntity(data_root=data_root, storage_options=storage_options), "Tehsil"
    )
    WATERBODY_GENERATED = build_graphql_type(
        WaterbodyEntity(data_root=data_root, storage_options=storage_options),
        "Waterbody",
    )

    MWSConnection = build_connection_type(
        MWS_GENERATED.strawberry_type, "MWSConnection"
    )

    sample_block_dir = (
        f"{settings.farm_data_root.rstrip('/')}/{settings.farm_schema_sample_block}"
    )
    farm_sample_entity = FarmEntity(
        data_root=sample_block_dir, storage_options=storage_options
    )
    FARM_ANNUAL_GENERATED = build_temporal_graphql_type(
        farm_sample_entity, "FarmAnnual", "annual"
    )
    FARM_MONTHLY_GENERATED = build_temporal_graphql_type(
        farm_sample_entity, "FarmMonthly", "sub_annual"
    )
    FarmTimeseriesType = build_farm_timeseries_type(
        FARM_ANNUAL_GENERATED.strawberry_type,
        FARM_MONTHLY_GENERATED.strawberry_type,
        "FarmTimeseries",
    )


def row_to_instance(
    row: dict[str, Any], generated: GeneratedType, geometry: Any = None
) -> Any:
    """Convert one polars row dict into an instance of a generated Strawberry type.

    Translates real parquet column names to normalized GraphQL field names using
    the generated type's field_to_column mapping. Callers should not pre-translate
    column names — this function owns that step.

    Args:
        row: A row dict with real parquet column names, as from iter_rows(named=True).
        generated: The GeneratedType whose field_to_column map drives translation.
        geometry: Optional geometry value; passed through as-is to the type.

    Returns:
        An instance of generated.strawberry_type.
    """
    kwargs = {
        field_name: row.get(col_name)
        for field_name, col_name in generated.field_to_column.items()
    }
    field_names = {f.name for f in dataclasses.fields(generated.strawberry_type)}
    if "geometry" in field_names:
        kwargs["geometry"] = geometry
    return generated.strawberry_type(**kwargs)
