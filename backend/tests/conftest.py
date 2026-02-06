import pytest
import geopandas as gpd
from shapely.geometry import Point, MultiPolygon, box


def make_parcel(apn, lot_size, units, tier1_zone, lon=-122.27, lat=37.87):
    """Create a single parcel as a small square polygon near Berkeley."""
    d = 0.0005  # ~55 meters
    return {
        "APN": apn,
        "OBJECTID": int(apn.replace("-", "")),
        "LotSize": lot_size,
        "Units": units,
        "SitusCity": "Berkeley",
        "SitusAddress": f"{apn} Test St",
        "BLDSQFTTAXABLE": units * 500 if units else 0,
        "tier1_zone": tier1_zone,
        "geometry": box(lon, lat, lon + d, lat + d),
    }


@pytest.fixture
def sample_parcels():
    """5 parcels with varying lot sizes, units, and tier zones."""
    rows = [
        make_parcel("001", lot_size=5000, units=2, tier1_zone="200ft", lon=-122.270, lat=37.870),
        make_parcel("002", lot_size=10000, units=0, tier1_zone="quarter_mile", lon=-122.272, lat=37.871),
        make_parcel("003", lot_size=8000, units=5, tier1_zone="half_mile", lon=-122.274, lat=37.872),
        make_parcel("004", lot_size=0, units=0, tier1_zone="200ft", lon=-122.276, lat=37.873),
        make_parcel("005", lot_size=43560, units=10, tier1_zone="quarter_mile", lon=-122.278, lat=37.874),
    ]
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


@pytest.fixture
def sample_parcels_with_zoning(sample_parcels):
    """Parcels with ZONECLASS/ZONEDESC already assigned."""
    parcels = sample_parcels.copy()
    parcels["ZONECLASS"] = ["R-1", "C-C", "R-3", "R-2", "R-1"]
    parcels["ZONEDESC"] = [
        "Residential Multi-Unit 1",
        "Community Commercial",
        "Multiple-Family Residential",
        "Residential Multi-Unit 2",
        "Residential Multi-Unit 1",
    ]
    return parcels


@pytest.fixture
def sample_zoning_districts():
    """Two large zone polygons that sample parcels will fall inside."""
    zone_r1 = box(-122.280, 37.869, -122.271, 37.875)
    zone_cc = box(-122.275, 37.869, -122.271, 37.875)
    rows = [
        {"ZONECLASS": "R-1", "ZONEDESC": "Residential Multi-Unit 1", "geometry": zone_r1},
        {"ZONECLASS": "C-C", "ZONEDESC": "Community Commercial", "geometry": zone_cc},
    ]
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


@pytest.fixture
def sample_southside_boundary():
    """Box covering parcel 003 (lon=-122.274, lat=37.872) for reclassification test."""
    boundary = box(-122.276, 37.871, -122.273, 37.873)
    return gpd.GeoDataFrame(
        [{"OBJECTID": 1, "geometry": boundary}],
        crs="EPSG:4326",
    )


@pytest.fixture
def gdf_no_crs():
    """GeoDataFrame with CRS explicitly set to None."""
    return gpd.GeoDataFrame(
        [{"val": 1, "geometry": Point(-122.27, 37.87)}],
    )


@pytest.fixture
def gdf_with_crs():
    """GeoDataFrame with CRS set to WGS84."""
    return gpd.GeoDataFrame(
        [{"val": 1, "geometry": Point(-122.27, 37.87)}],
        crs="EPSG:4326",
    )


@pytest.fixture
def sample_polygon_gdf():
    """Single polygon GeoDataFrame for ESRI conversion tests."""
    return gpd.GeoDataFrame(
        [{"id": 1, "geometry": box(-122.28, 37.86, -122.26, 37.88)}],
        crs="EPSG:4326",
    )


@pytest.fixture
def sample_multipolygon_gdf():
    """MultiPolygon GeoDataFrame for ESRI conversion tests."""
    p1 = box(-122.28, 37.86, -122.27, 37.87)
    p2 = box(-122.26, 37.86, -122.25, 37.87)
    return gpd.GeoDataFrame(
        [{"id": 1, "geometry": MultiPolygon([p1, p2])}],
        crs="EPSG:4326",
    )


@pytest.fixture
def duplicate_centroid_parcels():
    """Two parcels at same location — one with building, one without."""
    geom = box(-122.270, 37.870, -122.2695, 37.8705)
    rows = [
        {
            "APN": "DUP-001", "OBJECTID": 9001,
            "LotSize": 5000, "Units": 0, "BLDSQFTTAXABLE": 0,
            "tier1_zone": "200ft", "geometry": geom,
        },
        {
            "APN": "DUP-002", "OBJECTID": 9002,
            "LotSize": 5000, "Units": 3, "BLDSQFTTAXABLE": 1500,
            "tier1_zone": "200ft", "geometry": geom,
        },
    ]
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")
