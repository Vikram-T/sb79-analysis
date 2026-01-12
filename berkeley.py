import geopandas as gpd
import pandas as pd
import requests
import urllib
import folium
import json

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
            
            # determine next loop
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

def add_potential_capacity(parcels):
    """
    Calculate potential unit capacity for each parcel based on tier zone and lot size.

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

    # Print summary
    total_capacity = parcels['PotentialCapacity'].sum()
    print(f"\n✓ Calculated potential capacity for {len(parcels)} parcels")
    print(f"  Using densities: 200ft={DENSITY_200FT}, quarter_mile={DENSITY_QUARTER_MILE}, half_mile={DENSITY_HALF_MILE} units/acre")

    return parcels

def add_parcels(map_obj, parcels, color='orange', name='Parcels'):
    """
    Add parcel polygons to a folium map.

    Args:
        map_obj: Folium Map object to add the parcels to
        parcels: GeoDataFrame containing parcel data
        color: Color for the parcel borders (default: 'orange')
        name: Name for the layer (default: 'Parcels')
    """
    # Determine tooltip fields based on available columns
    tooltip_fields = []
    tooltip_aliases = []

    if 'APN' in parcels.columns:
        tooltip_fields.append('APN')
        tooltip_aliases.append('APN:')

    if 'SitusAddress' in parcels.columns:
        tooltip_fields.append('SitusAddress')
        tooltip_aliases.append('Address:')

    if 'SitusCity' in parcels.columns:
        tooltip_fields.append('SitusCity')
        tooltip_aliases.append('City:')

    if 'ZONECLASS' in parcels.columns:
        tooltip_fields.append('ZONECLASS')
        tooltip_aliases.append('Zone:')

    if 'ZONEDESC' in parcels.columns:
        tooltip_fields.append('ZONEDESC')
        tooltip_aliases.append('Zone Desc:')

    if 'Units' in parcels.columns:
        tooltip_fields.append('Units')
        tooltip_aliases.append('Existing Units:')

    if 'PotentialCapacity' in parcels.columns:
        tooltip_fields.append('PotentialCapacity')
        tooltip_aliases.append('Potential Capacity:')

    # Fallback to OBJECTID if no other fields available
    if not tooltip_fields:
        tooltip_fields = ['OBJECTID']
        tooltip_aliases = ['Parcel ID:']

    folium.GeoJson(
        parcels.to_json(),
        name=name,
        style_function=lambda x: {
            'fillColor': color,
            'color': color,
            'weight': 1,
            'fillOpacity': 0.2
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases,
            localize=True
        )
    ).add_to(map_obj)

def add_city_boundary(map_obj, city_geojson):
    """
    Add city boundary layer to a folium map.

    Args:
        map_obj: Folium Map object to add the boundary to
        city_geojson: GeoDataFrame containing the city boundary
    """
    city_name = city_geojson.iloc[0]['CDTFA_CITY']
    folium.GeoJson(
        city_geojson.to_json(),
        name=f'{city_name} Boundary',
        style_function=lambda x: {
            'fillColor': 'blue',
            'color': 'darkblue',
            'weight': 3,
            'fillOpacity': 0.1
        },
        popup=folium.Popup(f"{city_name} boundary", max_width=300)
    ).add_to(map_obj)

def add_transit_stops(map_obj, transit_stops):
    """
    Add transit stop markers to a folium map.

    Args:
        map_obj: Folium Map object to add the markers to
        transit_stops: GeoDataFrame containing transit stop data
    """
    for _, stop in transit_stops.iterrows():
        popup_html = f"""
        <b>Transit Stop Details</b><br>
        <b>OBJECTID:</b> {stop.get('OBJECTID', 'N/A')}<br>
        <b>Agency:</b> {stop.get('agency_primary', 'N/A')}<br>
        <b>HQTA Type:</b> {stop.get('hqta_type', 'N/A')}<br>
        <b>Stop ID:</b> {stop.get('stop_id', 'N/A')}<br>
        <b>Route ID:</b> {stop.get('route_id', 'N/A')}<br>
        <b>HQTA Details:</b> {stop.get('hqta_details', 'N/A')}
        """
        folium.CircleMarker(
            location=[stop.geometry.y, stop.geometry.x],
            radius=8,
            popup=folium.Popup(popup_html, max_width=300),
            color='red',
            fill=True,
            fillColor='red',
            fillOpacity=0.7
        ).add_to(map_obj)

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

        # Get parcels (will be saved after processing)
        tier1_parcels = get_tier1_parcels(BERKELEY_PARCEL_API, transit_stops, city_name)

    print(f"\n✓ Found {len(transit_stops)} transit stops in {city_name}")

    # Create folium map
    bounds = city_geojson.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="OpenStreetMap"
    )

    # Add map layers
    add_city_boundary(m, city_geojson)
    add_transit_stops(m, transit_stops)

    # Process parcels (add zoning and capacity) if not loading pre-processed data
    if not USE_LOCAL_DATA:
        # Add zoning info to parcels
        if tier1_parcels is not None and zoning_districts is not None:
            tier1_parcels = add_zoning_to_parcels(tier1_parcels, zoning_districts)

        # Add potential capacity to parcels
        if tier1_parcels is not None:
            tier1_parcels = add_potential_capacity(tier1_parcels)

        # Save processed parcels to local storage
        if tier1_parcels is not None:
            save_layer(tier1_parcels, city_name, LAYER_PARCELS, BERKELEY_PARCEL_API)

    if tier1_parcels is not None:
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

            print("\n✓ Capacity Summary by Tier Zone:")
            print(f"  - 200ft zone: {int(units_200ft)} existing / {int(cap_200ft)} potential ({len(two_hundred_ft_parcels)} parcels)")
            print(f"  - Quarter mile zone: {int(units_quarter)} existing / {int(cap_quarter)} potential ({len(quarter_mile_parcels)} parcels)")
            print(f"  - Half mile zone: {int(units_half)} existing / {int(cap_half)} potential ({len(half_mile_parcels)} parcels)")
            print(f"  - Total: {int(total_units)} existing / {int(total_capacity)} potential units")
            print(f"  - Net new capacity: {int(total_capacity - total_units)} units")

        add_parcels(m, two_hundred_ft_parcels, color="red", name="200ft Parcels (0-200ft)")
        add_parcels(m, quarter_mile_parcels, color="green", name="Quarter Mile Parcels (200ft-0.25mi)")
        add_parcels(m, half_mile_parcels, color="blue", name="Half Mile Parcels (0.25-0.5mi)")


    m.save('city_boundary.html')
    print("\n✓ Map saved to city_boundary.html")
    
if __name__ == "__main__":
    main()