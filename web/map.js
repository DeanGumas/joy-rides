// MapLibre setup: 3D terrain, imagery, slope overlay, runs and lifts.
import * as maplibregl from 'maplibre-gl';

export const DIFFICULTY = {
  green: { label: 'Easy', color: '#2f9e44' },
  blue: { label: 'Intermediate', color: '#1c6fe3' },
  black: { label: 'Advanced', color: '#111111' },
  'double-black': { label: 'Expert', color: '#111111' },
  freeride: { label: 'Freeride', color: '#f08c00' },
  unknown: { label: 'Unrated', color: '#868e96' },
};

const MAPTERHORN = 'https://tiles.mapterhorn.com/tilejson.json';
const USGS_IMAGERY = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}';
const FONT = ['Noto Sans Medium'];

const difficultyColor = ['match', ['get', 'difficulty'],
  ...Object.entries(DIFFICULTY).flatMap(([k, v]) => [k, v.color]), '#868e96'];

// Layer groups the UI can toggle.
export const GROUPS = {
  runs: ['run-areas', 'runs-casing', 'runs', 'runs-expert'],
  lifts: ['lifts-casing', 'lifts', 'stations'],
  labels: ['run-labels', 'lift-labels'],
  slope: ['slope'],
  hillshade: ['hillshade'],
};

function rasterSource(meta, product) {
  return {
    type: 'raster',
    tiles: [`${location.origin}/tiles/${product}/{z}/{x}/{y}.webp`],
    tileSize: meta.tileSize, minzoom: meta.minzoom, maxzoom: meta.maxzoom, bounds: meta.bounds,
    attribution: product === 'slope' ? 'Slope: USGS 3DEP 1m lidar' : `Imagery: USDA NAIP ${meta.naip ?? ''}`.trim(),
  };
}

function buildStyle(meta) {
  const geo = (name) => ({ type: 'geojson', data: `${location.origin}/geo/${name}.geojson`, promoteId: 'id' });
  const sources = {
    usgs: { type: 'raster', tiles: [USGS_IMAGERY], tileSize: 256, maxzoom: 16, attribution: 'USGS The National Map' },
    terrain: { type: 'raster-dem', url: MAPTERHORN, tileSize: 512, encoding: 'terrarium' },
    shade: { type: 'raster-dem', url: MAPTERHORN, tileSize: 512, encoding: 'terrarium' },
    runs: { ...geo('runs'), attribution: '© OpenStreetMap contributors (ODbL)' },
    areas: geo('areas'),
    lifts: geo('lifts'),
    stations: geo('stations'),
  };
  const layers = [
    { id: 'usgs', type: 'raster', source: 'usgs' },
  ];
  if (meta) {
    for (const p of ['summer', 'winter', 'slope']) sources[p] = rasterSource(meta, p);
    layers.push(
      { id: 'summer', type: 'raster', source: 'summer' },
      { id: 'winter', type: 'raster', source: 'winter', layout: { visibility: 'none' } },
    );
  }
  layers.push({
    id: 'hillshade', type: 'hillshade', source: 'shade',
    paint: { 'hillshade-exaggeration': 0.3, 'hillshade-shadow-color': '#1b2a3a', 'hillshade-highlight-color': '#ffffff' },
  });
  if (meta) {
    layers.push({ id: 'slope', type: 'raster', source: 'slope', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.55 } });
  }
  // Zoom expressions must be top-level, so scaled widths get their own interpolation.
  const runWidth = (k = 1) => ['interpolate', ['linear'], ['zoom'], 12, 1.4 * k, 14, 2.8 * k, 16, 5 * k];
  layers.push(
    { id: 'run-areas', type: 'fill', source: 'areas', paint: { 'fill-color': difficultyColor, 'fill-opacity': 0.15 } },
    {
      id: 'runs-selected', type: 'line', source: 'runs', filter: ['==', ['get', 'id'], ''],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffd43b', 'line-width': runWidth(3.2), 'line-opacity': 0.9 },
    },
    {
      id: 'runs-casing', type: 'line', source: 'runs',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': runWidth(2), 'line-opacity': 0.75 },
    },
    {
      id: 'runs', type: 'line', source: 'runs', filter: ['!=', ['get', 'difficulty'], 'double-black'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': difficultyColor, 'line-width': runWidth() },
    },
    {
      id: 'runs-expert', type: 'line', source: 'runs', filter: ['==', ['get', 'difficulty'], 'double-black'],
      layout: { 'line-join': 'round' },
      paint: { 'line-color': '#111111', 'line-width': runWidth(), 'line-dasharray': [2, 1] },
    },
    {
      id: 'lifts-casing', type: 'line', source: 'lifts',
      paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2.5, 16, 5], 'line-opacity': 0.8 },
    },
    {
      id: 'lifts', type: 'line', source: 'lifts',
      paint: { 'line-color': '#c92a2a', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 16, 3] },
    },
    {
      id: 'stations', type: 'circle', source: 'stations', minzoom: 13,
      paint: { 'circle-radius': 3, 'circle-color': '#c92a2a', 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 },
    },
    {
      id: 'run-labels', type: 'symbol', source: 'runs', minzoom: 13.8,
      layout: {
        'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'name'], ''], 'text-font': FONT,
        'text-size': ['interpolate', ['linear'], ['zoom'], 13.8, 12, 16, 15], 'text-max-angle': 35,
      },
      paint: { 'text-color': '#111', 'text-halo-color': 'rgba(255,255,255,0.9)', 'text-halo-width': 1.6 },
    },
    {
      id: 'lift-labels', type: 'symbol', source: 'lifts', minzoom: 12.5,
      layout: {
        'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'name'], ''], 'text-font': FONT,
        'text-size': 12, 'text-max-angle': 30,
      },
      paint: { 'text-color': '#8f1d1d', 'text-halo-color': 'rgba(255,255,255,0.95)', 'text-halo-width': 1.8 },
    },
  );

  return {
    version: 8,
    glyphs: 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
    sources,
    layers,
    terrain: { source: 'terrain', exaggeration: 1 },
    sky: {
      'sky-color': '#7fb4e6', 'horizon-color': '#e8f1fa', 'fog-color': '#e8f1fa',
      'sky-horizon-blend': 0.6, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.85, 'atmosphere-blend': 0,
    },
  };
}

