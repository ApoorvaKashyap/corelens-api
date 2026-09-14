"""Per-request GraphQL context.

The DataLoader is built fresh inside get_context (called once per incoming
request by strawberry-fastapi) rather than at module import time — sharing one
DataLoader across requests would leak batching cache between unrelated callers.
"""

from __future__ import annotations

from strawberry.fastapi import BaseContext

from src.app.graphql.loaders import make_mws_by_tehsil_loader
from src.configs import settings


class Context(BaseContext):
    """Request-scoped GraphQL context carrying per-request DataLoaders.

    Attributes:
        mws_by_tehsil_loader: DataLoader that batches MWS lookups by tehsil ID.
    """

    def __init__(self, data_root: str) -> None:
        super().__init__()
        self.mws_by_tehsil_loader = make_mws_by_tehsil_loader(data_root)


async def get_context() -> Context:
    """Construct a fresh Context for each incoming GraphQL request.

    Returns:
        A new Context instance with freshly-constructed DataLoaders.
    """
    return Context(data_root=settings.data_root)
