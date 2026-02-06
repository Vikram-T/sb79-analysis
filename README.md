# SB-79 Analysis

A geospatial analysis tool to visualize California Senate Bill 79 (SB-79) housing density impacts on parcels near high-quality transit stops. This project creates interactive maps showing which parcels would be upzoned under SB-79 and calculates potential housing capacity.


# ✨[Live Demo](https://vikram-t.github.io/sb79-analysis/public/)✨

## What is SB-79?

SB-79 is California housing legislation that allows increased residential density near high-quality transit stops. 

For more details take a look at the legislation: https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB79 or the pdf in this repo

## Features

- **Automated Data Collection**: Can pull real-time data from California State APIs (city boundaries, transit stops, parcels, zoning)
- **SB-79 Tier Classification**: Categorizes parcels by distance from transit stops (200ft, quarter-mile, half-mile zones)
- **Capacity Calculations**: Computes potential increase in housing capacity per SB-79 regulations
- **Local Caching**: GeoPackage storage for faster repeat runs without API calls
- **Static Deployment**: Frontend deployable to any static hosting (Cloudflare Pages, Netlify, etc.)
- **Currently Supports**: Berkeley, CA 

## Useful links
- https://berkeley.maps.arcgis.com/apps/webappviewer/index.html?id=2c7dfafbb1f64e159f4fdf28a52f51c6&showLayers=Berkeley%20Parcels;Base%20Data;Planning%20and%20Building
  - Web viewer for the various berkeley apis that exist

## Project Structure

```
sb79-analysis/
├── backend/                    # Python data processing
│   ├── pipeline.py            # Generic SB-79 pipeline (fetch, process, export)
│   ├── berkeley.py            # Berkeley-specific config and overlays
│   ├── city_config.py         # CityConfig dataclass (add new cities here)
│   ├── config.py              # State-level constants and API endpoints
│   ├── geo_utils.py           # Reusable geospatial utilities (CRS, ESRI, pagination)
│   ├── data_store.py          # Local data storage utilities (GeoPackage)
│   ├── data/                  # Cached data and reference CSVs
│   │   ├── berkeley_data.gpkg              # GeoPackage with all layers
│   │   ├── berkeley_data.metadata.json     # Data source metadata
│   │   ├── zoning_limits.csv               # City zoning height/density limits
│   │   └── sb79_limits.csv                 # SB-79 tier height/density minimums
│   └── tests/                 # pytest test suite
│       ├── conftest.py        # Shared GeoDataFrame fixtures
│       ├── test_geo_utils.py  # Tests for geospatial utilities
│       ├── test_pipeline.py   # Tests for generic pipeline functions
│       └── test_berkeley.py   # Tests for Berkeley-specific functions
├── public/                    # Frontend (static site - deployment ready)
│   ├── index.html            # Main map interface
│   ├── style.css             # Styles
│   ├── map.js               # MapLibre GL JS implementation
│   └── data/                # Generated GeoJSON files (for map)
│       ├── city_boundary.geojson
│       ├── transit_stops.geojson
│       ├── parcels.geojson
│       └── map_metadata.json
├── 20250SB79_84.pdf          # SB-79 legislation text
├── pyproject.toml            # Python dependencies (uv)
└── README.md
```

## How to Use

### Installation

1. Ensure you have Python 3.14+ installed and uv
2. Install dependencies:
```bash
uv sync --group dev   # includes pytest for testing
```

### Running the Analysis

**First run** (fetch data from APIs):
```bash
cd backend
# In config.py, set: USE_LOCAL_DATA = False
uv run berkeley.py
```

This will:
1. Fetch Data
   1. Fetch city boundary from California State Geoportal
   2. Fetch high-quality transit stops within Berkeley
   3. Fetch zoning districts from City GIS 
   4. Fetch all parcels within 0.5 miles of transit stops (in three zones: 200ft, quarter-mile, half-mile)
2. Combine Data
   1. Add zoning information to each parcel using spatial join
   2. Add SB-79 Height Limits
