import json
from unittest.mock import Mock

from shapely.geometry import Point

from geo_utils import (
    ensure_crs,
    project_to_utm,
    project_to_wgs84,
    polygon_to_esri_geometry,
    point_to_esri_geometry,
    validate_api_response,
)


# =========================================================================
# ensure_crs
# =========================================================================

class TestEnsureCrs:
    def test_returns_none_for_none_input(self):
        assert ensure_crs(None) is None

    def test_sets_wgs84_when_crs_missing(self, gdf_no_crs):
        result = ensure_crs(gdf_no_crs)
        assert result.crs is not None
        assert result.crs.to_epsg() == 4326

    def test_preserves_existing_crs(self, gdf_with_crs):
        result = ensure_crs(gdf_with_crs)
        assert result.crs.to_epsg() == 4326

    def test_sets_custom_crs_when_missing(self, gdf_no_crs):
        result = ensure_crs(gdf_no_crs, crs="EPSG:3857")
        assert result.crs.to_epsg() == 3857

    def test_does_not_override_existing_crs(self, gdf_with_crs):
        result = ensure_crs(gdf_with_crs, crs="EPSG:3857")
        # CRS was already 4326, should stay 4326
        assert result.crs.to_epsg() == 4326


# =========================================================================
# project_to_utm / project_to_wgs84
# =========================================================================

class TestProjections:
    def test_project_to_utm_returns_utm_crs(self, gdf_with_crs):
        result = project_to_utm(gdf_with_crs)
        # Berkeley is in UTM zone 10N (EPSG:32610)
        assert result.crs.to_epsg() == 32610

    def test_project_to_utm_handles_no_crs(self, gdf_no_crs):
        result = project_to_utm(gdf_no_crs)
        assert result.crs is not None
        assert result.crs.to_epsg() != 4326

    def test_project_to_wgs84(self, gdf_with_crs):
        utm = project_to_utm(gdf_with_crs)
        back = project_to_wgs84(utm)
        assert back.crs.to_epsg() == 4326

    def test_roundtrip_preserves_geometry(self, gdf_with_crs):
        original_x = gdf_with_crs.geometry.iloc[0].x
        original_y = gdf_with_crs.geometry.iloc[0].y
        roundtripped = project_to_wgs84(project_to_utm(gdf_with_crs))
        assert abs(roundtripped.geometry.iloc[0].x - original_x) < 1e-6
        assert abs(roundtripped.geometry.iloc[0].y - original_y) < 1e-6


# =========================================================================
# polygon_to_esri_geometry
# =========================================================================

class TestPolygonToEsriGeometry:
    def test_single_polygon_has_rings(self, sample_polygon_gdf):
        result = polygon_to_esri_geometry(sample_polygon_gdf)
        assert "rings" in result
        assert "spatialReference" in result
        assert result["spatialReference"]["wkid"] == 4326
        assert len(result["rings"]) == 1

    def test_multipolygon_has_two_rings(self, sample_multipolygon_gdf):
        result = polygon_to_esri_geometry(sample_multipolygon_gdf)
        assert len(result["rings"]) == 2

    def test_ring_coordinates_are_number_pairs(self, sample_polygon_gdf):
        result = polygon_to_esri_geometry(sample_polygon_gdf)
        ring = result["rings"][0]
        # A box has 5 coordinates (closed ring)
        assert len(ring) >= 4
        for coord in ring:
            assert len(coord) == 2
            assert isinstance(coord[0], float)
            assert isinstance(coord[1], float)


# =========================================================================
# point_to_esri_geometry
# =========================================================================

class TestPointToEsriGeometry:
    def test_basic_conversion(self):
        point = Point(-122.27, 37.87)
        result = point_to_esri_geometry(point)
        assert result["x"] == -122.27
        assert result["y"] == 37.87
        assert result["spatialReference"]["wkid"] == 4326


# =========================================================================
# validate_api_response
# =========================================================================

class TestValidateApiResponse:
    def test_valid_200_response(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"features": []}
        is_valid, data, err = validate_api_response(mock_resp)
        assert is_valid is True
        assert data == {"features": []}
        assert err is None

    def test_non_200_status_code(self):
        mock_resp = Mock()
        mock_resp.status_code = 500
        is_valid, data, err = validate_api_response(mock_resp)
        assert is_valid is False
        assert data is None
        assert "500" in err

    def test_invalid_json(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("err", "doc", 0)
        is_valid, data, err = validate_api_response(mock_resp)
        assert is_valid is False
        assert "Invalid JSON" in err

    def test_error_key_with_dict_message(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": {"message": "Query failed", "code": 400}
        }
        is_valid, data, err = validate_api_response(mock_resp)
        assert is_valid is False
        assert "Query failed" in err

    def test_error_key_with_string_message(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "Something went wrong"}
        is_valid, data, err = validate_api_response(mock_resp)
        assert is_valid is False
