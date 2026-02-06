# pipeline.py
# Generic SB-79 analysis pipeline — works for any city given a CityConfig.

import geopandas as gpd
import pandas as pd
import requests
import urllib
import json
from dataclasses import dataclass
from pathlib import Path

from city_config import CityConfig
from config import (
    CITY_BOUNDARIES_URL, HIGH_QUALITY_TRANSIT_STOPS_URL,
    DENSITY_200FT, DENSITY_QUARTER_MILE, DENSITY_HALF_MILE, USE_LOCAL_DATA
)
from data_store import (
    save_layer, load_layer,
    LAYER_CITY_BOUNDARY, LAYER_TRANSIT_STOPS, LAYER_ZONING, LAYER_PARCELS
)
from geo_utils import (
    ensure_crs, project_to_utm, project_to_wgs84,
    polygon_to_esri_geometry, point_to_esri_geometry,
    fetch_all_paginated,
    TIER_200FT, TIER_QUARTER_MILE, TIER_HALF_MILE,
)


@dataclass
class CityData:
    city_boundary: gpd.GeoDataFrame
    transit_stops: gpd.GeoDataFrame
    zoning_districts: gpd.GeoDataFrame | None
    parcels: gpd.GeoDataFrame


def get_city_boundary(city_name, buffer_miles=0):
    """
    Fetch city boundary from California State Geoportal.

    Args:
        city_name: Name of the city to fetch boundary for
        buffer_miles: Optional distance in miles to expand the boundary (default: 0, no expansion).
                      Useful for capturing transit stops outside the city whose radius overlaps
                      the city boundary. Typical use case: 0.6 miles.

    Returns:
        GeoDataFrame containing the city boundary, or None if error
    """
    city_boundary_params = {
        'where': f"CDTFA_CITY='{city_name}'",
        'outFields': 'CDTFA_CITY',
        'f': 'geojson'
    }

    url = f"{CITY_BOUNDARIES_URL}?{urllib.parse.urlencode(city_boundary_params)}"

    try:
        city_geojson = gpd.read_file(url)

        if len(city_geojson) == 0:
            print(f"No boundary found for {city_name}")
            return None

        # Apply buffer if specified
        if buffer_miles > 0:
            # Convert miles to meters (1 mile = 1609.344 meters)
            buffer_meters = buffer_miles * 1609.344

            # Project to UTM for accurate distance calculations
            city_projected = project_to_utm(city_geojson)
            city_projected['geometry'] = city_projected.geometry.buffer(buffer_meters)
            city_geojson = project_to_wgs84(city_projected)

            print(f"Applied {buffer_miles}-mile buffer to {city_name} boundary")

        return city_geojson
    except Exception as e:
        print(f"Error fetching city boundary: {e}")
        return None

def get_transit_stops(city_boundary, transit_stop_where="hqta_type='major_stop_rail' AND agency_primary!='Capitol Corridor Joint Powers Authority' AND agency_primary!='Amtrak'"):
    """
    Fetch high quality transit stops within a city boundary from California State Geoportal.

    Args:
        city_boundary: GeoDataFrame containing the city boundary
        transit_stop_where: WHERE clause to filter transit stops

    Returns:
        GeoDataFrame containing transit stops, or None if error
    """
    transit_params = {
        'where': transit_stop_where,
        'outFields': 'OBJECTID,agency_primary,hqta_type,stop_id,route_id,hqta_details',
        'geometry': json.dumps(polygon_to_esri_geometry(city_boundary)),
        'geometryType': 'esriGeometryPolygon',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'outSR': '4326',
        'f': 'geojson'
    }

    try:
        response = requests.post(HIGH_QUALITY_TRANSIT_STOPS_URL, data=transit_params)

        if response.status_code != 200 or 'error' in response.json():
            print(f"Error fetching transit stops: {response.json()}")
            return None

        transit_stops = gpd.GeoDataFrame.from_features(response.json()['features'])
        print(f"Filtering out stops with the same Stop ID {len(transit_stops)} -> {len(transit_stops['stop_id'].unique())} ")
        transit_stops = transit_stops.drop_duplicates(subset='stop_id', keep='first')
        return transit_stops
    except Exception as e:
        print(f"Error fetching transit stops: {e}")
        return None

