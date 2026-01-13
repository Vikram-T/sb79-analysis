# config.py
# API endpoints and dataset identifiers for SB-79 mapping

# California State Geoportal endpoints
CITY_BOUNDARIES_URL = "https://services3.arcgis.com/uknczv4rpevve42E/arcgis/rest/services/California_Cities_and_Identifiers_Blue_Version_view/FeatureServer/2/query"

HIGH_QUALITY_TRANSIT_STOPS_URL = "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Stops/FeatureServer/0/query"

BERKELEY_PARCEL_API = "https://gis.cityofberkeley.info/arcgis3/rest/services/Public/GISPortal/MapServer/1/query"
BERKELEY_ZONING_API = "https://gis.cityofberkeley.info/arcgis3/rest/services/Public/Portal_Planning/MapServer/7/query"

# SB-79 parameters
TIER1_BUFFER_MILES = 0.5
TIER2_BUFFER_MILES = 0.25

# SB-79 density limits (units per acre)
DENSITY_200FT = 160  # 0-200ft from transit
DENSITY_QUARTER_MILE = 120  # 200ft-0.25mi from transit
DENSITY_HALF_MILE = 100  # 0.25-0.5mi from transit

# Data storage settings
USE_LOCAL_DATA = True  # Set to True to load from local GeoPackage instead of API
DATA_DIR = "./data"  # Directory for storing local data snapshots