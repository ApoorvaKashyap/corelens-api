"""Batched DataLoaders for GraphQL field resolution.

Without batching, a nested query like:

    { tehsils(district: "Godda") { tehsil_id, mws { mws_id } } }

triggers one MWSEntity.where(tehsil=...) call per tehsil in the result — the
classic N+1 problem: if the query returns 10 tehsils, that is 10 separate
parquet scans. With a DataLoader, Strawberry collects every tehsil_id requested
within one GraphQL response and dispatches a single where(tehsil=[...]) call.
core_lens treats admin entity filters as list predicates, so this collapses N
scans into one predicate-pushdown filter regardless of N.

DataLoaders must not be shared across requests — their batching and caching
state would otherwise leak between unrelated GraphQL calls. The loader is
constructed fresh in context.py's get_context(), which Strawberry calls once
per incoming request.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core_lens.entities.mws import MWSEntity
import polars as pl
import polars.selectors as cs
from strawberry.dataloader import DataLoader


async def batch_load_mws_by_tehsil(
    tehsil_ids: list[str], data_root: str
) -> list[list[Any]]:
    """Load MWS units for many tehsils in one predicate-pushdown call.

    The DataLoader contract requires the output list to be the same length and
    order as the input list. Geometry is never fetched here — batched loads are
    for listing children, not for maps; request geometry via the top-level
    mws(...) field if actually needed.

    Args:
        tehsil_ids: Tehsil IDs in the order Strawberry needs results returned.
        data_root: Passed through from GraphQL context (request-scoped).

    Returns:
        One list of generated-MWS instances per input tehsil_id, in matching order.
    """
    from src.app.graphql.generated import MWS_GENERATED, row_to_instance

    assert MWS_GENERATED is not None, (
        "GraphQL types not initialized — call generated.initialize() during lifespan"
    )

    entity = MWSEntity(data_root=data_root)
    tehsil_col = MWS_GENERATED.field_to_column.get("tehsil", "tehsil")
    view = entity.where(**{tehsil_col: list(tehsil_ids)})
    df: pl.DataFrame = view.static.data.collect().with_columns(
        cs.float().fill_nan(None)
    )

    by_tehsil: dict[str, list[Any]] = defaultdict(list)
    for row in df.iter_rows(named=True):
        by_tehsil[row[tehsil_col]].append(row_to_instance(row, MWS_GENERATED))

    return [by_tehsil.get(tid, []) for tid in tehsil_ids]


def make_mws_by_tehsil_loader(data_root: str) -> DataLoader[Any, Any]:
    """Construct a fresh DataLoader for MWS-by-tehsil batching.

    Args:
        data_root: Filesystem path to the core_lens data root directory.

    Returns:
        A DataLoader that batches MWS lookups by tehsil ID.
    """
    return DataLoader(load_fn=lambda keys: batch_load_mws_by_tehsil(keys, data_root))
