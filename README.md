# SB-79 Analysis

A geospatial analysis tool to visualize California Senate Bill 79 (SB-79) housing density impacts on parcels near high-quality transit stops. This project creates interactive maps showing which parcels would be upzoned under SB-79 and calculates potential housing capacity.

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
│       ├── parcels_200ft.geojson
│       ├── parcels_quarter_mile.geojson
│       ├── parcels_half_mile.geojson
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
   - total_units_tier1 = (area_200ft * 160units/acre + area_quarter_mile * 120units/acre + area_half_mile * 100units/acre) 
   - total_units_tier2 = (area_200ft * 140units/acre + area_quarter_mile * 100units/acre + area_half_mile * 80units/acre) 
9. Calculate net increase capacity as per SB-79 65912.161.(a)(1)
   - total_units_tier1 - existing_unit_capacity
   - total_units_tier2 - existing_unit_capacity
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
  - 200ft zone: 452 existing / 3155 potential (24 parcels)
  - Quarter mile zone: 6675 existing / 24843 potential (1696 parcels)
  - Half mile zone: 22380 existing / 56648 potential (5432 parcels)
  - Total: 29507 existing / 84647 potential units
  - Net new capacity: 84647 units
```

### Viewing the Interactive Map

**Local Development:**
```bash
cd public
python -m http.server 8000
# Open http://localhost:8000 in your browser
```

**Deploy to Cloudflare Pages:**
1. Push your repository to GitHub
2. Connect to Cloudflare Pages
3. Set build directory to `public`
4. Deploy!

The map includes:
- **Layer Controls**: Toggle visibility of city boundary, transit stops, and parcel zones
- **Opacity Control**: Adjust transparency of parcel layers (0-100%)
- **Interactive Popups**: Click parcels to see details 

**Parcel color-coding by tier:**
- Red: 200ft zone (0-200ft from transit)
- Green: Quarter-mile zone (200ft - 0.25mi)
- Blue: Half-mile zone (0.25 - 0.5mi)

## Configuration

Edit `config.py` to customize:
- API endpoints (change city APIs for other locations)
- SB-79 density limits (`DENSITY_200FT`, `DENSITY_QUARTER_MILE`, `DENSITY_HALF_MILE`)
- Data caching behavior (`USE_LOCAL_DATA`)
- Map display settings

## TODOs

- [ ] Confirm the Net Capacity Calculation with someone 
- [ ] Look into making  API request batching a generic so we don't repeat functionality get_zoning_districts and get_parcels_near_transit_stops 
- [ ] Look into moving data saving out of this function so we always pull from local data and update with a different function 