def get_parcels_near_transit_stop(parcel_api, stop_geometry, distance_miles, city_name, parcel_city_field="SitusCity"):
    """
    Fetch all parcels within a specified distance from a single transit stop.

    NOTE: We query each stop individually rather than using multipoint geometry due to an
    ArcGIS REST API pagination bug. When using multipoint geometry with pagination parameters
    (resultOffset/resultRecordCount), if ANY point in the multipoint has zero results within
    the buffer distance, the entire query returns 0 results. This was causing issues with
    transit stops outside the city boundary (e.g., Rockridge BART) that have no Berkeley
    parcels within 200ft or 0.25mi. By querying each stop individually, pagination works
    correctly and we get all parcels.

    Args:
        parcel_api: URL of the parcel API endpoint
        stop_geometry: Point geometry of the transit stop
        distance_miles: Distance in miles to search around transit stop
        city_name: Name of the city to filter parcels by (e.g., 'Berkeley')
        parcel_city_field: Field name for city filtering (e.g., 'SitusCity')

    Returns:
        List of parcel features (GeoJSON), or empty list if none found
    """
    parcel_params = {
        'where': f"{parcel_city_field}='{city_name}'",
        'geometry': json.dumps(point_to_esri_geometry(stop_geometry)),
        'geometryType': 'esriGeometryPoint',
        'distance': distance_miles,
        'units': 'esriSRUnit_StatuteMile',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'outFields': '*',
        'outSR': '4326',
        'f': 'geojson'
    }

    return fetch_all_paginated(parcel_api, parcel_params, verbose=False)


def get_tier1_parcels(parcel_api, transit_stops, city_name, parcel_city_field="SitusCity"):
    """
    Get all Tier 1 SB-79 parcels with zone tagging (200ft, quarter_mile, half_mile).

    Queries each transit stop individually to avoid ArcGIS pagination bug with multipoint.
    Uses API's buffer on parcel polygons for accurate zone assignment.

    Args:
        parcel_api: URL of the parcel API endpoint
        transit_stops: GeoDataFrame containing transit stop data
        city_name: Name of the city to filter parcels by (e.g., 'Berkeley')
        parcel_city_field: Field name for city filtering (e.g., 'SitusCity')

    Returns:
        GeoDataFrame with all parcels tagged with their tier1_zone, or empty GeoDataFrame if none
    """
    # Distance thresholds in miles (innermost to outermost)
    zones = [
        (TIER_200FT, 200 / 5280),  # ~0.0379 miles
        (TIER_QUARTER_MILE, 0.25),
        (TIER_HALF_MILE, 0.5),
    ]

    zone_parcels = {}

    # Query each zone for each stop
    for zone_tag, distance_miles in zones:
        print(f"\nFetching {zone_tag} parcels ({distance_miles:.4f} miles):")
        all_parcels_list = []

        for i, (_, stop) in enumerate(transit_stops.iterrows()):
            stop_parcels = get_parcels_near_transit_stop(
                parcel_api, stop.geometry, distance_miles, city_name, parcel_city_field
            )
            count = len(stop_parcels) if stop_parcels else 0
            print(f"   Stop {i + 1}/{len(transit_stops)}: {count} parcels")
            if stop_parcels:
                all_parcels_list.extend(stop_parcels)

        if all_parcels_list:
            parcels = gpd.GeoDataFrame.from_features(all_parcels_list)
            parcels = parcels.drop_duplicates(subset=['APN'], keep='first')
            parcels['tier1_zone'] = zone_tag
            zone_parcels[zone_tag] = parcels
            print(f"✓ Found {len(parcels)} unique {zone_tag} parcels")
        else:
            zone_parcels[zone_tag] = gpd.GeoDataFrame()
            print(f"No {zone_tag} parcels found")

    # Get parcels for each zone
    two_hundred_ft_parcels = zone_parcels[TIER_200FT]
    quarter_mile_parcels = zone_parcels[TIER_QUARTER_MILE]
    half_mile_parcels = zone_parcels[TIER_HALF_MILE]

    # Filter to get exclusive zones (innermost zone takes priority)
    two_hundred_ft_objectids = set(two_hundred_ft_parcels['OBJECTID']) if len(two_hundred_ft_parcels) > 0 else set()
    quarter_mile_objectids = set(quarter_mile_parcels['OBJECTID']) if len(quarter_mile_parcels) > 0 else set()

    quarter_mile_only = quarter_mile_parcels[~quarter_mile_parcels['OBJECTID'].isin(two_hundred_ft_objectids)] if len(quarter_mile_parcels) > 0 else quarter_mile_parcels
    half_mile_only = half_mile_parcels[~half_mile_parcels['OBJECTID'].isin(quarter_mile_objectids)] if len(half_mile_parcels) > 0 else half_mile_parcels

    # Combine all zones
    zones_to_combine = [df for df in [two_hundred_ft_parcels, quarter_mile_only, half_mile_only] if len(df) > 0]
    if not zones_to_combine:
        return gpd.GeoDataFrame()

    parcels = gpd.GeoDataFrame(pd.concat(zones_to_combine, ignore_index=True))

    # Print Results
    two_hundred_ft_count = len(parcels[parcels['tier1_zone'] == TIER_200FT])
    quarter_count = len(parcels[parcels['tier1_zone'] == TIER_QUARTER_MILE])
    half_count = len(parcels[parcels['tier1_zone'] == TIER_HALF_MILE])

    print("\n✓ Tier 1 Parcel Summary:")
    print(f"  - 200ft zone (0-200ft): {two_hundred_ft_count} parcels")
    print(f"  - Quarter mile zone (200ft-0.25mi): {quarter_count} parcels")
    print(f"  - Half mile zone (0.25-0.5mi): {half_count} parcels")
    print(f"  - Total: {len(parcels)} parcels")

    return parcels

