import datetime

import strawberry


@strawberry.type
class FarmAnnual:
    """One year of annual-grain data for a single farm."""

    year: int
    area_in_ha: float | None
    aet_annual: float | None
    pet_annual: float | None
    mai_annual: float | None
    kharif_mai: float | None
    kharif_water_stress: bool | None
    kharif_severe_stress: bool | None


@strawberry.type
class FarmMonthly:
    """One month of sub-annual-grain data for a single farm."""

    year: int
    date: datetime.date
    area_in_ha: float | None
    aet: float | None
    pet: float | None
    mai: float | None


@strawberry.type
class FarmTimeseries:
    """Annual + monthly time series for one farm, located by state/district/block."""

    farm_id: str
    state: str
    district: str
    block: str
    annual: list[FarmAnnual]
    monthly: list[FarmMonthly]


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
    farm: str | None
