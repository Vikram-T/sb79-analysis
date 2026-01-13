let map;
let currentPopup = null;
let overlappingFeatures = [];
let currentFeatureIndex = 0;
let currentPopupLocation = null;
let isNavigating = false;

// Load metadata and initialize map
fetch('data/map_metadata.json')
    .then(response => response.json())
    .then(metadata => {
        initializeMap(metadata);
        updateInfoPanel(metadata);
    })
    .catch(error => {
        console.error('Error loading map metadata:', error);
    });

function initializeMap(metadata) {
    map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {
                'osm': {
                    type: 'raster',
                    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                    tileSize: 256,
                    attribution: '© OpenStreetMap contributors'
                }
            },
            layers: [{
                id: 'osm',
                type: 'raster',
                source: 'osm'
            }]
        },
        center: metadata.center,
        zoom: 13,
        pitch: 0,
        bearing: 0
    });

    map.on('load', () => {
        map.addControl(new maplibregl.NavigationControl(), 'top-right');
        loadDataSources();
    });
}

function updateInfoPanel(metadata) {
    document.getElementById('city-name').textContent = metadata.city_name + ' SB-79 Analysis';
    document.getElementById('stat-transit').textContent = metadata.stats.transit_stops.toLocaleString();
    document.getElementById('stat-existing').textContent = metadata.stats.total_existing_units.toLocaleString();
    document.getElementById('stat-capacity').textContent = metadata.stats.total_potential_capacity.toLocaleString();
    document.getElementById('stat-net').textContent = metadata.stats.net_increase_capacity.toLocaleString();
}

function loadDataSources() {
    // Add city boundary source
    map.addSource('city-boundary', {
        type: 'geojson',
        data: 'data/city_boundary.geojson'
    });

    // Add transit stops source
    map.addSource('transit-stops', {
        type: 'geojson',
        data: 'data/transit_stops.geojson'
    });

    // Add parcel sources
    map.addSource('parcels-200ft', {
        type: 'geojson',
        data: 'data/parcels_200ft.geojson'
    });

    map.addSource('parcels-quarter-mile', {
        type: 'geojson',
        data: 'data/parcels_quarter_mile.geojson'
    });

    map.addSource('parcels-half-mile', {
        type: 'geojson',
        data: 'data/parcels_half_mile.geojson'
    });

    // Add layers
    addLayers();
    setupInteractivity();
}

