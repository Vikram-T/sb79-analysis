# berkeley.py
# Berkeley-specific configuration and overlays for the SB-79 pipeline.

import geopandas as gpd
import pandas as pd
import requests
from pathlib import Path

from city_config import CityConfig
from geo_utils import ensure_crs, project_to_utm, validate_api_response
from pipeline import gather_city_data, process_city_data, export_city_results

# =============================================================================
# Berkeley-specific API URLs
# =============================================================================

BERKELEY_PARCEL_API = "https://gis.cityofberkeley.info/arcgis3/rest/services/Public/GISPortal/MapServer/1/query"
BERKELEY_ZONING_API = "https://gis.cityofberkeley.info/arcgis3/rest/services/Public/Portal_Planning/MapServer/7/query"
BERKELEY_SOUTHSIDE_PLAN_API = "https://gis.cityofberkeley.info/arcgis3/rest/services/Public/Portal_Planning/MapServer/13/query"


# =============================================================================
# Berkeley-specific overlay functions
# =============================================================================

def get_southside_plan_boundary(api_url=None):
    """
    Fetch the Southside Plan boundary from Berkeley's GIS.

    The Southside Plan area has different zoning rules for R-3 parcels:
    - Inside Southside: 45ft height limit, 100% lot coverage, 60 du/acre min density
    - Outside Southside: 35ft height limit, 30-45% lot coverage, no min density

    Args:
        api_url: URL of the Southside Plan API endpoint (defaults to BERKELEY_SOUTHSIDE_PLAN_API)

    Returns:
        GeoDataFrame containing the Southside Plan boundary polygon, or None if error
    """
    if api_url is None:
        api_url = BERKELEY_SOUTHSIDE_PLAN_API

    params = {
        'where': '1=1',
        'outFields': '*',
        'outSR': '4326',
        'f': 'geojson'
    }

    try:
        response = requests.post(api_url, data=params)
        is_valid, response_json, error_msg = validate_api_response(response)

        if not is_valid:
            print(f"Error fetching Southside Plan boundary: {error_msg}")
            return None

        if 'features' not in response_json or len(response_json['features']) == 0:
            print("No Southside Plan boundary found")
            return None

        boundary = gpd.GeoDataFrame.from_features(response_json['features'])
        boundary = ensure_crs(boundary)
        print("✓ Fetched Southside Plan boundary")
        return boundary

    except Exception as e:
        print(f"Error fetching Southside Plan boundary: {e}")
        return None

def reclassify_r3_in_southside(parcels, southside_boundary):
    """
    Reclassify R-3 parcels inside the Southside Plan area to R-3S.

    R-3 parcels have different development standards inside vs outside
    the Southside Plan area:
    - R-3S (Southside): 45ft height, 100% lot coverage, 60 du/acre min density
    - R-3 (elsewhere): 35ft height, 30-45% lot coverage, no min density

    Args:
        parcels: GeoDataFrame containing parcel data with ZONECLASS column
        southside_boundary: GeoDataFrame containing the Southside Plan boundary

    Returns:
        GeoDataFrame with ZONECLASS updated to R-3S for R-3 parcels in Southside Plan
    """
    if parcels is None or southside_boundary is None:
        return parcels

    parcels = parcels.copy()

    # Find R-3 parcels (but not R-3H - hillside overlay has its own rules)
    r3_mask = parcels['ZONECLASS'] == 'R-3'

    if r3_mask.sum() == 0:
        print("✓ No R-3 parcels found - Southside reclassification not needed")
        return parcels

    # Ensure both have CRS set and project to UTM for accurate spatial operations
    parcels = ensure_crs(parcels)
    southside_boundary = ensure_crs(southside_boundary)
    parcels_projected = project_to_utm(parcels)
    boundary_projected = project_to_utm(southside_boundary)

    # Combine all boundary polygons into one (in case there are multiple)
    combined_boundary = boundary_projected.union_all()

    # Check which R-3 parcel centroids are inside the Southside Plan boundary
    r3_indices = parcels[r3_mask].index
    reclassified_count = 0

    for idx in r3_indices:
        centroid = parcels_projected.loc[idx].geometry.centroid
        if centroid.within(combined_boundary):
            parcels.loc[idx, 'ZONECLASS'] = 'R-3S'
            parcels.loc[idx, 'ZONEDESC'] = 'Multiple Family Residential (Southside Plan)'
            reclassified_count += 1

    remaining_r3 = (parcels['ZONECLASS'] == 'R-3').sum()
    print(f"✓ Reclassified {reclassified_count} R-3 parcels to R-3S (Southside Plan)")
    print(f"  {remaining_r3} R-3 parcels remain outside Southside Plan")

    return parcels

