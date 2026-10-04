import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import maplibregl from 'maplibre-gl';
import waterClasses from '../../shared/water_classes.json';
import 'maplibre-gl/dist/maplibre-gl.css';
import { analysisForPair, assetUrl, type ComparisonData, type Observation } from '../lib/observations';
import { usePrefs } from '../lib/prefs';

export type ViewMode = 'before' | 'compare' | 'after' | 'change';
export type Basemap = 'plain' | 'streets' | 'imagery';
interface Props {
  data: ComparisonData;
  baseline: Observation;
  post: Observation;
  mode: ViewMode;
  basemap: Basemap;
  opacity: number;
  outline: boolean;
}
const baseStyle = (): maplibregl.StyleSpecification => ({
  version: 8,
  sources: {
    streets: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
    imagery: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 18, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#dce3df' } },
    { id: 'streets', type: 'raster', source: 'streets', layout: { visibility: 'none' } },
    { id: 'imagery', type: 'raster', source: 'imagery', layout: { visibility: 'none' } },
  ],
});
function updateDisplay(map: maplibregl.Map, basemap: Basemap, opacity: number, outline: boolean, mode: ViewMode, observationId: string) {
  for (const id of ['streets', 'imagery']) map.setLayoutProperty(id, 'visibility', id === basemap ? 'visible' : 'none');
  for (const layer of map.getStyle().layers) {
    if (!layer.id.startsWith('radar-')) continue;
    map.setLayoutProperty(layer.id, 'visibility', layer.id === 'radar-' + observationId ? 'visible' : 'none');
    map.setPaintProperty(layer.id, 'raster-opacity', opacity);
  }
  if (map.getLayer('water-change')) map.setLayoutProperty('water-change', 'visibility', mode === 'change' ? 'visible' : 'none');
  for (const id of ['boundary-halo', 'boundary-line']) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', outline ? 'visible' : 'none');
  }
}
function addObservation(map: maplibregl.Map, data: ComparisonData, observation: Observation) {
  const [west, south, east, north] = data.manifest.aoi.bounds;
  // Four local images are loaded once; selecting layers keeps cameras and
  // avoids stale async image replacements during rapid date changes.
  for (const item of data.manifest.observations) {
    const id = 'radar-' + item.id;
    map.addSource(id, { type: 'image', url: assetUrl(item.image_url), coordinates: [[west, north], [east, north], [east, south], [west, south]] });
    map.addLayer({ id, type: 'raster', source: id, layout: { visibility: item.id === observation.id ? 'visible' : 'none' }, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  }
  if (data.analysis) {
    map.addSource('water-change', { type: 'image', url: assetUrl(data.analysis.overlay_url), coordinates: [[west,north],[east,north],[east,south],[west,south]] });
    map.addLayer({ id: 'water-change', type: 'raster', source: 'water-change', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  }
  map.addSource('boundary', { type: 'geojson', data: data.boundary });
  map.addLayer({ id: 'boundary-halo', type: 'line', source: 'boundary', paint: { 'line-color': '#fff', 'line-width': 3.5, 'line-opacity': 0.8 } });
  map.addLayer({ id: 'boundary-line', type: 'line', source: 'boundary', paint: { 'line-color': '#087c75', 'line-width': 1.5, 'line-dasharray': [4, 3] } });
  const element = document.createElement('div');
  element.className = 'village-marker';
  element.innerHTML = '<span class="village-dot" aria-hidden="true"></span><span></span>';
  element.lastElementChild!.textContent = data.manifest.aoi.name;
  return new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(data.manifest.aoi.center).addTo(map);
}

export function ObservationMap({ data, baseline, post, mode, basemap, opacity, outline }: Props) {
  const { t, fd } = usePrefs();
  const selected = useRef({ before: baseline, after: post });
  selected.current = { before: baseline, after: post };
  const analysis = analysisForPair(data, baseline.id, post.id);
  const displayMode = mode === 'change' && !analysis ? 'compare' : mode;
  const wrapper = useRef<HTMLDivElement>(null);
  const afterContainer = useRef<HTMLDivElement>(null);
  const beforeContainer = useRef<HTMLDivElement>(null);
  const maps = useRef<maplibregl.Map[]>([]);
  const options = useRef({ basemap, opacity, outline, mode: displayMode });
  options.current = { basemap, opacity, outline, mode: displayMode };
  const [loaded, setLoaded] = useState({ before: '', after: '' });
  const [mapError, setMapError] = useState<string | null>(null);
  const [backgroundError, setBackgroundError] = useState(false);
  const [split, setSplit] = useState(50);
  const pointer = useRef<number | null>(null);

  useEffect(() => {
    if (!afterContainer.current || !beforeContainer.current) return;
    let disposed = false;
    const created: maplibregl.Map[] = [];
    const markers: maplibregl.Marker[] = [];
    const [west, south, east, north] = data.manifest.aoi.bounds;
    setLoaded({ before: '', after: '' });
    setMapError(null);
    const observer = new ResizeObserver(() => created.forEach((map) => map.resize()));
    try {
      const makeMap = (container: HTMLElement, side: 'before' | 'after') => {
        const map = new maplibregl.Map({
          container, style: baseStyle(),
          bounds: [[west, south], [east, north]], fitBoundsOptions: { padding: 48 },
          attributionControl: side === 'after' ? { compact: true } : false,
          interactive: side === 'after', dragRotate: false, pitchWithRotate: false,
          maxPitch: 0, minPitch: 0, maxZoom: 18,
        });
        created.push(map);
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        map.getCanvas().setAttribute('aria-label', 'Interactive radar map of ' + data.manifest.aoi.name);
        if (side === 'before') map.getCanvas().setAttribute('tabindex', '-1');
        map.on('error', (event) => {
          if (disposed) return;
          const sourceId = (event as unknown as { sourceId?: string }).sourceId;
          if (sourceId === 'streets' || sourceId === 'imagery') {
            setBackgroundError(true);
          } else {
            setMapError('The radar map could not be displayed. ' + event.error.message);
          }
        });
        map.on('load', () => {
          if (disposed) return;
          try {
            markers.push(addObservation(map, data, selected.current[side]));
            updateDisplay(map, options.current.basemap, options.current.opacity, options.current.outline, options.current.mode, selected.current[side].id);
          } catch (error) {
            setMapError('The radar map could not be displayed. ' + (error instanceof Error ? error.message : String(error)));
          }
        });
        map.on('idle', () => {
          const id = selected.current[side].id;
          if (!disposed && map.getSource('radar-' + id) && map.isSourceLoaded('radar-' + id) && (!data.analysis || (map.getSource('water-change') && map.isSourceLoaded('water-change')))) {
            setLoaded((current) => current[side] === id ? current : { ...current, [side]: id });
          }
        });
        map.getCanvas().addEventListener('webglcontextlost', (event) => {
          event.preventDefault();
          if (!disposed) setMapError('The graphics connection was interrupted. Reload the page to restore the radar map.');
        });
        return map;
      };
      const after = makeMap(afterContainer.current, 'after');
      const before = makeMap(beforeContainer.current, 'before');
      maps.current = [after, before];
      after.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 100 }), 'bottom-left');
      const sync = () => {
        if (!disposed) before.jumpTo({ center: after.getCenter(), zoom: after.getZoom(), bearing: 0, pitch: 0 });
      };
      after.on('move', sync);
      before.once('load', sync);
      if (wrapper.current) observer.observe(wrapper.current);
    } catch (error) {
      setMapError('The browser could not start the map. Enable WebGL or try another browser. ' + (error instanceof Error ? error.message : String(error)));
    }
    return () => {
      disposed = true;
      observer.disconnect();
      markers.forEach((marker) => marker.remove());
      created.forEach((map) => map.remove());
      maps.current = [];
    };
  }, [data]);

  useEffect(() => { setBackgroundError(false); }, [basemap]);

  useEffect(() => {
    for (const map of maps.current) map.getCanvas().setAttribute('aria-label', t('Interactive radar map of {name}', { name: data.manifest.aoi.name }));
  }, [t, data, loaded]);

  useEffect(() => {
    for (const [index, map] of maps.current.entries()) {
      const id = index === 0 ? post.id : baseline.id;
      if (map.getLayer('radar-' + id)) updateDisplay(map, basemap, opacity, outline, displayMode, id);
    }
  }, [basemap, opacity, outline, displayMode, baseline, post]);

  const updateSplit = (event: ReactPointerEvent<HTMLElement>) => {
    if (!wrapper.current) return;
    const bounds = wrapper.current.getBoundingClientRect();
    setSplit(Math.round(Math.max(0, Math.min(100, (event.clientX - bounds.left) / bounds.width * 100))));
  };
  const keyboardSplit = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 10 : 1;
    const actions: Record<string, number> = { ArrowLeft: -step, ArrowDown: -step, ArrowRight: step, ArrowUp: step, PageDown: -10, PageUp: 10 };
    if (event.key in actions || event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      event.stopPropagation();
      setSplit((value) => event.key === 'Home' ? 0 : event.key === 'End' ? 100 : Math.min(100, Math.max(0, value + actions[event.key])));
    }
  };
  const visibleSplit = mode === 'before' ? 100 : (mode === 'after' || mode === 'change') ? 0 : split;
  const leftLoaded = loaded.before === baseline.id;
  const rightLoaded = loaded.after === post.id;
  const ready = leftLoaded && rightLoaded;
  return <div className="comparison-map" ref={wrapper} data-testid="comparison-map" data-before-loaded={leftLoaded} data-after-loaded={rightLoaded} data-left-id={baseline.id} data-right-id={post.id} data-mode={mode} aria-label={t('Radar observations of Kalari Abdu')}>
    <div className="map map-after" ref={afterContainer} style={{ visibility: ready ? 'visible' : 'hidden' }} />
    <div className="map map-before" ref={beforeContainer} style={{ visibility: ready ? 'visible' : 'hidden', clipPath: 'inset(0 ' + (100 - visibleSplit) + '% 0 0)' }} aria-hidden="true" />
    {!ready && !mapError && <div className="map-loading" role="status">{t('Drawing radar observations…')}</div>}
    {mapError && <div className="map-failure" role="alert"><strong>{t('Map unavailable')}</strong><p>{mapError}</p><a href={assetUrl(baseline.image_url)} target="_blank" rel="noreferrer">{t('Open left image')}</a><a href={assetUrl(post.image_url)} target="_blank" rel="noreferrer">{t('Open right image')}</a></div>}
    {backgroundError && !mapError && <p className="basemap-error" role="status">{t('Background tiles unavailable. The local radar images still work; select Plain for an offline background.')}</p>}
    <div className="map-date-labels" aria-live="polite">
      {mode !== 'after' && mode !== 'change' && <div className="map-date before"><span>{t('Left image')}</span><strong>{fd(baseline.date)}</strong></div>}
      {mode !== 'before' && <div className="map-date after"><span>{mode === 'change' ? t('Changes between dates · unverified') : t('Right image')}</span><strong>{fd(post.date)}</strong></div>}
    </div>
    {displayMode === 'change' && <div className="change-legend" aria-label={t('Candidate change legend')}>
      <strong>{t('What the colours mean')}</strong>
      {['new', 'persistent', 'brighter'].map((key) => {
        const entry = waterClasses.classes.find((item) => item.key === key)!;
        return <span key={key}><i className="swatch" style={{ background: `rgb(${entry.rgba.slice(0, 3).join(',')})` }} />{t(entry.label)}</span>;
      })}
      <small>{t('Orange: brighter in September; water loss is unconfirmed.')}<br />{t('All colours need checking. Uncoloured areas may also contain water.')}</small>
    </div>}
    <div className="map-navigation" aria-label={t('Map controls')}>
      <span className="north-indicator" title={t('North is up')} aria-label={t('North is up')}>↑<small>N</small></span>
      <button aria-label={t('Zoom in')} onClick={() => maps.current[0]?.zoomIn({ duration: 0 })}>+</button>
      <button aria-label={t('Zoom out')} onClick={() => maps.current[0]?.zoomOut({ duration: 0 })}>−</button>
      <button className="reset-view" aria-label={t('Reset to study area')} title={t('Reset to study area')} onClick={() => {
        const [west, south, east, north] = data.manifest.aoi.bounds;
        maps.current[0]?.fitBounds([[west, south], [east, north]], { padding: 48, duration: 0 });
      }}><svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><circle cx="12" cy="12" r="3" /></svg></button>
    </div>
    {mode === 'compare' && <div className="swipe-divider" style={{ left: split + '%' }}>
      <div
        role="slider" tabIndex={0} aria-label={t('Left and right divider')} aria-orientation="horizontal"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={split}
        aria-valuetext={t('{left}% left image, {right}% right image', { left: split, right: 100 - split })}
        aria-describedby="divider-help" className="swipe-handle"
        onKeyDown={keyboardSplit}
        onPointerDown={(event) => { event.preventDefault(); event.stopPropagation(); pointer.current = event.pointerId; event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); updateSplit(event); }}
        onPointerMove={(event) => { if (pointer.current === event.pointerId) { event.stopPropagation(); updateSplit(event); } }}
        onPointerUp={(event) => { pointer.current = null; event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { pointer.current = null; }}
        onLostPointerCapture={() => { pointer.current = null; }}
      ><span aria-hidden="true">‹ ›</span></div>
    </div>}
    <span id="divider-help" className="sr-only">{t('Drag the divider or use the arrow keys. Home shows only right, End shows only left. Shift and arrow moves ten percent.')}</span>
    <span className="map-boundary-legend"><span aria-hidden="true" />{t('{r} km study radius', { r: data.manifest.aoi.radius_m / 1000 })}</span>
  </div>;
}