def get_zoning_districts(city_boundary, zoning_api):
    """
    Fetch all zoning districts within a city boundary.

    Args:
        city_boundary: GeoDataFrame containing the city boundary
        zoning_api: URL of the zoning API endpoint

    Returns:
        GeoDataFrame containing zoning districts, or None if error
    """
    zoning_params = {
        'where': '1=1',
        'geometry': json.dumps(polygon_to_esri_geometry(city_boundary)),
        'geometryType': 'esriGeometryPolygon',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'outFields': 'OBJECTID,ZONECLASS,ZONEDESC',
        'outSR': '4326',
        'f': 'geojson'
    }

    zones_list = fetch_all_paginated(zoning_api, zoning_params)

    if not zones_list:
        print("No zoning districts found")
        return None

    zones = gpd.GeoDataFrame.from_features(zones_list)
    zones = ensure_crs(zones)
    print(f"✓ Found {len(zones)} zoning districts")
    return zones

def add_zoning_to_parcels(parcels, zoning_districts):
    """
    Add zoning information to parcels using spatial join.

    Args:
        parcels: GeoDataFrame containing parcel data
        zoning_districts: GeoDataFrame containing zoning data

    Returns:
        GeoDataFrame with ZONECLASS and ZONEDESC columns added
    """
    if parcels is None or zoning_districts is None:
        return parcels

    # Ensure both have CRS set and project to UTM for accurate centroid calculation
    parcels = ensure_crs(parcels)
    zoning_districts = ensure_crs(zoning_districts)
    parcels_projected = project_to_utm(parcels)
    zoning_projected = project_to_utm(zoning_districts)

    # Create centroids in projected CRS for accurate zone matching
    parcels_with_centroids = parcels_projected.copy()
    parcels_with_centroids['centroid'] = parcels_with_centroids.geometry.centroid
    parcels_with_centroids = parcels_with_centroids.set_geometry('centroid')

    # Spatial join to find which zone each parcel centroid falls in
    joined = gpd.sjoin(
        parcels_with_centroids,
        zoning_projected[['ZONECLASS', 'ZONEDESC', 'geometry']],
        how='left',
        predicate='within'
    )

    # Restore original geometry (in WGS84) and drop centroid column
    joined = joined.set_geometry(parcels.geometry)
    joined = joined.drop(columns=['centroid', 'index_right'], errors='ignore')
    joined = ensure_crs(joined)

    # Handle duplicates (parcel centroid in multiple zones - take first)
    if 'APN' in joined.columns:
        joined = joined.drop_duplicates(subset=['APN'], keep='first')

    # Report stats
    matched = joined['ZONECLASS'].notna().sum()
    unmatched = joined['ZONECLASS'].isna().sum()
    total = len(joined)
    print(f"✓ Added zoning info: {matched}/{total} parcels matched to zones")

    # Print parcels without zones
    if unmatched > 0:
        print(f"\n⚠ {unmatched} parcels have no zone assigned:")
        no_zone_parcels = joined[joined['ZONECLASS'].isna()]
        for _, parcel in no_zone_parcels.iterrows():
            apn = parcel.get('APN', 'N/A')
            address = parcel.get('SitusAddress', 'N/A')
            tier = parcel.get('tier1_zone', 'N/A')
            print(f"  - APN: {apn}, Address: {address}, Tier: {tier}")

    return joined