3. Filter Data
   1. Filter for residential, commercial, and mixed-use parcels only  
   2. Filter out parcels with zero lot size
   3. Filter out parcels with the same centroid
   4. Remove duplicate parcels sharing the same centroid (keeps only parcels with BLDSQFTTAXABLE = 0)
4. Calculate potential capacity based on SB-79 density limits and lot size
   ```python
   density_value = {
      DENSITY_200FT = 160 du/acre
      DENSITY_QUARTER_MILE = 140 du/acre
      DENSITY_HALF_MILE = 120 du/acre
   }
   total_net_capacity = 0
   for parcel in all parcels:
      parcel_capacity = max(parcel_area * density_value - existing_capacity)
      total_net_capacity += parcel_capacity
   ```
   - To see the actual formula see `add_potential_and_net_capacity()` in pipeline.py
5. Save all data to `backend/berkeley_data.gpkg` for future use
6. Export GeoJSON files to `public/data/` for the map

**Subsequent runs** (use cached data):
```bash
cd backend
# In config.py, set: USE_LOCAL_DATA = True
uv run berkeley.py
```

This loads data from the local GeoPackage, which is much faster.

### Viewing Results

The script will output capacity calculations:

Example:
```bash
✓ Capacity Summary by Tier Zone w/ net increase calculations:
  - 200ft zone: 121 existing / 3155 potential (22 parcels)
  - Quarter mile zone: 6012 existing / 24595 potential (1604 parcels)
  - Half mile zone: 14672 existing / 55678 potential (4762 parcels)
  - Total: 20805 existing / 83430 potential units
  - Net new capacity: 83430 units
```

### Viewing the Interactive Map

**Local Development:**
```bash
cd public
python -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Running Tests

```bash
uv run pytest -v
```

66 tests covering the pure pipeline functions (capacity calculations, zoning limits, parcel filtering, geospatial utilities).

## Adding a New City

The pipeline is driven by `CityConfig` (defined in `city_config.py`). To add a new city, define a config object in `berkeley.py` (or a new file) and call `process_city()`:

```python
from city_config import CityConfig

OAKLAND_CONFIG = CityConfig(
    name="Oakland",
    parcel_api="https://...",
    zoning_api="https://...",
    parcel_city_field="SitusCity",
    parcel_city_value="Oakland",
)

process_city(OAKLAND_CONFIG)
```

Optional fields: `zone_prefix_filter`, `zoning_limits_csv`, `transit_stop_where`, `overlays` (list of `Callable[[GeoDataFrame], GeoDataFrame]` for city-specific post-processing like Berkeley's Southside Plan reclassification).

## Configuration

Edit `config.py` to customize:
- State-level API endpoints (city boundaries, transit stops)
- SB-79 density limits (`DENSITY_200FT`, `DENSITY_QUARTER_MILE`, `DENSITY_HALF_MILE`)
- Data caching behavior (`USE_LOCAL_DATA`)

## TODOs

### Features
- [ ] Add zones that can be deferred to the next RHNA cycle
   - [ ] Very High Fire Hazard Severity Zones
   - [ ] Areas vulnerable to 1 foot of sea level rise
   - [ ] Sites with a locally designated historical resource (designated as of 1/1/2025)
   - [ ] Sites and station areas meeting minimum local zoning standards:
      - [ ] A site allowing at least 50% of the density & FAR allowed by SB 79
      - [ ] A station area where at least 33% of sites allow at least half the density/FAR allowed by SB 79, and where the station area cumulatively allows for at least 75% of the aggregate density as SB 79
      - [ ] A station area that is primarily “low resource” on the TCAC Opportunity Maps, and that cumulatively allows at least 40% of the aggregate density as SB 79
      - [ ] Any site within a low resource area if the city cumulatively allows at least 50% of the aggregate transit-oriented density as SB 79


### General Code Cleanup
- [ ] Confirm the Net Capacity Calculation with someone
- [ ] Look into moving data saving out of this function so we always pull from local data and update with a different function
- [x] Wire CityConfig through the pipeline so adding a new city is just a config object
- [x] Add pytest test suite for pure pipeline functions

