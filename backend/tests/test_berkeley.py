import geopandas as gpd

from berkeley import reclassify_r3_in_southside


# =========================================================================
# reclassify_r3_in_southside (Berkeley-specific)
# =========================================================================

class TestReclassifyR3InSouthside:
    def test_returns_parcels_unchanged_if_none_boundary(self, sample_parcels_with_zoning):
        result = reclassify_r3_in_southside(sample_parcels_with_zoning, None)
        assert result is sample_parcels_with_zoning

    def test_returns_none_if_none_parcels(self):
        result = reclassify_r3_in_southside(None, gpd.GeoDataFrame())
        assert result is None

    def test_reclassifies_r3_inside_boundary(self, sample_parcels_with_zoning, sample_southside_boundary):
        """Parcel 003 is R-3 at lon=-122.274, lat=37.872, inside the boundary."""
        result = reclassify_r3_in_southside(sample_parcels_with_zoning, sample_southside_boundary)
        row = result[result["APN"] == "003"].iloc[0]
        assert row["ZONECLASS"] == "R-3S"
        assert "Southside" in row["ZONEDESC"]

    def test_does_not_reclassify_non_r3(self, sample_parcels_with_zoning, sample_southside_boundary):
        result = reclassify_r3_in_southside(sample_parcels_with_zoning, sample_southside_boundary)
        r1_row = result[result["APN"] == "001"].iloc[0]
        assert r1_row["ZONECLASS"] == "R-1"

    def test_does_not_modify_original(self, sample_parcels_with_zoning, sample_southside_boundary):
        original_zone = sample_parcels_with_zoning[sample_parcels_with_zoning["APN"] == "003"].iloc[0]["ZONECLASS"]
        reclassify_r3_in_southside(sample_parcels_with_zoning, sample_southside_boundary)
        after_zone = sample_parcels_with_zoning[sample_parcels_with_zoning["APN"] == "003"].iloc[0]["ZONECLASS"]
        assert original_zone == after_zone
