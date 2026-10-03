import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Bounds, Manifest, RankedUnit } from '../lib/types';
import { fmtDate, itemForDate } from '../lib/analysis';

export type Basemap = 'imagery' | 'streets';

export interface LayerState {
  basemap: Basemap;
  duration: boolean;
  water: boolean;
  places: boolean;
  radar: boolean;
  aux: string | null; // id of the context dataset shown, if any
  opacity: number; // 0..1 for the flood layers
}

interface Props {
  manifest: Manifest;
  ranked: RankedUnit[];
  passIndex: number;
  comparePassIndex: number | null; // when set, the map shows a before/after swipe
  layers: LayerState;
  selectedId: string | null;
  focus: { id: string; n: number } | null;
  onSelect: (id: string) => void;
}

const corners = (b: Bounds) =>
  [
    [b[0], b[3]],
    [b[2], b[3]],
    [b[2], b[1]],
    [b[0], b[1]],
  ] as [[number, number], [number, number], [number, number], [number, number]];

const waterUrl = (m: Manifest, i: number) => m.layers.water.url_template.replace('{date}', m.passes[i].date);

/** Radar image for a pass: same date if there is one, else the latest earlier one. */
const radarUrl = (m: Manifest, i: number) => {
  const r = m.layers.radar;
  if (!r || !r.dates.length) return null;
  const d = itemForDate(r.dates.map((date) => ({ date })), m.passes[i].date)?.date ?? r.dates[0];
  return r.url_template.replace('{date}', d);
};

const auxFor = (m: Manifest, id: string | null, i: number) => {
  const layer = m.aux_layers?.find((a) => a.id === id) ?? m.aux_layers?.[0];
  if (!layer) return null;
  const item = itemForDate(layer.items, m.passes[i].date);
  return item ? { url: item.url, bounds: layer.bounds } : null;
};

/** Point the per-pass image layers (water, radar, context data) at one pass. */
function showPass(map: maplibregl.Map, m: Manifest, i: number, auxId: string | null) {
  (map.getSource('water') as maplibregl.ImageSource | undefined)?.updateImage({ url: waterUrl(m, i), coordinates: corners(m.layers.water.bounds) });
  const r = radarUrl(m, i);
  if (r && m.layers.radar) (map.getSource('radar') as maplibregl.ImageSource | undefined)?.updateImage({ url: r, coordinates: corners(m.layers.radar.bounds) });
  const a = auxFor(m, auxId, i);
  if (a) (map.getSource('aux') as maplibregl.ImageSource | undefined)?.updateImage({ url: a.url, coordinates: corners(a.bounds) });
}

function baseStyle(): maplibregl.StyleSpecification {
  return {
    version: 8,
    sources: {
      imagery: {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 18,
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
      },
      streets: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© OpenStreetMap contributors',
      },
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#dfe6e3' } },
      { id: 'imagery', type: 'raster', source: 'imagery', paint: { 'raster-saturation': -0.35 } },
      { id: 'streets', type: 'raster', source: 'streets', layout: { visibility: 'none' }, paint: { 'raster-saturation': -0.6 } },
    ],
  };
}

/** Adds every data layer to a map. Used for the main map and the "before" map of the swipe. */
function addDataLayers(map: maplibregl.Map, m: Manifest, passIndex: number, withPlaces: boolean) {
  const r = radarUrl(m, passIndex);
  if (r && m.layers.radar) {
    map.addSource('radar', { type: 'image', url: r, coordinates: corners(m.layers.radar.bounds) });
    map.addLayer({ id: 'radar', type: 'raster', source: 'radar', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0 } });
  }
  const a = auxFor(m, null, passIndex);
  if (a) {
    map.addSource('aux', { type: 'image', url: a.url, coordinates: corners(a.bounds) });
    map.addLayer({ id: 'aux', type: 'raster', source: 'aux', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.75, 'raster-fade-duration': 0 } });
  }
  map.addSource('duration', { type: 'image', url: m.layers.flood_duration.url, coordinates: corners(m.layers.flood_duration.bounds) });
  map.addLayer({ id: 'duration', type: 'raster', source: 'duration', paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } });
  map.addSource('water', { type: 'image', url: waterUrl(m, passIndex), coordinates: corners(m.layers.water.bounds) });
  map.addLayer({ id: 'water', type: 'raster', source: 'water', paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } });
  if (!withPlaces) return;
  map.addSource('units', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: 'units-fill',
    type: 'fill',
    source: 'units',
    paint: {
      'fill-color': ['case', ['get', 'flooded'], '#c98b1a', '#3f7d4f'],
      'fill-opacity': ['case', ['get', 'flooded'], 0.28, 0.12],
    },
  });
  map.addLayer({
    id: 'units-line',
    type: 'line',
    source: 'units',
    paint: {
      'line-color': ['case', ['get', 'flooded'], '#8a5d0b', '#2f5e3b'],
      'line-width': ['case', ['get', 'flooded'], 1.6, 1],
      'line-dasharray': ['case', ['==', ['get', 'type'], 'cropland'], ['literal', [2, 1.5]], ['literal', [1, 0]]],
    },
  });
  map.addLayer({
    id: 'units-selected',
    type: 'line',
    source: 'units',
    filter: ['==', ['get', 'id'], ''],
    paint: { 'line-color': '#ffffff', 'line-width': 4 },
  });
  map.addLayer({
    id: 'units-selected-inner',
    type: 'line',
    source: 'units',
    filter: ['==', ['get', 'id'], ''],
    paint: { 'line-color': '#1d2b30', 'line-width': 2 },
  });
}