def add_potential_and_net_capacity(parcels):
    """
    Calculate potential unit capacity for each parcel based on tier zone and lot size.
    Use this to then calculate the net capacity which is Potential - Existing.
    This number cannot be negative though and will default to 0

    Args:
        parcels: GeoDataFrame containing parcel data with 'tier1_zone' and 'LotSize' columns

    Returns:
        GeoDataFrame with 'PotentialCapacity' column added
    """
    if parcels is None:
        return parcels

    # Conversion: 1 acre = 43,560 square feet
    SQFT_PER_ACRE = 43560

    # Map tier zones to density limits
    density_map = {
        TIER_200FT: DENSITY_200FT,
        TIER_QUARTER_MILE: DENSITY_QUARTER_MILE,
        TIER_HALF_MILE: DENSITY_HALF_MILE
    }

    # Vectorized: map tier zone to density, then multiply by lot size in acres
    lot_acres = parcels['LotSize'].fillna(0) / SQFT_PER_ACRE
    density = parcels['tier1_zone'].map(density_map).fillna(0)
    parcels['PotentialCapacity'] = lot_acres * density

    # Calculating net capacity based on SB-79 65912.161. (a) (1)
    # Essentially we take (potential capacity based on distance from transit) - (existing capacity) = net_capacity
    # This incentivizes development on parking lots over places that already have housing
    parcels['NetIncreaseCapacity'] = (parcels['PotentialCapacity'] - parcels['Units'].fillna(0)).clip(lower=0)

    # Print summary
    print(f"\n✓ Calculated potential capacity for {len(parcels)} parcels")
    print(f"  Using densities: 200ft={DENSITY_200FT}, quarter_mile={DENSITY_QUARTER_MILE}, half_mile={DENSITY_HALF_MILE} units/acre")

    return parcels



