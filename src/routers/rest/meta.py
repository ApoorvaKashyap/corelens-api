from fastapi import APIRouter
from loguru import logger
import polars as pl

from src.configs import settings

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/active_tehsils")
def get_active_tehsils() -> dict[str, list[str]]:
    tehsils = (
        pl.scan_csv(f"{settings.data_root}/meta/mws_layer_version.csv")
        .filter(pl.col("Algorithm Version") > 1)
        .collect()["Tehsil"]
        .to_list()
    )
    logger.info("Fetched list of active tehsils")
    return {"tehsils": tehsils}
