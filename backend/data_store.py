# data_store.py
# Local data storage for SB-79 analysis - saves/loads GeoDataFrames to GeoPackage format

import json
from datetime import datetime
from pathlib import Path
import geopandas as gpd

from config import DATA_DIR
from geo_utils import ensure_crs

# Layer names in the GeoPackage
LAYER_CITY_BOUNDARY = "city_boundary"
LAYER_TRANSIT_STOPS = "transit_stops"
LAYER_ZONING = "zoning_districts"
LAYER_PARCELS = "parcels"


def _get_gpkg_path(city_name):
    """Get the GeoPackage file path for a city."""
    return Path(DATA_DIR) / f"{city_name.lower()}_data.gpkg"


def _ensure_data_dir():
    """Create data directory if it doesn't exist."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def _save_metadata(gpkg_path, layer_name, record_count, source_api=None):
    """Save metadata for a layer to a JSON sidecar file."""
    metadata_path = gpkg_path.with_suffix('.metadata.json')

    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {"layers": {}}

    metadata["layers"][layer_name] = {
        "timestamp": datetime.now().isoformat(),
        "record_count": record_count,
        "source_api": source_api
    }
    metadata["last_updated"] = datetime.now().isoformat()

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)


def _load_metadata(gpkg_path):
    """Load metadata for a GeoPackage."""
    metadata_path = gpkg_path.with_suffix('.metadata.json')
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            return json.load(f)
    return None


def save_layer(gdf, city_name, layer_name, source_api=None):
    """
    Save a GeoDataFrame to local storage.

    Args:
        gdf: GeoDataFrame to save
        city_name: Name of the city
        layer_name: Layer name (use LAYER_* constants)
        source_api: Optional API URL for audit trail
    """
    _ensure_data_dir()
    gpkg_path = _get_gpkg_path(city_name)

    gdf = ensure_crs(gdf)
    gdf.to_file(gpkg_path, layer=layer_name, driver="GPKG")
    _save_metadata(gpkg_path, layer_name, len(gdf), source_api)
    print(f"  [data_store] Saved {len(gdf)} {layer_name} to {gpkg_path}")


def load_layer(city_name, layer_name):
    """
    Load a GeoDataFrame from local storage.

    Args:
        city_name: Name of the city
        layer_name: Layer name (use LAYER_* constants)

    Returns:
        GeoDataFrame or None if not found
    """
    gpkg_path = _get_gpkg_path(city_name)

    if not gpkg_path.exists():
        print(f"  [data_store] No local data found at {gpkg_path}")
        return None

    try:
        gdf = gpd.read_file(gpkg_path, layer=layer_name)
        print(f"  [data_store] Loaded {len(gdf)} {layer_name} from {gpkg_path}")
        return gdf
    except Exception as e:
        print(f"  [data_store] Error loading {layer_name}: {e}")
        return None


def list_snapshots():
    """
    List all available data snapshots with their metadata.

    Returns:
        dict: Dictionary of city names to their metadata
    """
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        print("No data directory found")
        return {}

    snapshots = {}
    for gpkg_file in data_path.glob("*_data.gpkg"):
        city_name = gpkg_file.stem.replace("_data", "").title()
        metadata = _load_metadata(gpkg_file)
        snapshots[city_name] = {
            "file": str(gpkg_file),
            "metadata": metadata
        }

    return snapshots


def print_snapshot_info():
    """Print formatted information about available snapshots."""
    snapshots = list_snapshots()

    if not snapshots:
        print("No local data snapshots found.")
        return

    print("\n=== Local Data Snapshots ===")
    for city, info in snapshots.items():
        print(f"\n{city}:")
        print(f"  File: {info['file']}")
        if info['metadata']:
            print(f"  Last updated: {info['metadata'].get('last_updated', 'Unknown')}")
            for layer, layer_info in info['metadata'].get('layers', {}).items():
                print(f"  - {layer}: {layer_info['record_count']} records ({layer_info['timestamp']})")


def data_exists(city_name):
    """Check if local data exists for a city."""
    return _get_gpkg_path(city_name).exists()