const INTERACTIVE = ['runs', 'runs-expert', 'lifts', 'run-areas'];

export function createMap(container, meta, { onSelect, onHover }) {
  const map = new maplibregl.Map({
    container,
    style: buildStyle(meta),
    center: [-119.028, 37.641],
    zoom: 14,
    pitch: 64,
    bearing: 205,
    maxPitch: 85,
    hash: true, // camera in the URL, so views are shareable
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.FullscreenControl(), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-right');

  for (const id of INTERACTIVE) {
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }
  map.on('click', (e) => {
    const f = map.queryRenderedFeatures(e.point, { layers: INTERACTIVE.filter((l) => map.getLayer(l)) })[0];
    onSelect(f ? { ...f.properties, kind: f.layer.id.startsWith('lift') ? 'lift' : 'run' } : null);
  });
  let pending = null;
  map.on('mousemove', (e) => {
    clearTimeout(pending);
    pending = setTimeout(() => onHover(e.lngLat), 120);
  });

  // Resolves once the style has loaded (map.loaded() is also false while tiles stream in).
  const ready = new Promise((resolve) => map.once('load', resolve));

  return {
    map,
    ready,
    setSeason(season) {
      if (!map.getLayer('summer')) return;
      map.setLayoutProperty('summer', 'visibility', season === 'summer' ? 'visible' : 'none');
      map.setLayoutProperty('winter', 'visibility', season === 'winter' ? 'visible' : 'none');
      // Outside the rendered area, fade the summer basemap so the seams aren't jarring.
      map.setPaintProperty('usgs', 'raster-saturation', season === 'winter' ? -0.7 : 0);
      map.setPaintProperty('usgs', 'raster-brightness-min', season === 'winter' ? 0.35 : 0);
    },
    setGroup(group, visible) {
      for (const id of GROUPS[group]) {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
      }
    },
    setExaggeration(v) {
      map.setTerrain({ source: 'terrain', exaggeration: v });
    },
    highlight(id) {
      map.setFilter('runs-selected', ['==', ['get', 'id'], id ?? '']);
    },
    flyToFeature(feature) {
      const coords = feature.geometry.type === 'Polygon' ? feature.geometry.coordinates[0] : feature.geometry.coordinates;
      const bounds = coords.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(coords[0], coords[0]));
      const cam = map.cameraForBounds(bounds, { padding: 120, bearing: map.getBearing() });
      if (cam) map.flyTo({ ...cam, zoom: Math.min(cam.zoom - 0.4, 16), pitch: 60, duration: 1800 });
    },
  };
}
