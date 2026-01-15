# SB-79 Analysis

A geospatial analysis tool to visualize California Senate Bill 79 (SB-79) housing density impacts on parcels near high-quality transit stops. This project creates interactive maps showing which parcels would be upzoned under SB-79 and calculates potential housing capacity.


# ✨[Live Demo](https://vikram-t.github.io/sb79-analysis/public/)✨

## What is SB-79?

SB-79 is California housing legislation that allows increased residential density near high-quality transit stops. 

For more details take a look at the legislation: https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB79 or the pdf in this repo

## Features

- **Automated Data Collection**: Can pull real-time data from California State APIs (city boundaries, transit stops, parcels, zoning)
- **SB-79 Tier Classification**: Categorizes parcels by distance from transit stops (200ft, quarter-mile, half-mile zones)
- **Capacity Calculations**: Computes potential and net increase housing capacity per SB-79 regulations
- **Local Caching**: GeoPackage storage for faster repeat runs without API calls
- **Static Deployment**: Frontend deployable to any static hosting (Cloudflare Pages, Netlify, etc.)
- **Currently Supports**: Berkeley, CA 

## Project Structure

```
sb79-analysis/
├── backend/                    # Python data processing
│   ├── berkeley.py            # Main script to fetch and process data
│   ├── config.py              # Configuration and API endpoints
│   ├── data_store.py          # Local data storage utilities (GeoPackage)
│   └── data/                  # Cached data (generated)
│       ├── berkeley_data.gpkg              # GeoPackage with all layers
│       └── berkeley_data.metadata.json     # Data source metadata
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
2. Use uv sync to install dependencies:
```bash
uv sync
```

### Running the Analysis

**First run** (fetch data from APIs):
```bash
cd backend
# In config.py, set: USE_LOCAL_DATA = False
uv run berkeley.py
```

This will:
1. Fetch city boundary from California State Geoportal
2. Fetch high-quality transit stops within Berkeley
3. Fetch zoning districts from Berkeley's GIS
4. Fetch all parcels within 0.5 miles of transit stops (in three zones: 200ft, quarter-mile, half-mile)
5. Add zoning information to each parcel using spatial join
6. Filter for residential, commercial, and mixed-use parcels only (ZONECLASS: R-*, C-*, ES-R)
7. Filter out parcels with zero lot size
8. Calculate potential capacity based on SB-79 density limits and lot size
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
   - To see the actual formula see `add_potential_and_net_capacity()` in berkeley.py
10. Remove duplicate parcels sharing the same centroid (keeps only parcels with BLDSQFTTAXABLE = 0)
11. Save all data to `backend/berkeley_data.gpkg` for future use
12. Export GeoJSON files to `public/data/` for the map

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

## Configuration

Edit `config.py` to customize:
- API endpoints (change city APIs for other locations)
- SB-79 density limits (`DENSITY_200FT`, `DENSITY_QUARTER_MILE`, `DENSITY_HALF_MILE`)
- Data caching behavior (`USE_LOCAL_DATA`)
- Map display settings

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
- [ ] Look into making  API request batching a generic so we don't repeat functionality get_zoning_districts and get_parcels_near_transit_stops 
- [ ] Look into moving data saving out of this function so we always pull from local data and update with a different function 