def make_southside_overlay(api_url):
    """
    Factory that returns an overlay callable for Southside Plan R-3 reclassification.

    Args:
        api_url: URL of the Southside Plan API endpoint

    Returns:
        Callable[[GeoDataFrame], GeoDataFrame] that fetches the boundary and reclassifies R-3 → R-3S
    """
    def overlay(parcels):
        southside_boundary = get_southside_plan_boundary(api_url)
        if southside_boundary is not None:
            parcels = reclassify_r3_in_southside(parcels, southside_boundary)
        return parcels
    return overlay


# =============================================================================
# Berkeley-specific data loaders
# =============================================================================

def load_zoning_limits(zoning_limits_csv=None):
    """
    Load Berkeley zoning limits from CSV.

    Args:
        zoning_limits_csv: Path to the zoning limits CSV (defaults to data/zoning_limits.csv)

    Returns:
        dict with 'height' and 'max_density' dicts mapping ZONECLASS to values
    """
    csv_path = zoning_limits_csv or Path(__file__).parent / 'data' / 'zoning_limits.csv'
    df = pd.read_csv(csv_path, skipinitialspace=True)
    # Strip whitespace from column names and values
    df.columns = df.columns.str.strip()
    df['zoneclass'] = df['zoneclass'].str.strip()
    return {
        'height': dict(zip(df['zoneclass'], df['height_ft'])),
        'max_density': dict(zip(df['zoneclass'], df['max_density_du_acre']))
    }


def add_zoning_limits(parcels, zoning_limits):
    """
    Add Berkeley current zoning height, max density, and zoned capacity to parcels.

    Args:
        parcels: GeoDataFrame with ZONECLASS and LotSize columns
        zoning_limits: dict with 'height' and 'max_density' dicts mapping ZONECLASS to values

    Returns:
        GeoDataFrame with CurrentHeightLimit, CurrentMaxDensity, and CurrentZonedCapacity columns added
    """
    if parcels is None or len(parcels) == 0:
        return parcels

    parcels['CurrentHeightLimit'] = parcels['ZONECLASS'].map(zoning_limits['height'])
    parcels['CurrentMaxDensity'] = parcels['ZONECLASS'].map(zoning_limits['max_density'])

    # Calculate current zoned capacity (max density * lot size in acres)
    SQFT_PER_ACRE = 43560
    max_density = parcels['CurrentMaxDensity']
    lot_acres = parcels['LotSize'].fillna(0) / SQFT_PER_ACRE
    has_density = max_density.notna() & (max_density != 0)
    parcels['CurrentZonedCapacity'] = pd.Series(index=parcels.index, dtype=float)
    parcels.loc[has_density, 'CurrentZonedCapacity'] = lot_acres[has_density] * max_density[has_density]

    has_height = parcels['CurrentHeightLimit'].notna().sum()
    has_density_count = parcels['CurrentMaxDensity'].notna().sum()
    print(f"\n✓ Added zoning limits: {has_height}/{len(parcels)} have height, {has_density_count}/{len(parcels)} have max density")

    return parcels


# =============================================================================
# Berkeley-specific configuration
# =============================================================================

BERKELEY_CONFIG = CityConfig(
    name="Berkeley",
    parcel_api=BERKELEY_PARCEL_API,
    zoning_api=BERKELEY_ZONING_API,
    parcel_city_field="SitusCity",
    parcel_city_value="Berkeley",
    zone_prefix_filter=("C-", "R-"),
    overlays=[make_southside_overlay(BERKELEY_SOUTHSIDE_PLAN_API)],
)


def main():
    data = gather_city_data(BERKELEY_CONFIG)
    if data is None:
        return
    parcels = process_city_data(BERKELEY_CONFIG, data)
    zoning_limits = load_zoning_limits(BERKELEY_CONFIG.zoning_limits_csv)
    parcels = add_zoning_limits(parcels, zoning_limits)
    export_city_results(BERKELEY_CONFIG.name, data, parcels)


if __name__ == "__main__":
    main()
