import geopandas as gpd

from pipeline import (
    add_potential_and_net_capacity,
    add_sb79_limits,
    load_sb79_limits,
    filter_zero_lotsize_parcels,
    filter_parcels_with_same_centroid,
    add_zoning_to_parcels,
)
from berkeley import load_zoning_limits, add_zoning_limits
from config import DENSITY_200FT, DENSITY_QUARTER_MILE, DENSITY_HALF_MILE


SQFT_PER_ACRE = 43560


# =========================================================================
# load_zoning_limits (uses real CSV)
# =========================================================================

class TestLoadZoningLimits:
    def test_loads_successfully(self):
        limits = load_zoning_limits()
        assert "height" in limits
        assert "max_density" in limits

    def test_contains_known_zones(self):
        limits = load_zoning_limits()
        assert "R-1" in limits["height"]
        assert "C-C" in limits["height"]
        assert "R-3S" in limits["height"]

    def test_r1_height_is_35(self):
        limits = load_zoning_limits()
        assert limits["height"]["R-1"] == 35

    def test_r3s_height_is_45(self):
        limits = load_zoning_limits()
        assert limits["height"]["R-3S"] == 45

    def test_r1_max_density_is_70(self):
        limits = load_zoning_limits()
        assert limits["max_density"]["R-1"] == 70


# =========================================================================
# load_sb79_limits (uses real CSV)
# =========================================================================

class TestLoadSb79Limits:
    def test_loads_successfully(self):
        limits = load_sb79_limits()
        assert len(limits) > 0

    def test_contains_all_three_tiers(self):
        limits = load_sb79_limits()
        assert "200ft" in limits
        assert "quarter_mile" in limits
        assert "half_mile" in limits

    def test_adjacent_is_95ft(self):
        limits = load_sb79_limits()
        assert limits["200ft"] == 95

    def test_quarter_mile_is_75ft(self):
        limits = load_sb79_limits()
        assert limits["quarter_mile"] == 75

    def test_half_mile_is_65ft(self):
        limits = load_sb79_limits()
        assert limits["half_mile"] == 65


# =========================================================================
# add_potential_and_net_capacity
# =========================================================================

