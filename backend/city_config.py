# city_config.py
# City-specific configuration for SB-79 analysis

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import geopandas as gpd


@dataclass
class CityConfig:
    """All city-specific parameters needed to run the SB-79 pipeline."""

    # Identity
    name: str  # e.g. "Berkeley" — must match CDTFA_CITY in state geoportal

    # City-specific ArcGIS API endpoints
    parcel_api: str
    zoning_api: str

    # Parcel query field/value for filtering to this city
    # e.g. field="SitusCity", value="Berkeley"
    parcel_city_field: str
    parcel_city_value: str

    # Which zone class prefixes are relevant (residential, commercial, etc.)
    zone_prefix_filter: tuple[str, ...] = ("C-", "R-")

    # Path to the city-specific zoning limits CSV
    zoning_limits_csv: Path = None

    # Transit stop filter — SB-79 defines qualifying stops, but some agencies
    # (e.g. Amtrak, Capitol Corridor) are excluded per the bill's definitions.
    # This is the WHERE clause for the transit stops API.
    transit_stop_where: str = (
        "hqta_type='major_stop_rail' "
        "AND agency_primary!='Capitol Corridor Joint Powers Authority' "
        "AND agency_primary!='Amtrak'"
    )

    # Optional post-processing overlays (e.g. Southside Plan reclassification)
    # Each is a callable: (parcels: GeoDataFrame) -> GeoDataFrame
    overlays: list[Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame]] = field(
        default_factory=list
    )

    def __post_init__(self):
        if self.zoning_limits_csv is None:
            self.zoning_limits_csv = (
                Path(__file__).parent / "data" / "zoning_limits.csv"
            )
