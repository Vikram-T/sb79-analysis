# SB-79 Analysis

A geospatial analysis tool to visualize California Senate Bill 79 (SB-79) housing density impacts on parcels near high-quality transit stops. This project creates interactive maps showing which parcels would be upzoned under SB-79 and calculates potential housing capacity.

## What is SB-79?

SB-79 is California housing legislation that allows increased residential density near high-quality transit stops. The law establishes three distance-based tiers:
- **200ft zone**: Up to 160 units/acre (0-200 feet from transit)
- **Quarter-mile zone**: Up to 120 units/acre (200ft - 0.25 miles from transit)
- **Half-mile zone**: Up to 100 units/acre (0.25 - 0.5 miles from transit)

## Features

- Fetches city boundaries, transit stops, parcels, and zoning data from California State APIs
- Categorizes parcels into SB-79 tiers based on distance from high-quality transit stops
- Calculates potential housing capacity for each parcel based on lot size and density limits
- Generates interactive Folium maps with color-coded parcel layers
- Supports local data caching (GeoPackage format) to reduce API calls
- Currently configured for Berkeley, CA (easily adaptable to other California cities)

## Project Structure

- `berkeley.py` - Main analysis script that fetches data, processes parcels, and generates maps
- `config.py` - Configuration file with API endpoints, SB-79 density parameters, and settings
- `data_store.py` - Local data storage module for caching GeoDataFrames
- `data/` - Directory for local GeoPackage data snapshots
- `city_boundary.html` - Generated interactive map (output)

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
# In config.py, set: USE_LOCAL_DATA = False
uv run berkeley.py
```

This will:
1. Fetch city boundary from California State Geoportal
2. Fetch high-quality transit stops within Berkeley
3. Fetch zoning districts from Berkeley's GIS
4. Fetch all parcels within 0.5 miles of transit stops
5. Add zoning information to each parcel
6. Calculate potential capacity based on SB-79 density limits
7. Save all data to `data/berkeley_data.gpkg` for future use
8. Generate `city_boundary.html` interactive map

**Subsequent runs** (use cached data):
```bash
# In config.py, set: USE_LOCAL_DATA = True
uv run berkeley.py
```

This loads data from the local GeoPackage, which is much faster.

### Viewing Results

Open `city_boundary.html` in a web browser to explore the interactive map. The map includes:
- City boundary (blue outline)
- High-quality transit stops (red markers)
- Parcels color-coded by tier:
  - Red: 200ft zone (0-200ft from transit)
  - Green: Quarter-mile zone (200ft - 0.25mi)
  - Blue: Half-mile zone (0.25 - 0.5mi)

Click on parcels to see details including address, APN, zoning, existing units, and potential capacity.

## Configuration

Edit `config.py` to customize:
- API endpoints (change city APIs for other locations)
- SB-79 density limits (`DENSITY_200FT`, `DENSITY_QUARTER_MILE`, `DENSITY_HALF_MILE`)
- Data caching behavior (`USE_LOCAL_DATA`)
- Map display settings

## Future Goals

- Compare SB-79 capacity to local planning capacity to verify compliance
- Extend analysis to other California cities
- Add filtering by existing zoning type
- Generate comparative reports and statistics
