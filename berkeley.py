import geopandas as gpd
import pandas as pd
import requests
import urllib
import folium
import json

# California State Geoportal - City Boundaries
from config import CITY_BOUNDARIES_URL, HIGH_QUALITY_TRANSIT_STOPS_URL, ALAMEDA_PARCEL_API

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
        # Remove duplicates based on OBJECTID
        parcels = parcels.drop_duplicates(subset=['OBJECTID'])

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
    # Get parcels within 0.5 miles (outer zone)
    half_mile_parcels = get_parcels_near_transit_stops(
        parcel_api, transit_stops, 0.5, city_name, zone_tag='half_mile'
    )

    if half_mile_parcels is None:
        return None

    # Get parcels within 0.25 miles (inner zone)
    quarter_mile_parcels = get_parcels_near_transit_stops(
        parcel_api, transit_stops, 0.25, city_name, zone_tag='quarter_mile'
    )

    if quarter_mile_parcels is None:
        return half_mile_parcels

    # Get OBJECTIDs that are in the quarter mile zone
    quarter_mile_objectids = set(quarter_mile_parcels['OBJECTID'])

    # Update half_mile_parcels: remove any that are in quarter_mile zone
    half_mile_only = half_mile_parcels[~half_mile_parcels['OBJECTID'].isin(quarter_mile_objectids)]

    # Combine quarter_mile parcels with the remaining half_mile parcels
    all_parcels = gpd.GeoDataFrame(pd.concat([quarter_mile_parcels, half_mile_only], ignore_index=True))

    quarter_count = len(all_parcels[all_parcels['tier1_zone'] == 'quarter_mile'])
    half_count = len(all_parcels[all_parcels['tier1_zone'] == 'half_mile'])

    print(f"\n✓ Tier 1 Parcel Summary:")
    print(f"  - Quarter mile zone (0-0.25mi): {quarter_count} parcels")
    print(f"  - Half mile zone (0.25-0.5mi): {half_count} parcels")
    print(f"  - Total: {len(all_parcels)} parcels")

    return all_parcels

