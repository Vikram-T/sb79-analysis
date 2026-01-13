import geopandas as gpd
import pandas as pd
import requests
import urllib
import json
import os
from pathlib import Path

# California State Geoportal - City Boundaries
from config import (
    BERKELEY_PARCEL_API, CITY_BOUNDARIES_URL, HIGH_QUALITY_TRANSIT_STOPS_URL, BERKELEY_ZONING_API,
    DENSITY_200FT, DENSITY_QUARTER_MILE, DENSITY_HALF_MILE, USE_LOCAL_DATA
)
from data_store import (
    save_layer, load_layer,
    LAYER_CITY_BOUNDARY, LAYER_TRANSIT_STOPS, LAYER_ZONING, LAYER_PARCELS
)

def get_city_boundary(city_name):
    """
    Fetch city boundary from California State Geoportal.

    Args:
        city_name: Name of the city to fetch boundary for

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

        return city_geojson
    except Exception as e:
        print(f"Error fetching city boundary: {e}")
        return None

def get_transit_stops(city_boundary):
    """
    Fetch high quality transit stops within a city boundary from California State Geoportal.

    Args:
        city_boundary: GeoDataFrame containing the city boundary

    Returns:
        GeoDataFrame containing transit stops, or None if error
    """
    coords = list(city_boundary.geometry.iloc[0].exterior.coords)
    esri_geometry = {
        "rings": [coords],
        "spatialReference": {"wkid": 4326}
    }

    transit_params = {
        'where': "hqta_type='major_stop_rail' AND agency_primary!='Capitol Corridor Joint Powers Authority' AND agency_primary!='Amtrak'",
        'outFields': 'OBJECTID,agency_primary,hqta_type,stop_id,route_id,hqta_details',
        'geometry': json.dumps(esri_geometry),
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
        return transit_stops
    except Exception as e:
        print(f"Error fetching transit stops: {e}")
        return None

def get_parcels_near_transit_stops(parcel_api, transit_stops, distance_miles, city_name, zone_tag=None):
    """
    Fetch all parcels within a specified distance from transit stops using multipoint geometry.

    Args:
        parcel_api: URL of the parcel API endpoint
        transit_stops: GeoDataFrame containing transit stop data
        distance_miles: Distance in miles to search around transit stops
        city_name: Name of the city to filter parcels by (e.g., 'Berkeley')
        zone_tag: Optional string to tag parcels with (e.g., 'quarter_mile', 'half_mile')

    Returns:
        GeoDataFrame containing unique parcels within distance of any transit stop, or None if error
    """
    # Create multipoint geometry from all transit stops
    points = [[stop.geometry.x, stop.geometry.y] for _, stop in transit_stops.iterrows()]

    esri_geometry = {
        "points": points,
        "spatialReference": {"wkid": 4326}
    }

    parcel_params = {
        'where': f"SitusCity='{city_name}'",
        'geometry': json.dumps(esri_geometry),
        'geometryType': 'esriGeometryMultipoint',
        'distance': distance_miles,
        'units': 'esriSRUnit_StatuteMile',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'outFields': '*',
        'outSR': '4326',
        'f': 'geojson'
    }
    parcels_list = []
    offset = 0
    batch_size = 2000
    remaining_records = True

    try:
        # API Only returns results in batches so we need to loop until we get all items
        while remaining_records:
            parcel_params["resultOffset"] = offset
            parcel_params["resultRecordCount"] = batch_size

            response = requests.post(parcel_api, data=parcel_params)

            if response.status_code != 200:
                print(f"Error fetching parcels: HTTP {response.status_code}")
                return None

            response_json = response.json()

            if 'error' in response_json:
                print(f"Error fetching parcels: {response_json['error']}")
                return None

            if 'features' not in response_json or len(response_json['features']) == 0:
                print(f"No parcels found within {distance_miles} miles of any transit stop")
                return None

            parcel_json = response_json['features']
            parcels_list.extend(parcel_json)
            
            # determine next batch
            remaining_records = response_json.get("properties", {}).get("exceededTransferLimit", False)
            print(f"   Fetched batch at offset {offset}: {len(parcel_json)} parcels (total: {len(parcels_list)})")
            offset += batch_size
        
        parcels = gpd.GeoDataFrame.from_features(parcels_list)
        # Remove duplicates based on APN (Assessor's Parcel Number)
        # Keep first occurrence to ensure we have one record per physical parcel
        parcels = parcels.drop_duplicates(subset=['APN'], keep='first')

        # Add zone tag if provided
        if zone_tag:
            parcels['tier1_zone'] = zone_tag

        print(f"✓ Found {len(parcels)} unique parcels within {distance_miles} miles of transit stops")
        return parcels

    except Exception as e:
        print(f"Error fetching parcels: {e}")
        return None

def get_tier1_parcels(parcel_api, transit_stops, city_name):
    """
    Get all Tier 1 SB-79 parcels with zone tagging (quarter_mile or half_mile).

    Args:
        parcel_api: URL of the parcel API endpoint
        transit_stops: GeoDataFrame containing transit stop data
        city_name: Name of the city to filter parcels by (e.g., 'Berkeley')

    Returns:
        GeoDataFrame with all parcels tagged with their tier1_zone, or None if error
    """
    # Convert 200ft to miles: 200 / 5280 ≈ 0.0379
    two_hundred_ft_miles = 200 / 5280

    # Get parcels within 0.5 miles (outer zone)
    half_mile_parcels = get_parcels_near_transit_stops(
        parcel_api, transit_stops, 0.5, city_name, zone_tag='half_mile'
    )
    if half_mile_parcels is None:
        return None

    # Get parcels within 0.25 miles (middle zone)
    quarter_mile_parcels = get_parcels_near_transit_stops(
        parcel_api, transit_stops, 0.25, city_name, zone_tag='quarter_mile'
    )

    if quarter_mile_parcels is None:
        return half_mile_parcels

    # Get parcels within 200ft (inner zone)
    two_hundred_ft_parcels = get_parcels_near_transit_stops(
        parcel_api, transit_stops, two_hundred_ft_miles, city_name, zone_tag='200ft'
    )

    if two_hundred_ft_parcels is None:
        return quarter_mile_parcels

    # Get OBJECTIDs for each zone
    two_hundred_ft_objectids = set(two_hundred_ft_parcels['OBJECTID'])
    quarter_mile_objectids = set(quarter_mile_parcels['OBJECTID'])

    # Filter quarter_mile to exclude 200ft parcels
    quarter_mile_only = quarter_mile_parcels[~quarter_mile_parcels['OBJECTID'].isin(two_hundred_ft_objectids)]

    # Filter half_mile to exclude quarter_mile parcels (quarter_mile includes 200ft, so both are excluded)
    half_mile_only = half_mile_parcels[~half_mile_parcels['OBJECTID'].isin(quarter_mile_objectids)]

    # Combine all zones
    all_parcels = gpd.GeoDataFrame(pd.concat([two_hundred_ft_parcels, quarter_mile_only, half_mile_only], ignore_index=True))

    # Print Results
    two_hundred_ft_count = len(all_parcels[all_parcels['tier1_zone'] == '200ft'])
    quarter_count = len(all_parcels[all_parcels['tier1_zone'] == 'quarter_mile'])
    half_count = len(all_parcels[all_parcels['tier1_zone'] == 'half_mile'])

    print("\n✓ Tier 1 Parcel Summary:")
    print(f"  - 200ft zone (0-200ft): {two_hundred_ft_count} parcels")
    print(f"  - Quarter mile zone (200ft-0.25mi): {quarter_count} parcels")
    print(f"  - Half mile zone (0.25-0.5mi): {half_count} parcels")
    print(f"  - Total: {len(all_parcels)} parcels")

    return all_parcels

def get_zoning_districts(city_boundary):
    """
    Fetch all zoning districts within a city boundary from Berkeley's GIS.

    Args:
        city_boundary: GeoDataFrame containing the city boundary

    Returns:
        GeoDataFrame containing zoning districts, or None if error
    """
    coords = list(city_boundary.geometry.iloc[0].exterior.coords)
    esri_geometry = {
        "rings": [coords],
        "spatialReference": {"wkid": 4326}
    }

    zoning_params = {
        'where': '1=1',
        'geometry': json.dumps(esri_geometry),
        'geometryType': 'esriGeometryPolygon',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'outFields': 'OBJECTID,ZONECLASS,ZONEDESC',
        'outSR': '4326',
        'f': 'geojson'
    }

    zones_list = []
    offset = 0
    batch_size = 2000
    remaining_records = True

    try:
        while remaining_records:
            zoning_params["resultOffset"] = offset
            zoning_params["resultRecordCount"] = batch_size

            response = requests.post(BERKELEY_ZONING_API, data=zoning_params)

            if response.status_code != 200:
                print(f"Error fetching zoning districts: HTTP {response.status_code}")
                return None

            response_json = response.json()

            if 'error' in response_json:
                print(f"Error fetching zoning districts: {response_json['error']}")
                return None

            if 'features' not in response_json or len(response_json['features']) == 0:
                if len(zones_list) == 0:
                    print("No zoning districts found")
                    return None
                break

            zone_json = response_json['features']
            zones_list.extend(zone_json)

            remaining_records = response_json.get("properties", {}).get("exceededTransferLimit", False)
            print(f"   Fetched zoning batch at offset {offset}: {len(zone_json)} zones (total: {len(zones_list)})")
            offset += batch_size

        zones = gpd.GeoDataFrame.from_features(zones_list)
        zones = zones.set_crs(epsg=4326)
        print(f"✓ Found {len(zones)} zoning districts")
        return zones

    except Exception as e:
        print(f"Error fetching zoning districts: {e}")
        return None

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

    # Ensure both have CRS set
    if parcels.crs is None:
        parcels = parcels.set_crs(epsg=4326)
    if zoning_districts.crs is None:
        zoning_districts = zoning_districts.set_crs(epsg=4326)

    # Project to UTM Zone 10N (EPSG:32610) for accurate centroid calculation
    parcels_projected = parcels.to_crs(epsg=32610)
    zoning_projected = zoning_districts.to_crs(epsg=32610)

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
    joined = joined.set_crs(epsg=4326)

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
    This number cannot be negative though and will rather be 0

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
        '200ft': DENSITY_200FT,
        'quarter_mile': DENSITY_QUARTER_MILE,
        'half_mile': DENSITY_HALF_MILE
    }

    def calc_capacity(row):
        lot_size = row.get('LotSize', 0) or 0
        tier_zone = row.get('tier1_zone', '')
        density = density_map.get(tier_zone, 0)

        # Convert lot size from sq ft to acres and multiply by density
        acres = lot_size / SQFT_PER_ACRE
        return acres * density

    parcels['PotentialCapacity'] = parcels.apply(calc_capacity, axis=1)

    # Calculating net capacity based on SB-79 65912.161. (a) (1)
    # Essentially we take (potential capacity based on distance from transit) - (existing capacity) = net_capacity
    # This incentivizes development on parking lots over places that already have housing
    def net_capacity(row):
        potential = row.get('PotentialCapacity', 0)
        existing = row.get('Units', 0)

        return max(potential - existing, 0)

    parcels["NetIncreaseCapacity"] = parcels.apply(net_capacity,axis=1)

    # Print summary
    print(f"\n✓ Calculated potential capacity for {len(parcels)} parcels")
    print(f"  Using densities: 200ft={DENSITY_200FT}, quarter_mile={DENSITY_QUARTER_MILE}, half_mile={DENSITY_HALF_MILE} units/acre")

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

    # Ensure CRS is set
    parcels_copy = parcels.copy()
    if parcels_copy.crs is None:
        parcels_copy = parcels_copy.set_crs(epsg=4326)

    # Project to UTM Zone 10N (EPSG:32610) for accurate centroid calculation
    parcels_projected = parcels_copy.to_crs(epsg=32610)

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
    for (x, y), group in grouped:
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

    # Export to GeoJSON
    gdf.to_file(str(filepath), driver='GeoJSON')
    print(f"✓ Exported {len(gdf)} features to {filepath}")

def main():
    city_name = "Berkeley"

    if USE_LOCAL_DATA:
        print("\n=== Loading data from local storage ===")
        # Load from local GeoPackage
        city_geojson = load_layer(city_name, LAYER_CITY_BOUNDARY)
        transit_stops = load_layer(city_name, LAYER_TRANSIT_STOPS)
        zoning_districts = load_layer(city_name, LAYER_ZONING)
        tier1_parcels = load_layer(city_name, LAYER_PARCELS)

        missing = []
        if city_geojson is None:
            missing.append("city_boundary")
        if transit_stops is None:
            missing.append("transit_stops")
        if zoning_districts is None:
            missing.append("zoning_districts")
        if tier1_parcels is None:
            missing.append("parcels")

        if missing:
            print(f"\n✗ Missing local data: {', '.join(missing)}")
            print("  Set USE_LOCAL_DATA=False in config.py to fetch from API.")
            return
    else:
        print("\n=== Fetching data from APIs ===")
        # Get city boundary
        city_geojson = get_city_boundary(city_name)
        if city_geojson is None:
            return
        save_layer(city_geojson, city_name, LAYER_CITY_BOUNDARY, CITY_BOUNDARIES_URL)

        # Get transit stops within boundary
        transit_stops = get_transit_stops(city_geojson)
        if transit_stops is None:
            return
        save_layer(transit_stops, city_name, LAYER_TRANSIT_STOPS, HIGH_QUALITY_TRANSIT_STOPS_URL)

        print(f"\n✓ Found {len(transit_stops)} transit stops in {city_name}")

        # Get zoning districts
        zoning_districts = get_zoning_districts(city_geojson)
        if zoning_districts is not None:
            save_layer(zoning_districts, city_name, LAYER_ZONING, BERKELEY_ZONING_API)

        # Get parcels 
        tier1_parcels = get_tier1_parcels(BERKELEY_PARCEL_API, transit_stops, city_name)
        if tier1_parcels is not None:
            save_layer(tier1_parcels, city_name, LAYER_PARCELS, BERKELEY_PARCEL_API)

    print(f"\n✓ Found {len(transit_stops)} transit stops in {city_name}")

    tier1_parcels = add_zoning_to_parcels(tier1_parcels, zoning_districts)

    # Filter for residential, commercial, and mixed use parcels
    tier1_parcels = tier1_parcels[(tier1_parcels["ZONECLASS"].str.startswith(("C-", "R-")) | (tier1_parcels["ZONECLASS"] == "ES-R") | (tier1_parcels["ZONECLASS"].isna()))]

    tier1_parcels = add_potential_and_net_capacity(tier1_parcels)

    tier1_parcels = filter_zero_lotsize_parcels(tier1_parcels)

    tier1_parcels = filter_parcels_with_same_centroid(tier1_parcels)


    two_hundred_ft_parcels = tier1_parcels[tier1_parcels['tier1_zone'] == "200ft"]
    quarter_mile_parcels = tier1_parcels[tier1_parcels['tier1_zone'] == "quarter_mile"]
    half_mile_parcels = tier1_parcels[tier1_parcels['tier1_zone'] == "half_mile"]

    # Print existing units and potential capacity summary by tier zone
    if 'Units' in tier1_parcels.columns:
        units_200ft = two_hundred_ft_parcels['Units'].fillna(0).sum()
        units_quarter = quarter_mile_parcels['Units'].fillna(0).sum()
        units_half = half_mile_parcels['Units'].fillna(0).sum()
        total_units = tier1_parcels['Units'].fillna(0).sum()

        cap_200ft = two_hundred_ft_parcels['PotentialCapacity'].sum()
        cap_quarter = quarter_mile_parcels['PotentialCapacity'].sum()
        cap_half = half_mile_parcels['PotentialCapacity'].sum()
        total_capacity = tier1_parcels['PotentialCapacity'].sum()


        print("\n✓ Capacity Summary by Tier Zone simple:")
        print(f"  - 200ft zone: {int(units_200ft)} existing / {int(cap_200ft)} potential ({len(two_hundred_ft_parcels)} parcels)")
        print(f"  - Quarter mile zone: {int(units_quarter)} existing / {int(cap_quarter)} potential ({len(quarter_mile_parcels)} parcels)")
        print(f"  - Half mile zone: {int(units_half)} existing / {int(cap_half)} potential ({len(half_mile_parcels)} parcels)")
        print(f"  - Total: {int(total_units)} existing / {int(total_capacity)} potential units")
        print(f"  - Net new capacity: {int(total_capacity - total_units)} units")

        net_increase_cap_200ft = two_hundred_ft_parcels['NetIncreaseCapacity'].sum()
        net_increase_cap_quarter = quarter_mile_parcels['NetIncreaseCapacity'].sum()
        net_increase_cap_half = half_mile_parcels['NetIncreaseCapacity'].sum()
        net_increase_total_capacity = tier1_parcels['NetIncreaseCapacity'].sum()

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

    export_geojson(city_geojson, data_dir / 'city_boundary.geojson')
    export_geojson(transit_stops, data_dir / 'transit_stops.geojson')
    export_geojson(two_hundred_ft_parcels, data_dir / 'parcels_200ft.geojson')
    export_geojson(quarter_mile_parcels, data_dir / 'parcels_quarter_mile.geojson')
    export_geojson(half_mile_parcels, data_dir / 'parcels_half_mile.geojson')

    # Calculate map bounds for MapLibre
    bounds = city_geojson.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    # Create map metadata
    map_metadata = {
        'center': [center_lon, center_lat],
        'bounds': [[bounds[0], bounds[1]], [bounds[2], bounds[3]]],
        'city_name': city_name,
        'stats': {
            'transit_stops': len(transit_stops),
            'parcels_200ft': len(two_hundred_ft_parcels),
            'parcels_quarter_mile': len(quarter_mile_parcels),
            'parcels_half_mile': len(half_mile_parcels),
            'total_existing_units': int(total_units) if 'Units' in tier1_parcels.columns else 0,
            'total_potential_capacity': int(total_capacity) if 'PotentialCapacity' in tier1_parcels.columns else 0,
            'net_increase_capacity': int(net_increase_total_capacity) if 'NetIncreaseCapacity' in tier1_parcels.columns else 0
        }
    }

    metadata_path = data_dir / 'map_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(map_metadata, f, indent=2)

    print(f"✓ Exported map metadata to {metadata_path}")
    print("\n✓ All data exported to public/data/")
    print("✓ Run the map by opening public/index.html in your browser")
    print("✓ Or deploy the 'public' directory to Cloudflare Pages or any static host")
    
if __name__ == "__main__":
    main()