function applyLayerState(map: maplibregl.Map, layers: LayerState, withPlaces: boolean) {
  map.setLayoutProperty('imagery', 'visibility', layers.basemap === 'imagery' ? 'visible' : 'none');
  map.setLayoutProperty('streets', 'visibility', layers.basemap === 'streets' ? 'visible' : 'none');
  map.setLayoutProperty('duration', 'visibility', layers.duration ? 'visible' : 'none');
  map.setLayoutProperty('water', 'visibility', layers.water ? 'visible' : 'none');
  map.setPaintProperty('duration', 'raster-opacity', layers.opacity);
  map.setPaintProperty('water', 'raster-opacity', layers.opacity);
  if (map.getLayer('radar')) map.setLayoutProperty('radar', 'visibility', layers.radar ? 'visible' : 'none');
  if (map.getLayer('aux')) map.setLayoutProperty('aux', 'visibility', layers.aux ? 'visible' : 'none');
  if (withPlaces) {
    for (const id of ['units-fill', 'units-line', 'units-selected', 'units-selected-inner']) {
      map.setLayoutProperty(id, 'visibility', layers.places ? 'visible' : 'none');
    }
  }
}

function newMap(container: HTMLElement, m: Manifest, interactive = true) {
  const [w, s, e, n] = m.aoi.bounds;
  return new maplibregl.Map({
    container,
    style: baseStyle(),
    bounds: [
      [w, s],
      [e, n],
    ],
    fitBoundsOptions: { padding: 24 },
    attributionControl: { compact: true },
    interactive,
    dragRotate: false,
    pitchWithRotate: false,
  });
}