class TestAddPotentialAndNetCapacity:
    def test_returns_none_for_none_input(self):
        assert add_potential_and_net_capacity(None) is None

    def test_adds_potential_capacity_column(self, sample_parcels):
        result = add_potential_and_net_capacity(sample_parcels)
        assert "PotentialCapacity" in result.columns

    def test_adds_net_increase_capacity_column(self, sample_parcels):
        result = add_potential_and_net_capacity(sample_parcels)
        assert "NetIncreaseCapacity" in result.columns

    def test_200ft_density_calculation(self, sample_parcels):
        """Parcel 001: LotSize=5000, tier=200ft -> (5000/43560)*160"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "001"].iloc[0]
        expected = (5000 / SQFT_PER_ACRE) * DENSITY_200FT
        assert abs(row["PotentialCapacity"] - expected) < 0.01

    def test_quarter_mile_density_calculation(self, sample_parcels):
        """Parcel 002: LotSize=10000, tier=quarter_mile -> (10000/43560)*120"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "002"].iloc[0]
        expected = (10000 / SQFT_PER_ACRE) * DENSITY_QUARTER_MILE
        assert abs(row["PotentialCapacity"] - expected) < 0.01

    def test_half_mile_density_calculation(self, sample_parcels):
        """Parcel 003: LotSize=8000, tier=half_mile -> (8000/43560)*100"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "003"].iloc[0]
        expected = (8000 / SQFT_PER_ACRE) * DENSITY_HALF_MILE
        assert abs(row["PotentialCapacity"] - expected) < 0.01

    def test_one_acre_parcel_equals_density(self, sample_parcels):
        """Parcel 005: LotSize=43560 (1 acre), tier=quarter_mile -> exactly 120"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "005"].iloc[0]
        assert abs(row["PotentialCapacity"] - DENSITY_QUARTER_MILE) < 0.01

    def test_zero_lotsize_gives_zero_capacity(self, sample_parcels):
        """Parcel 004: LotSize=0 -> 0 capacity"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "004"].iloc[0]
        assert row["PotentialCapacity"] == 0

    def test_net_increase_subtracts_existing_units(self, sample_parcels):
        """Parcel 001: potential ~18.37, existing=2 -> net ~16.37"""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "001"].iloc[0]
        expected_net = row["PotentialCapacity"] - 2
        assert abs(row["NetIncreaseCapacity"] - expected_net) < 0.01

    def test_net_increase_cannot_be_negative(self, sample_parcels):
        result = add_potential_and_net_capacity(sample_parcels)
        assert (result["NetIncreaseCapacity"] >= 0).all()

    def test_vacant_parcel_net_equals_potential(self, sample_parcels):
        """Parcel 002: Units=0, so net should equal potential."""
        result = add_potential_and_net_capacity(sample_parcels)
        row = result[result["APN"] == "002"].iloc[0]
        assert abs(row["NetIncreaseCapacity"] - row["PotentialCapacity"]) < 0.01


# =========================================================================
# add_sb79_limits (pipeline — state-level SB-79 minimums)
# =========================================================================

class TestAddSb79Limits:
    def test_returns_none_for_none_input(self):
        assert add_sb79_limits(None) is None

    def test_returns_empty_for_empty_gdf(self):
        empty = gpd.GeoDataFrame()
        result = add_sb79_limits(empty)
        assert len(result) == 0

    def test_adds_sb79_height_limit(self, sample_parcels_with_zoning):
        result = add_sb79_limits(sample_parcels_with_zoning)
        assert "SB79HeightLimit" in result.columns

    def test_200ft_zone_gets_95ft_sb79_height(self, sample_parcels_with_zoning):
        result = add_sb79_limits(sample_parcels_with_zoning)
        zone_200ft = result[result["tier1_zone"] == "200ft"]
        assert (zone_200ft["SB79HeightLimit"] == 95).all()


# =========================================================================
# add_zoning_limits (berkeley — city-specific zoning limits)
# =========================================================================

class TestAddZoningLimits:
    def test_returns_none_for_none_input(self):
        assert add_zoning_limits(None, {}) is None

    def test_returns_empty_for_empty_gdf(self):
        empty = gpd.GeoDataFrame()
        result = add_zoning_limits(empty, {})
        assert len(result) == 0

    def test_adds_current_height_limit(self, sample_parcels_with_zoning):
        result = add_zoning_limits(sample_parcels_with_zoning, load_zoning_limits())
        assert "CurrentHeightLimit" in result.columns

    def test_adds_current_max_density(self, sample_parcels_with_zoning):
        result = add_zoning_limits(sample_parcels_with_zoning, load_zoning_limits())
        assert "CurrentMaxDensity" in result.columns

    def test_adds_current_zoned_capacity(self, sample_parcels_with_zoning):
        result = add_zoning_limits(sample_parcels_with_zoning, load_zoning_limits())
        assert "CurrentZonedCapacity" in result.columns

    def test_r1_gets_35ft_height(self, sample_parcels_with_zoning):
        result = add_zoning_limits(sample_parcels_with_zoning, load_zoning_limits())
        r1_rows = result[result["ZONECLASS"] == "R-1"]
        assert (r1_rows["CurrentHeightLimit"] == 35).all()


# =========================================================================
# filter_zero_lotsize_parcels
# =========================================================================

class TestFilterZeroLotsizeParcels:
    def test_returns_none_for_none_input(self):
        assert filter_zero_lotsize_parcels(None) is None

    def test_removes_zero_lotsize(self, sample_parcels):
        result = filter_zero_lotsize_parcels(sample_parcels)
        assert (result["LotSize"] > 0).all()

    def test_correct_count_after_filter(self, sample_parcels):
        """sample_parcels has 1 parcel with LotSize=0 (APN 004)."""
        result = filter_zero_lotsize_parcels(sample_parcels)
        assert len(result) == len(sample_parcels) - 1

    def test_specific_parcel_removed(self, sample_parcels):
        result = filter_zero_lotsize_parcels(sample_parcels)
        assert "004" not in result["APN"].values

    def test_preserves_valid_parcels(self, sample_parcels):
        result = filter_zero_lotsize_parcels(sample_parcels)
        assert "001" in result["APN"].values
        assert "005" in result["APN"].values


# =========================================================================
# filter_parcels_with_same_centroid
# =========================================================================

class TestFilterParcelsWithSameCentroid:
    def test_returns_none_for_none_input(self):
        assert filter_parcels_with_same_centroid(None) is None

    def test_returns_empty_for_empty_gdf(self):
        empty = gpd.GeoDataFrame()
        result = filter_parcels_with_same_centroid(empty)
        assert len(result) == 0

    def test_removes_duplicate_with_building(self, duplicate_centroid_parcels):
        result = filter_parcels_with_same_centroid(duplicate_centroid_parcels)
        assert "DUP-001" in result["APN"].values
        assert "DUP-002" not in result["APN"].values

    def test_no_duplicates_returns_unchanged(self, sample_parcels):
        result = filter_parcels_with_same_centroid(sample_parcels)
        assert len(result) == len(sample_parcels)


# =========================================================================
# add_zoning_to_parcels
# =========================================================================

class TestAddZoningToParcels:
    def test_returns_parcels_if_zones_none(self, sample_parcels):
        result = add_zoning_to_parcels(sample_parcels, None)
        assert result is sample_parcels

    def test_returns_none_if_parcels_none(self, sample_zoning_districts):
        result = add_zoning_to_parcels(None, sample_zoning_districts)
        assert result is None

    def test_adds_zoneclass_column(self, sample_parcels, sample_zoning_districts):
        result = add_zoning_to_parcels(sample_parcels, sample_zoning_districts)
        assert "ZONECLASS" in result.columns

    def test_adds_zonedesc_column(self, sample_parcels, sample_zoning_districts):
        result = add_zoning_to_parcels(sample_parcels, sample_zoning_districts)
        assert "ZONEDESC" in result.columns

    def test_preserves_parcel_count(self, sample_parcels, sample_zoning_districts):
        result = add_zoning_to_parcels(sample_parcels, sample_zoning_districts)
        assert len(result) == len(sample_parcels)