function addLayers() {
    // City boundary
    map.addLayer({
        id: 'city-boundary-fill',
        type: 'fill',
        source: 'city-boundary',
        paint: {
            'fill-color': 'blue',
            'fill-opacity': 0.1
        }
    });

    map.addLayer({
        id: 'city-boundary-line',
        type: 'line',
        source: 'city-boundary',
        paint: {
            'line-color': 'darkblue',
            'line-width': 3
        }
    });

    // Half mile parcels (bottom layer)
    map.addLayer({
        id: 'parcels-half-fill',
        type: 'fill',
        source: 'parcels-half-mile',
        paint: {
            'fill-color': 'blue',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-half-line',
        type: 'line',
        source: 'parcels-half-mile',
        paint: {
            'line-color': 'blue',
            'line-width': 1
        }
    });

    // Quarter mile parcels
    map.addLayer({
        id: 'parcels-quarter-fill',
        type: 'fill',
        source: 'parcels-quarter-mile',
        paint: {
            'fill-color': 'green',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-quarter-line',
        type: 'line',
        source: 'parcels-quarter-mile',
        paint: {
            'line-color': 'green',
            'line-width': 1
        }
    });

    // 200ft parcels (top layer)
    map.addLayer({
        id: 'parcels-200ft-fill',
        type: 'fill',
        source: 'parcels-200ft',
        paint: {
            'fill-color': 'red',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-200ft-line',
        type: 'line',
        source: 'parcels-200ft',
        paint: {
            'line-color': 'red',
            'line-width': 1
        }
    });

    // Transit stops
    map.addLayer({
        id: 'transit-stops',
        type: 'circle',
        source: 'transit-stops',
        paint: {
            'circle-radius': 8,
            'circle-color': 'red',
            'circle-stroke-width': 2,
            'circle-stroke-color': 'white'
        }
    });
}

function createParcelPopupHTML(props, currentIndex, totalCount) {
    let html = '<div>';

    // Add navigation controls if there are multiple features
    if (totalCount > 1) {
        html += `<div style="margin-bottom: 10px; padding: 5px; background: #f0f0f0; border-radius: 4px;">`;
        html += `<strong>Parcel ${currentIndex + 1} of ${totalCount}</strong>`;
        html += `<div style="margin-top: 5px;">`;
        html += `<button onclick="window.previousParcel()" style="padding: 4px 8px; margin-right: 5px;">◀ Previous</button>`;
        html += `<button onclick="window.nextParcel()" style="padding: 4px 8px;">Next ▶</button>`;
        html += `</div></div>`;
    }

    if (props.APN) html += `<div class="popup-row"><strong>APN:</strong> ${props.APN}</div>`;
    if (props.SitusAddress) html += `<div class="popup-row"><strong>Address:</strong> ${props.SitusAddress}</div>`;
    if (props.LotSize !== undefined) html += `<div class="popup-row"><strong>Lot Size:</strong> ${props.LotSize.toLocaleString()} sq ft</div>`;
    if (props.ZONECLASS) html += `<div class="popup-row"><strong>Zone:</strong> ${props.ZONECLASS}</div>`;
    if (props.ZONEDESC) html += `<div class="popup-row"><strong>Zone Desc:</strong> ${props.ZONEDESC}</div>`;
    if (props.Units !== undefined) html += `<div class="popup-row"><strong>Existing Units:</strong> ${props.Units}</div>`;

    // Always display Potential Capacity and Net Increase, even if 0
    const potentialCapacity = props.PotentialCapacity !== undefined ? Math.round(props.PotentialCapacity) : 0;
    const netIncrease = props.NetIncreaseCapacity !== undefined ? Math.round(props.NetIncreaseCapacity) : 0;
    html += `<div class="popup-row"><strong>Potential Capacity:</strong> ${potentialCapacity}</div>`;
    html += `<div class="popup-row"><strong>Net Increase:</strong> ${netIncrease}</div>`;

    if (props.tier1_zone) html += `<div class="popup-row"><strong>Tier Zone:</strong> ${props.tier1_zone}</div>`;
    html += '</div>';

    return html;
}

function showParcelPopup(lngLat) {
    if (overlappingFeatures.length === 0) return;

    // Store the location for navigation
    currentPopupLocation = lngLat;

    const feature = overlappingFeatures[currentFeatureIndex];
    const html = createParcelPopupHTML(feature.properties, currentFeatureIndex, overlappingFeatures.length);

    if (currentPopup) {
        // Set flag to prevent clearing variables during navigation
        isNavigating = true;
        currentPopup.remove();
        isNavigating = false;
    }

    currentPopup = new maplibregl.Popup()
        .setLngLat(lngLat)
        .setHTML(html)
        .addTo(map);

    currentPopup.on('close', () => {
        // Only clear variables if not navigating between features
        if (!isNavigating) {
            currentPopup = null;
            overlappingFeatures = [];
            currentFeatureIndex = 0;
            currentPopupLocation = null;
        }
    });
}

// Global functions for popup navigation
window.nextParcel = function() {
    if (overlappingFeatures.length === 0 || !currentPopupLocation) return;
    currentFeatureIndex = (currentFeatureIndex + 1) % overlappingFeatures.length;
    showParcelPopup(currentPopupLocation);
};

window.previousParcel = function() {
    if (overlappingFeatures.length === 0 || !currentPopupLocation) return;
    currentFeatureIndex = (currentFeatureIndex - 1 + overlappingFeatures.length) % overlappingFeatures.length;
    showParcelPopup(currentPopupLocation);
};

function setupInteractivity() {
    // Popup for parcels with overlap support
    const parcelLayers = ['parcels-200ft-fill', 'parcels-quarter-fill', 'parcels-half-fill'];

    // Single click handler for all parcel layers
    map.on('click', (e) => {
        // Query all parcel layers at the click point
        const features = map.queryRenderedFeatures(e.point, {
            layers: parcelLayers
        });

        if (features.length > 0) {
            overlappingFeatures = features;
            currentFeatureIndex = 0;
            showParcelPopup(e.lngLat);
        }
    });

    // Hover cursor for all parcel layers
    parcelLayers.forEach(layer => {
        map.on('mouseenter', layer, () => {
            map.getCanvas().style.cursor = 'pointer';
        });

        map.on('mouseleave', layer, () => {
            map.getCanvas().style.cursor = '';
        });
    });

    // Popup for transit stops
    map.on('click', 'transit-stops', (e) => {
        const props = e.features[0].properties;

        let html = '<div><strong>Transit Stop</strong>';
        if (props.agency_primary) html += `<div class="popup-row"><strong>Agency:</strong> ${props.agency_primary}</div>`;
        if (props.hqta_type) html += `<div class="popup-row"><strong>Type:</strong> ${props.hqta_type}</div>`;
        if (props.stop_id) html += `<div class="popup-row"><strong>Stop ID:</strong> ${props.stop_id}</div>`;
        if (props.route_id) html += `<div class="popup-row"><strong>Route ID:</strong> ${props.route_id}</div>`;
        html += '</div>';

        new maplibregl.Popup()
            .setLngLat(e.lngLat)
            .setHTML(html)
            .addTo(map);
    });

    map.on('mouseenter', 'transit-stops', () => {
        map.getCanvas().style.cursor = 'pointer';
    });

    map.on('mouseleave', 'transit-stops', () => {
        map.getCanvas().style.cursor = '';
    });
}

// Layer toggles
document.getElementById('toggle-boundary').addEventListener('change', (e) => {
    const visibility = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty('city-boundary-fill', 'visibility', visibility);
    map.setLayoutProperty('city-boundary-line', 'visibility', visibility);
});

document.getElementById('toggle-transit').addEventListener('change', (e) => {
    const visibility = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty('transit-stops', 'visibility', visibility);
});

document.getElementById('toggle-200ft').addEventListener('change', (e) => {
    const visibility = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty('parcels-200ft-fill', 'visibility', visibility);
    map.setLayoutProperty('parcels-200ft-line', 'visibility', visibility);
});

document.getElementById('toggle-quarter').addEventListener('change', (e) => {
    const visibility = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty('parcels-quarter-fill', 'visibility', visibility);
    map.setLayoutProperty('parcels-quarter-line', 'visibility', visibility);
});

document.getElementById('toggle-half').addEventListener('change', (e) => {
    const visibility = e.target.checked ? 'visible' : 'none';
    map.setLayoutProperty('parcels-half-fill', 'visibility', visibility);
    map.setLayoutProperty('parcels-half-line', 'visibility', visibility);
});

// Opacity control
document.getElementById('opacity-slider').addEventListener('input', (e) => {
    const opacity = e.target.value / 100;
    document.getElementById('opacity-value').textContent = e.target.value;

    map.setPaintProperty('parcels-200ft-fill', 'fill-opacity', opacity);
    map.setPaintProperty('parcels-quarter-fill', 'fill-opacity', opacity);
    map.setPaintProperty('parcels-half-fill', 'fill-opacity', opacity);
});