export function MapView({ manifest, ranked, passIndex, comparePassIndex, layers, selectedId, focus, onSelect }: Props) {
  const mainEl = useRef<HTMLDivElement>(null);
  const beforeEl = useRef<HTMLDivElement>(null);
  const wrapEl = useRef<HTMLDivElement>(null);
  const mainMap = useRef<maplibregl.Map | null>(null);
  const beforeMap = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [beforeReady, setBeforeReady] = useState(false);
  const [split, setSplit] = useState(0.5);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Main map: created once.
  useEffect(() => {
    if (!mainEl.current) return;
    const map = newMap(mainEl.current, manifest);
    mainMap.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    map.on('load', () => {
      if (mainMap.current !== map) return; // a map discarded by a re-mount
      addDataLayers(map, manifest, passIndex, true);
      setReady(true);
    });
    map.on('click', 'units-fill', (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) onSelectRef.current(id);
    });
    map.on('mouseenter', 'units-fill', () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', 'units-fill', () => (map.getCanvas().style.cursor = ''));
    return () => {
      setReady(false);
      mainMap.current = null;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest]);

  // "Before" map for the swipe: exists only while comparing.
  const comparing = comparePassIndex !== null;
  useEffect(() => {
    if (!comparing || !beforeEl.current || !mainMap.current) return;
    const main = mainMap.current;
    const map = newMap(beforeEl.current, manifest, false);
    beforeMap.current = map;
    const sync = () => {
      map.jumpTo({ center: main.getCenter(), zoom: main.getZoom(), bearing: main.getBearing(), pitch: main.getPitch() });
    };
    map.on('load', () => {
      if (beforeMap.current !== map) return;
      addDataLayers(map, manifest, comparePassIndex ?? 0, false);
      sync();
      setBeforeReady(true);
    });
    main.on('move', sync);
    return () => {
      main.off('move', sync);
      setBeforeReady(false);
      beforeMap.current = null;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comparing, manifest]);

  // Per-pass images follow the selected pass (and the chosen context dataset).
  useEffect(() => {
    const map = mainMap.current;
    if (ready && map) showPass(map, manifest, passIndex, layers.aux);
  }, [ready, passIndex, manifest, layers.aux]);

  useEffect(() => {
    const map = beforeMap.current;
    if (beforeReady && map && comparePassIndex !== null) showPass(map, manifest, comparePassIndex, layers.aux);
  }, [beforeReady, comparePassIndex, manifest, layers.aux]);

  // Layer toggles.
  useEffect(() => {
    if (ready && mainMap.current) applyLayerState(mainMap.current, layers, true);
  }, [ready, layers]);
  useEffect(() => {
    if (beforeReady && beforeMap.current) applyLayerState(beforeMap.current, layers, false);
  }, [beforeReady, layers]);

  // Places: status and rank depend on the pass and on the weights.
  useEffect(() => {
    const map = mainMap.current;
    if (!ready || !map) return;
    (map.getSource('units') as maplibregl.GeoJSONSource | undefined)?.setData({
      type: 'FeatureCollection',
      features: ranked.map((r) => ({
        type: 'Feature',
        geometry: r.feature.geometry,
        properties: { id: r.props.id, type: r.props.type, flooded: r.floodedNow, rank: r.rank },
      })),
    });
  }, [ready, ranked]);

  // Rank badges for the top five flooded places (HTML markers: no font server needed).
  const markers = useRef<maplibregl.Marker[]>([]);
  useEffect(() => {
    const map = mainMap.current;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];
    if (!ready || !map || !layers.places) return;
    ranked
      .filter((r) => r.floodedNow && r.rank <= 5)
      .forEach((r) => {
        const el = document.createElement('button');
        el.className = 'rank-badge';
        el.textContent = String(r.rank);
        el.title = `Priority ${r.rank}: ${r.props.name}`;
        el.addEventListener('click', (ev) => {
          ev.stopPropagation();
          onSelectRef.current(r.props.id);
        });
        markers.current.push(new maplibregl.Marker({ element: el }).setLngLat(r.props.centroid).addTo(map));
      });
  }, [ready, ranked, layers.places]);

  useEffect(() => {
    const map = mainMap.current;
    if (!ready || !map) return;
    const f: maplibregl.FilterSpecification = ['==', ['get', 'id'], selectedId ?? ''];
    map.setFilter('units-selected', f);
    map.setFilter('units-selected-inner', f);
  }, [ready, selectedId]);

  // Fly to a place picked from the list.
  useEffect(() => {
    const map = mainMap.current;
    if (!ready || !map || !focus) return;
    const r = ranked.find((x) => x.props.id === focus.id);
    if (!r) return;
    const ring = r.feature.geometry.coordinates[0];
    const xs = ring.map((c) => c[0]);
    const ys = ring.map((c) => c[1]);
    map.fitBounds(
      [
        [Math.min(...xs), Math.min(...ys)],
        [Math.max(...xs), Math.max(...ys)],
      ],
      { padding: 120, maxZoom: 14.5, duration: 900 },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focus]);

  // Swipe handle.
  const dragging = useRef(false);
  useEffect(() => {
    const move = (ev: PointerEvent) => {
      if (!dragging.current || !wrapEl.current) return;
      const box = wrapEl.current.getBoundingClientRect();
      setSplit(Math.min(0.95, Math.max(0.05, (ev.clientX - box.left) / box.width)));
    };
    const up = () => (dragging.current = false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, []);

  const pass = manifest.passes[passIndex];
  return (
    <div className="map-wrap" ref={wrapEl}>
      <div ref={mainEl} className="map" aria-label="Flood map" />
      {comparing && (
        <>
          <div
            ref={beforeEl}
            className="map map-before"
            style={{ clipPath: `inset(0 ${100 - split * 100}% 0 0)` }}
            aria-hidden="true"
          />
          <div className="swipe" style={{ left: `${split * 100}%` }}>
            <button
              className="swipe-handle"
              aria-label="Drag to compare passes"
              onPointerDown={(e) => {
                dragging.current = true;
                (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
              }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowLeft') setSplit((s) => Math.max(0.05, s - 0.05));
                if (e.key === 'ArrowRight') setSplit((s) => Math.min(0.95, s + 0.05));
              }}
            />
          </div>
          <div className="swipe-label left">{fmtDate(manifest.passes[comparePassIndex].date, true)}</div>
          <div className="swipe-label right">{fmtDate(pass.date, true)}</div>
        </>
      )}
    </div>
  );
}
