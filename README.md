# SB-79 Analysis

A geospatial analysis tool to visualize California Senate Bill 79 (SB-79) housing density impacts on parcels near high-quality transit stops. This project creates interactive maps showing which parcels would be upzoned under SB-79 and calculates potential housing capacity.

## What is SB-79?

SB-79 is California housing legislation that allows increased residential density near high-quality transit stops. 

For more details take a look at the legislation: https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB79 or the pdf in this repo

## Features

- Fetches city boundaries, transit stops, parcels, and zoning data from California State APIs
- Categorizes parcels into SB-79 tiers based on distance from high-quality transit stops
- Calculates potential housing capacity for each parcel based on lot size and density limits
- Generates interactive Folium maps with color-coded parcel layers
- Supports local data caching (GeoPackage format) to reduce API calls
- Currently configured for Berkeley, CA 

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

The script will output some calculations on the net capacity increase

Example:
```bash

✓ Capacity Summary by Tier Zone w/ net increase calculations:
  - 200ft zone: 452 existing / 3155 potential (24 parcels)
  - Quarter mile zone: 6675 existing / 24843 potential (1696 parcels)
  - Half mile zone: 22380 existing / 56648 potential (5432 parcels)
  - Total: 29507 existing / 84647 potential units
  - Net new capacity: 84647 units
```

It will also output `city_boundary.html` an interactive map. The map includes:
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

## TODOs


- [ ] Figure out why some parcels are overlapping
- [ ] Figure out why some parcels show 0 LotSize but have a large number of existing units
- [ ] Confirm the Net Capacity Calculation with someone 
- [ ] Look into making  API request batching a generic so we don't repeat functionality get_zoning_districts and get_parcels_near_transit_stops 
- [ ] Look into moving data saving out of this function so we always pull from local data and update with a different function 