def load_sb79_limits():
    """
    Load SB-79 minimum height limits from CSV.

    Returns:
        dict mapping (tier, distance) to height_ft_min
    """
    csv_path = Path(__file__).parent / 'data' / 'sb79_limits.csv'
    df = pd.read_csv(csv_path, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    df['tier'] = df['tier'].str.strip()
    df['distance'] = df['distance'].str.strip()
    # Map distance names to tier1_zone values
    distance_map = {
        'adjacent': '200ft',
        'quarter_mile': 'quarter_mile',
        'half_mile': 'half_mile'
    }
    result = {}
    for _, row in df.iterrows():
        zone_key = distance_map.get(row['distance'])
        if zone_key and row['tier'] == 'tier1':
            result[zone_key] = row['height_ft_min']
    return result


def add_zoning_and_sb79_limits(parcels, zoning_limits):
    """
    Add current zoning limits and SB-79 minimums to parcels.

    Args:
        parcels: GeoDataFrame with ZONECLASS, tier1_zone, and LotSize columns
        zoning_limits: dict with 'height' and 'max_density' dicts mapping ZONECLASS to values

    Returns:
        GeoDataFrame with CurrentHeightLimit, SB79HeightLimit, and CurrentMaxDensity columns added
    """
    if parcels is None or len(parcels) == 0:
        return parcels

    sb79_limits = load_sb79_limits()

    # Add current height limit based on zoning
    parcels['CurrentHeightLimit'] = parcels['ZONECLASS'].map(zoning_limits['height'])

    # Add SB-79 minimum height based on tier zone
    parcels['SB79HeightLimit'] = parcels['tier1_zone'].map(sb79_limits)

    # Add current max density based on zoning
    parcels['CurrentMaxDensity'] = parcels['ZONECLASS'].map(zoning_limits['max_density'])

    # Calculate current zoned capacity (max density * lot size in acres)
    # Only for parcels that have a max density limit
    SQFT_PER_ACRE = 43560

    # Vectorized: where max density exists and is non-zero, compute capacity
    max_density = parcels['CurrentMaxDensity']
    lot_acres = parcels['LotSize'].fillna(0) / SQFT_PER_ACRE
    has_density = max_density.notna() & (max_density != 0)
    parcels['CurrentZonedCapacity'] = pd.Series(index=parcels.index, dtype=float)
    parcels.loc[has_density, 'CurrentZonedCapacity'] = lot_acres[has_density] * max_density[has_density]

    # Report stats
    has_height = parcels['CurrentHeightLimit'].notna().sum()
    has_density = parcels['CurrentMaxDensity'].notna().sum()
    has_sb79 = parcels['SB79HeightLimit'].notna().sum()
    print(f"\n✓ Added zoning limits: {has_height}/{len(parcels)} have height, {has_density}/{len(parcels)} have max density, {has_sb79}/{len(parcels)} have SB-79 height")

    return parcels


def filter_zero_lotsize_parcels(parcels):
    """
    Filter out parcels with LotSize = 0.

    Args:
        parcels: GeoDataFrame containing parcel data with 'LotSize' column

    Returns:
        GeoDataFrame with parcels where LotSize > 0
    """
    if parcels is None:
        return None

    initial_count = len(parcels)
    filtered_parcels = parcels[parcels['LotSize'] > 0]
    removed_count = initial_count - len(filtered_parcels)

    print(f"\n✓ Filtered out {removed_count} parcels with LotSize = 0")
    print(f"  Remaining parcels: {len(filtered_parcels)}")

    return filtered_parcels

def filter_parcels_with_same_centroid(parcels):
    """
    Find parcels that share the same centroid coordinates and filter out those with BLDSQFTTAXABLE > 0.

    Args:
        parcels: GeoDataFrame containing parcel data

    Returns:
        GeoDataFrame with parcels filtered (removes parcels with BLDSQFTTAXABLE > 0 that share centroids)
    """
    if parcels is None or len(parcels) == 0:
        print("No parcels to analyze")
        return parcels

    # Ensure CRS is set and project to UTM for accurate centroid calculation
    parcels_copy = ensure_crs(parcels.copy())
    parcels_projected = project_to_utm(parcels_copy)

    # Calculate centroids in projected CRS
    parcels_projected['centroid'] = parcels_projected.geometry.centroid
    parcels_projected['centroid_x'] = parcels_projected['centroid'].x
    parcels_projected['centroid_y'] = parcels_projected['centroid'].y

    # Group by centroid coordinates (rounded to avoid floating point issues)
    # Using 2 decimal places for meters precision (0.01m = 1cm)
    parcels_projected['centroid_x_rounded'] = parcels_projected['centroid_x'].round(2)
    parcels_projected['centroid_y_rounded'] = parcels_projected['centroid_y'].round(2)

    # Find duplicates
    grouped = parcels_projected.groupby(['centroid_x_rounded', 'centroid_y_rounded'])
    duplicate_groups = grouped.filter(lambda x: len(x) > 1)

    if len(duplicate_groups) == 0:
        print("\n✓ No parcels with duplicate centroids found")
        return parcels

    print(f"\n⚠ Found {len(duplicate_groups)} parcels sharing centroids:")
    print(f"  {len(grouped.filter(lambda x: len(x) > 1).groupby(['centroid_x_rounded', 'centroid_y_rounded']))} unique centroid locations have duplicates\n")

    # Track indices to remove
    indices_to_remove = set()

    # Print details for each group and identify parcels to remove
    for _, group in grouped:
        if len(group) > 1:
            # Filter out parcels with BLDSQFTTAXABLE > 0 from this group
            to_remove = group[group['BLDSQFTTAXABLE'] > 0]
            indices_to_remove.update(to_remove.index)

    # Remove the identified parcels from the original dataframe
    filtered_parcels = parcels.drop(index=indices_to_remove, errors='ignore')

    print(f"\n✓ Removed {len(indices_to_remove)} parcels with BLDSQFTTAXABLE > 0 that shared centroids")
    print(f"  Remaining parcels: {len(filtered_parcels)}")

    return filtered_parcels

def export_geojson(gdf, filename):
    """
    Export a GeoDataFrame to a GeoJSON file.

    Args:
        gdf: GeoDataFrame to export
        filename: Path to output file (str or Path)
    """
    if gdf is None or len(gdf) == 0:
        print(f"⚠ Skipping export of {filename} (no data)")
        return

    # Convert to Path and create output directory if it doesn't exist
    filepath = Path(filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Ensure CRS is set (GeoJSON standard is WGS84/EPSG:4326)
    gdf = ensure_crs(gdf)

    # Export to GeoJSON
    gdf.to_file(str(filepath), driver='GeoJSON')
    print(f"✓ Exported {len(gdf)} features to {filepath}")


def gather_city_data(config: CityConfig) -> CityData | None:
    """
    Load or fetch all raw data needed for SB-79 analysis.

    When USE_LOCAL_DATA is True, loads from the local GeoPackage.
    Otherwise fetches from remote APIs and saves locally.

    Args:
        config: CityConfig for the target city

    Returns:
        CityData on success, None if critical data is missing
    """
    city_name = config.name

    if USE_LOCAL_DATA:
        print("\n=== Loading data from local storage ===")
        city_boundary = load_layer(city_name, LAYER_CITY_BOUNDARY)
        transit_stops = load_layer(city_name, LAYER_TRANSIT_STOPS)
        zoning_districts = load_layer(city_name, LAYER_ZONING)
        parcels = load_layer(city_name, LAYER_PARCELS)

        missing = []
        if city_boundary is None:
            missing.append("city_boundary")
        if transit_stops is None:
            missing.append("transit_stops")
        if zoning_districts is None:
            missing.append("zoning_districts")
        if parcels is None:
            missing.append("parcels")

        if missing:
            print(f"\n✗ Missing local data: {', '.join(missing)}")
            print("  Set USE_LOCAL_DATA=False in config.py to fetch from API.")
            return None
    else:
        print("\n=== Fetching data from APIs ===")
        city_boundary = get_city_boundary(city_name)
        if city_boundary is None:
            return None
        save_layer(city_boundary, city_name, LAYER_CITY_BOUNDARY, CITY_BOUNDARIES_URL)

        # Get transit stops within 0.5mi of city boundary (to capture stops whose radius overlaps the city)
        city_buffered = get_city_boundary(city_name, buffer_miles=0.6)
        transit_stops = get_transit_stops(city_buffered, config.transit_stop_where)
        if transit_stops is None:
            return None
        save_layer(transit_stops, city_name, LAYER_TRANSIT_STOPS, HIGH_QUALITY_TRANSIT_STOPS_URL)

        print(f"\n✓ Found {len(transit_stops)} transit stops in {city_name}")

        # Get zoning districts
        zoning_districts = get_zoning_districts(city_boundary, config.zoning_api)
        if zoning_districts is not None:
            save_layer(zoning_districts, city_name, LAYER_ZONING, config.zoning_api)

        # Get parcels
        parcels = get_tier1_parcels(config.parcel_api, transit_stops, config.parcel_city_value, config.parcel_city_field)
        if parcels is not None:
            save_layer(parcels, city_name, LAYER_PARCELS, config.parcel_api)

    return CityData(
        city_boundary=city_boundary,
        transit_stops=transit_stops,
        zoning_districts=zoning_districts,
        parcels=parcels,
    )


def process_city_data(config: CityConfig, data: CityData, zoning_limits: dict) -> gpd.GeoDataFrame:
    """
    Transform raw city data into processed SB-79 parcels.

    Applies zoning join, overlays, zone prefix filter, capacity calculations,
    zoning/SB-79 limits, and filters.

    Args:
        config: CityConfig for the target city
        data: CityData containing raw GeoDataFrames
        zoning_limits: dict with 'height' and 'max_density' dicts mapping ZONECLASS to values

    Returns:
        Processed parcels GeoDataFrame
    """
    print(f"\n✓ Found {len(data.transit_stops)} transit stops in {config.name}")

    parcels = add_zoning_to_parcels(data.parcels, data.zoning_districts)

    # Apply overlays (e.g. Southside Plan reclassification)
    for overlay in config.overlays:
        parcels = overlay(parcels)

    # Filter for residential, commercial, and mixed use parcels
    parcels = parcels[(parcels["ZONECLASS"].str.startswith(config.zone_prefix_filter) & (parcels["ZONECLASS"].notna()))]

    parcels = add_potential_and_net_capacity(parcels)

    parcels = add_zoning_and_sb79_limits(parcels, zoning_limits)

    parcels = filter_zero_lotsize_parcels(parcels)

    parcels = filter_parcels_with_same_centroid(parcels)

    return parcels


def export_city_results(city_name: str, data: CityData, parcels: gpd.GeoDataFrame):
    """
    Print stats summary and export GeoJSON files and map metadata.

    Args:
        city_name: Name of the city
        data: CityData containing raw GeoDataFrames (for boundary/transit export)
        parcels: Processed parcels GeoDataFrame
    """
    two_hundred_ft_parcels = parcels[parcels['tier1_zone'] == TIER_200FT]
    quarter_mile_parcels = parcels[parcels['tier1_zone'] == TIER_QUARTER_MILE]
    half_mile_parcels = parcels[parcels['tier1_zone'] == TIER_HALF_MILE]

    # Print existing units and potential capacity summary by tier zone
    if 'Units' in parcels.columns:
        units_200ft = two_hundred_ft_parcels['Units'].fillna(0).sum()
        units_quarter = quarter_mile_parcels['Units'].fillna(0).sum()
        units_half = half_mile_parcels['Units'].fillna(0).sum()
        total_units = parcels['Units'].fillna(0).sum()

        net_increase_cap_200ft = two_hundred_ft_parcels['NetIncreaseCapacity'].sum()
        net_increase_cap_quarter = quarter_mile_parcels['NetIncreaseCapacity'].sum()
        net_increase_cap_half = half_mile_parcels['NetIncreaseCapacity'].sum()
        net_increase_total_capacity = parcels['NetIncreaseCapacity'].sum()

        print("\n✓ Capacity Summary by Tier Zone w/ net increase calculations:")
        print(f"  - 200ft zone: {int(units_200ft)} existing / {int(net_increase_cap_200ft)} potential ({len(two_hundred_ft_parcels)} parcels)")
        print(f"  - Quarter mile zone: {int(units_quarter)} existing / {int(net_increase_cap_quarter)} potential ({len(quarter_mile_parcels)} parcels)")
        print(f"  - Half mile zone: {int(units_half)} existing / {int(net_increase_cap_half)} potential ({len(half_mile_parcels)} parcels)")
        print(f"  - Total: {int(total_units)} existing / {int(net_increase_total_capacity)} potential units")
        print(f"  - Net new capacity: {int(net_increase_total_capacity)} units")

    # Export GeoJSON files for MapLibre
    print("\n=== Exporting GeoJSON files ===")

    # Get the directory where this script is located and construct path to public/data
    script_dir = Path(__file__).parent
    data_dir = script_dir / '..' / 'public' / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    export_geojson(data.city_boundary, data_dir / 'city_boundary.geojson')
    export_geojson(data.transit_stops, data_dir / 'transit_stops.geojson')
    # Export all parcels in a single file - they already have tier1_zone property for filtering
    export_geojson(parcels, data_dir / 'parcels.geojson')

    # Calculate map bounds for MapLibre
    bounds = data.city_boundary.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    # Create map metadata
    map_metadata = {
        'center': [center_lon, center_lat],
        'bounds': [[bounds[0], bounds[1]], [bounds[2], bounds[3]]],
        'city_name': city_name,
        'stats': {
            'transit_stops': len(data.transit_stops),
            'parcels_200ft': len(two_hundred_ft_parcels),
            'parcels_quarter_mile': len(quarter_mile_parcels),
            'parcels_half_mile': len(half_mile_parcels),
            'total_existing_units': int(total_units) if 'Units' in parcels.columns else 0,
            'net_increase_capacity': net_increase_total_capacity if 'NetIncreaseCapacity' in parcels.columns else 0,
            'existing_units_200ft': int(units_200ft) if 'Units' in parcels.columns else 0,
            'existing_units_quarter': int(units_quarter) if 'Units' in parcels.columns else 0,
            'existing_units_half': int(units_half) if 'Units' in parcels.columns else 0,
            'net_increase_capacity_200ft': net_increase_cap_200ft if 'NetIncreaseCapacity' in parcels.columns else 0,
            'net_increase_capacity_quarter': net_increase_cap_quarter if 'NetIncreaseCapacity' in parcels.columns else 0,
            'net_increase_capacity_half': net_increase_cap_half if 'NetIncreaseCapacity' in parcels.columns else 0
        }
    }

    metadata_path = data_dir / 'map_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(map_metadata, f, indent=2)

    print(f"✓ Exported map metadata to {metadata_path}")
    print("\n✓ All data exported to public/data/")
    print("✓ Run the map by opening public/index.html in your browser")
    print("✓ Or deploy the 'public' directory to Cloudflare Pages or any static host")
