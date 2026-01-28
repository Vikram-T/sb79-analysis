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
    document.getElementById('stat-net').textContent = metadata.stats.net_increase_capacity.toLocaleString();

    // Update zone-specific statistics
    document.getElementById('stat-200ft-parcels').textContent = metadata.stats.parcels_200ft.toLocaleString();
    document.getElementById('stat-200ft-existing').textContent = metadata.stats.existing_units_200ft.toLocaleString();
    document.getElementById('stat-200ft-capacity').textContent = (Math.round(metadata.stats.net_increase_capacity_200ft*100)/100).toLocaleString();
    document.getElementById('stat-quarter-parcels').textContent = metadata.stats.parcels_quarter_mile.toLocaleString();
    document.getElementById('stat-quarter-existing').textContent = metadata.stats.existing_units_quarter.toLocaleString();
    document.getElementById('stat-quarter-capacity').textContent = (Math.round(metadata.stats.net_increase_capacity_quarter*100)/100).toLocaleString();
    document.getElementById('stat-half-parcels').textContent = metadata.stats.parcels_half_mile.toLocaleString();
    document.getElementById('stat-half-existing').textContent = metadata.stats.existing_units_half.toLocaleString();
    document.getElementById('stat-half-capacity').textContent = (Math.round(metadata.stats.net_increase_capacity_half*100)/100).toLocaleString();

    // Load and populate transit stops list from GeoJSON
    loadTransitStopsList();

    // Setup toggle button for transit stops list
    const toggleButton = document.getElementById('toggle-transit-list');
    const transitStopsList = document.getElementById('transit-stops-list');

    toggleButton.addEventListener('click', () => {
        transitStopsList.classList.toggle('hidden');
        toggleButton.textContent = transitStopsList.classList.contains('hidden') ? 'Show List' : 'Hide List';
    });
}

function loadTransitStopsList() {
    fetch('data/transit_stops.geojson')
        .then(response => response.json())
        .then(data => {
            const transitStopsItems = document.getElementById('transit-stops-items');
            transitStopsItems.innerHTML = '';

            data.features.forEach(feature => {
                const props = feature.properties;
                const coords = feature.geometry.coordinates;

                const li = document.createElement('li');
                li.style.cursor = 'pointer';
                li.innerHTML = `
                    <div class="stop-id">Stop ID: ${props.stop_id || 'N/A'}</div>
                    <div class="stop-agency">${props.agency_primary || 'N/A'}</div>
                    <div class="stop-agency">${props.hqta_type || 'N/A'}</div>
                `;

                // Add click handler to zoom to and highlight the stop
                li.addEventListener('click', () => {
                    // Close any existing popups first
                    if (currentPopup) {
                        currentPopup.remove();
                        currentPopup = null;
                    }

                    // Fly to the transit stop
                    map.flyTo({
                        center: coords,
                        zoom: 17,
                        duration: 1500
                    });

                    // Show popup for the stop
                    let html = '<div><strong>Transit Stop</strong>';
                    if (props.agency_primary) html += `<div class="popup-row"><strong>Agency:</strong> ${props.agency_primary}</div>`;
                    if (props.hqta_type) html += `<div class="popup-row"><strong>Type:</strong> ${props.hqta_type}</div>`;
                    if (props.stop_id) html += `<div class="popup-row"><strong>Stop ID:</strong> ${props.stop_id}</div>`;
                    if (props.route_id) html += `<div class="popup-row"><strong>Route ID:</strong> ${props.route_id}</div>`;
                    html += '</div>';

                    currentPopup = new maplibregl.Popup()
                        .setLngLat(coords)
                        .setHTML(html)
                        .addTo(map);

                    currentPopup.on('close', () => {
                        currentPopup = null;
                    });
                });

                transitStopsItems.appendChild(li);
            });
        })
        .catch(error => {
            console.error('Error loading transit stops:', error);
        });
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

    // Add single parcel source - all parcels with tier1_zone property
    map.addSource('parcels', {
        type: 'geojson',
        data: 'data/parcels.geojson'
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

    // Half mile parcels (bottom layer) - filtered from single source
    map.addLayer({
        id: 'parcels-half-fill',
        type: 'fill',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], 'half_mile'],
        paint: {
            'fill-color': 'blue',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-half-line',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], 'half_mile'],
        paint: {
            'line-color': 'blue',
            'line-width': 1
        }
    });

    // Quarter mile parcels - filtered from single source
    map.addLayer({
        id: 'parcels-quarter-fill',
        type: 'fill',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], 'quarter_mile'],
        paint: {
            'fill-color': 'purple',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-quarter-line',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], 'quarter_mile'],
        paint: {
            'line-color': 'purple',
            'line-width': 1
        }
    });

    // 200ft parcels (top layer) - filtered from single source
    map.addLayer({
        id: 'parcels-200ft-fill',
        type: 'fill',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], '200ft'],
        paint: {
            'fill-color': 'red',
            'fill-opacity': 0.4
        }
    });

    map.addLayer({
        id: 'parcels-200ft-line',
        type: 'line',
        source: 'parcels',
        filter: ['==', ['get', 'tier1_zone'], '200ft'],
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

    // Height limits
    if (props.CurrentHeightLimit !== undefined && props.CurrentHeightLimit !== null) {
        html += `<div class="popup-row"><strong>Current Height Limit:</strong> ${props.CurrentHeightLimit} ft</div>`;
    }
    if (props.SB79HeightLimit !== undefined && props.SB79HeightLimit !== null) {
        html += `<div class="popup-row"><strong>SB-79 Height Limit:</strong> ${props.SB79HeightLimit} ft</div>`;
    }

    // Always display Potential Capacity and Net Increase, even if 0
    const potentialCapacity = props.PotentialCapacity !== undefined ? Math.round(props.PotentialCapacity*10)/10 : 0;
    const netIncrease = props.NetIncreaseCapacity !== undefined ? Math.round(props.NetIncreaseCapacity*10)/10 : 0;
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

// Sidebar resize functionality
const resizeHandle = document.querySelector('.resize-handle');
const sidebar = document.querySelector('.sidebar');
let isResizing = false;

resizeHandle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
    isResizing = true;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';

    // Disable map dragging
    if (map) {
        map.dragPan.disable();
    }
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    e.preventDefault();
    const newWidth = e.clientX;
    const minWidth = 250;
    const maxWidth = 800;

    if (newWidth >= minWidth && newWidth <= maxWidth) {
        sidebar.style.width = newWidth + 'px';
        // Trigger map resize to adjust to new sidebar width
        if (map) {
            map.resize();
        }
    }
});

document.addEventListener('mouseup', () => {
    if (isResizing) {
        isResizing = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        // Re-enable map dragging
        if (map) {
            map.dragPan.enable();
        }
    }
});

// Mobile menu toggle
const menuToggle = document.getElementById('menu-toggle');
const sidebarElement = document.querySelector('.sidebar');

menuToggle.addEventListener('click', () => {
    sidebarElement.classList.toggle('open');
});

// Close sidebar when clicking on map area on mobile
document.getElementById('map').addEventListener('click', () => {
    if (window.innerWidth <= 768 && sidebarElement.classList.contains('open')) {
        sidebarElement.classList.remove('open');
    }
});

