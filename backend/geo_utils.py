# geo_utils.py
# Utility functions for geospatial operations and API interactions

import json
from pathlib import Path

import geopandas as gpd
import requests

# CRS constants
CRS_WGS84 = "EPSG:4326"
CRS_UTM_10N = "EPSG:32610"  # UTM Zone 10N - appropriate for SF Bay Area

# Tier zone constants
TIER_200FT = "200ft"
TIER_QUARTER_MILE = "quarter_mile"
TIER_HALF_MILE = "half_mile"

TIER_ZONES = [TIER_200FT, TIER_QUARTER_MILE, TIER_HALF_MILE]


# =============================================================================
# CRS Helpers
# =============================================================================

def ensure_crs(gdf, crs=CRS_WGS84):
    """
    Ensure GeoDataFrame has CRS set, defaulting to WGS84.

    Args:
        gdf: GeoDataFrame to check
        crs: CRS to set if none exists (default: EPSG:4326)

    Returns:
        GeoDataFrame with CRS set
    """
    if gdf is None:
        return None
    if gdf.crs is None:
        return gdf.set_crs(crs)
    return gdf


def project_to_utm(gdf):
    """
    Project GeoDataFrame to UTM Zone 10N for accurate distance calculations.

    Args:
        gdf: GeoDataFrame in any CRS

    Returns:
        GeoDataFrame projected to EPSG:32610 (UTM Zone 10N)
    """
    gdf = ensure_crs(gdf)
    return gdf.to_crs(CRS_UTM_10N)


def project_to_wgs84(gdf):
    """
    Project GeoDataFrame to WGS84 (standard lat/lon).

    Args:
        gdf: GeoDataFrame in any CRS

    Returns:
        GeoDataFrame projected to EPSG:4326 (WGS84)
    """
    return gdf.to_crs(CRS_WGS84)


# =============================================================================
# ESRI Geometry Conversion
# =============================================================================

def polygon_to_esri_geometry(gdf):
    """
    Convert a GeoDataFrame polygon to ESRI geometry format for API queries.

    Args:
        gdf: GeoDataFrame containing a polygon geometry

    Returns:
        dict: ESRI geometry object with rings and spatial reference
    """
    coords = list(gdf.geometry.iloc[0].exterior.coords)
    return {
        "rings": [coords],
        "spatialReference": {"wkid": 4326}
    }


def point_to_esri_geometry(point):
    """
    Convert a Shapely Point to ESRI geometry format for API queries.

    Args:
        point: Shapely Point geometry

    Returns:
        dict: ESRI geometry object with x, y and spatial reference
    """
    return {
        "x": point.x,
        "y": point.y,
        "spatialReference": {"wkid": 4326}
    }


# =============================================================================
# API Helpers
# =============================================================================

def validate_api_response(response, context="API"):
    """
    Validate an API response for common error conditions.

    Args:
        response: requests.Response object
        context: Description of the API call for error messages

    Returns:
        tuple: (is_valid, response_json or None, error_message or None)
    """
    if response.status_code != 200:
        return False, None, f"HTTP {response.status_code}"

    try:
        response_json = response.json()
    except json.JSONDecodeError:
        return False, None, "Invalid JSON response"

    if 'error' in response_json:
        error_msg = response_json.get('error', {})
        if isinstance(error_msg, dict):
            error_msg = error_msg.get('message', str(error_msg))
        return False, response_json, str(error_msg)

    return True, response_json, None


def fetch_all_paginated(api_url, params, batch_size=2000, verbose=True):
    """
    Fetch all features from a paginated ArcGIS REST API.

    Handles pagination automatically by checking exceededTransferLimit
    and incrementing resultOffset.

    Args:
        api_url: URL of the ArcGIS REST API endpoint
        params: dict of query parameters (will be modified with pagination params)
        batch_size: Number of records per request (default: 2000)
        verbose: Whether to print progress messages (default: True)

    Returns:
        list: All features from the API, or empty list if error
    """
    all_features = []
    offset = 0
    params = params.copy()  # Don't modify the original

    while True:
        params["resultOffset"] = offset
        params["resultRecordCount"] = batch_size

        try:
            response = requests.post(api_url, data=params)
            is_valid, response_json, error_msg = validate_api_response(response)

            if not is_valid:
                if verbose:
                    print(f"Error fetching data: {error_msg}")
                return all_features if all_features else []

            features = response_json.get('features', [])
            if not features:
                break

            all_features.extend(features)

            if verbose:
                print(f"   Fetched batch at offset {offset}: {len(features)} features (total: {len(all_features)})")

            # Check if there are more records
            exceeded_limit = response_json.get("properties", {}).get("exceededTransferLimit", False)
            if not exceeded_limit:
                break

            offset += batch_size

        except requests.RequestException as e:
            if verbose:
                print(f"Request error: {e}")
            return all_features if all_features else []

    return all_features