def add_parcels(map_obj, parcels, color='orange', name='Parcels'):
    """
    Add parcel polygons to a folium map.

    Args:
        map_obj: Folium Map object to add the parcels to
        parcels: GeoDataFrame containing parcel data
        color: Color for the parcel borders (default: 'orange')
        name: Name for the layer (default: 'Parcels')
    """
    folium.GeoJson(
        parcels.to_json(),
        name=name,
        style_function=lambda x: {
            'fillColor': color,
            'color': color,
            'weight': 1,
            'fillOpacity': 0.3
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['OBJECTID', 'SitusCity', 'SitusAddress'] if 'SitusAddress' in parcels.columns else ['OBJECTID', 'SitusCity'],
            aliases=['Parcel ID:', 'City:', 'Address:'] if 'SitusAddress' in parcels.columns else ['Parcel ID:', 'City:'],
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
    for idx, stop in transit_stops.iterrows():
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

def add_tier1_quarter_mile_zones(map_obj, transit_stops):
    """
    Add 1/4 mile radius circles around transit stops showing SB-79 Tier 1 zones.

    Args:
        map_obj: Folium Map object to add the circles to
        transit_stops: GeoDataFrame containing transit stop data
    """
    sb79_popup_html = """
    <div style="font-family: Arial, sans-serif;">
        <h2>Tier 1 Quarter Mile</h2>
        <p><b>(3)</b> For a transit-oriented housing development project within one-quarter mile of a Tier 1 transit-oriented development stop, all of the following apply:</p>
        <p style="margin-left: 20px;"><b>(A)</b> A local government shall not impose any height limit less than 75 feet.</p>
        <p style="margin-left: 20px;"><b>(B)</b> A local government shall not impose any maximum density of less than 120 dwelling units per acre.</p>
        <p style="margin-left: 20px;"><b>(C)</b> A local government shall not enforce any other local development standard or combination of standards that would physically preclude achieving a residential floor area ratio of up to 3.5.</p>
        <p style="margin-left: 20px;"><b>(D)</b> A development that achieves a minimum density of 90 dwelling units per acre and that otherwise meets the eligibility requirements of Section 65915, including, but not limited to, affordability requirements, shall be eligible for additional concessions pursuant to Section 65915, as specified in subdivision (d).</p>
    </div>
    """

    # 0.25 miles in meters (folium.Circle requires radius in meters)
    quarter_mile_meters = 0.25 * 1609.34

    for idx, stop in transit_stops.iterrows():
        folium.Circle(
            location=[stop.geometry.y, stop.geometry.x],
            radius=quarter_mile_meters,
            popup=folium.Popup(sb79_popup_html, max_width=400),
            color='green',
            fill=True,
            fillColor='green',
            fillOpacity=0.2
        ).add_to(map_obj)

def add_tier1_half_mile_zones(map_obj, transit_stops):
    """
    Add 1/2 mile radius circles around transit stops showing SB-79 Tier 1 half-mile zones.

    Args:
        map_obj: Folium Map object to add the circles to
        transit_stops: GeoDataFrame containing transit stop data
    """
    sb79_popup_html = """
    <div style="font-family: Arial, sans-serif;">
        <h2>Tier 1 Quarter to Half Mile</h2>
        <p><b>(4)</b> For a transit-oriented housing development project further than one-quarter mile but within one-half mile of a Tier 1 transit-oriented development stop, and within a city with a population of at least 35,000, all of the following apply:</p>
        <p style="margin-left: 20px;"><b>(A)</b> A local government shall not impose any height limit less than 65 feet.</p>
        <p style="margin-left: 20px;"><b>(B)</b> A local government shall not impose any maximum density standard of less than 100 dwelling units per acre.</p>
        <p style="margin-left: 20px;"><b>(C)</b> A local government shall not enforce any other local development standard or combination of standards that would physically preclude achieving a residential floor area ratio of up to 3.</p>
        <p style="margin-left: 20px;"><b>(D)</b> A development that achieves a minimum density of 75 dwelling units per acre and that otherwise meets the eligibility requirements of Section 65915, including, but not limited to, affordability requirements, shall be eligible for additional concessions pursuant to Section 65915, as specified in subdivision (d).</p>
    </div>
    """

    # 0.5 miles in meters (folium.Circle requires radius in meters)
    half_mile_meters = 0.5 * 1609.34

    for idx, stop in transit_stops.iterrows():
        folium.Circle(
            location=[stop.geometry.y, stop.geometry.x],
            radius=half_mile_meters,
            popup=folium.Popup(sb79_popup_html, max_width=400),
            color='blue',
            fill=True,
            fillColor='blue',
            fillOpacity=0.15
        ).add_to(map_obj)

def main():
    city_name = "Berkeley"

    # Get city boundary
    city_geojson = get_city_boundary(city_name)
    if city_geojson is None:
        return

    # Get transit stops within boundary
    transit_stops = get_transit_stops(city_geojson)
    if transit_stops is None:
        return

    print(f"\n✓ Found {len(transit_stops)} transit stops in {city_name}")
    if len(transit_stops) > 0:
        print(transit_stops)

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
    # add_tier1_half_mile_zones(m, transit_stops)
    # add_tier1_quarter_mile_zones(m, transit_stops)
    add_transit_stops(m, transit_stops)
    tier1_parcels = get_tier1_parcels(ALAMEDA_PARCEL_API, transit_stops, "Berkeley")

    if tier1_parcels is not None:
        quarter_mile_parcels = tier1_parcels[tier1_parcels['tier1_zone'] == "quarter_mile"]
        half_mile_parcels = tier1_parcels[tier1_parcels['tier1_zone'] == "half_mile"]
    
    add_parcels(m, quarter_mile_parcels, color="green", name="Quarter Mile Parcels (0-0.25mi)")
    add_parcels(m, half_mile_parcels, color="blue", name="Half Mile Parcels (0.25-0.5mi)")


    m.save('city_boundary.html')
    print("\n✓ Map saved to city_boundary.html")
    
if __name__ == "__main__":
    main()