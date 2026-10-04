import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';

export interface Observation {
  id: string;
  date: string;
  role: 'baseline' | 'post-event';
  label: string;
  image_url: string;
  source_product: string;
  beam_mode: string;
  polarization: string;
  orbit_direction: string;
  acquisition_utc: string;
}
export interface ObservationManifest {
  schema_version: '2.0';
  mode: 'imagery-comparison';
  event: { name: string; date: string };
  aoi: { name: string; center: [number, number]; radius_m: number; bounds: [number, number, number, number] };
  observations: Observation[];
  aoi_url: string;
  analysis_url?: string;
  display: {
    crs: 'EPSG:3857'; width: number; height: number;
    stretch: { min: number; max: number; unit: string };
    status: 'uncalibrated-preview' | 'terrain-corrected-preview' | 'calibrated-analysis-preview';
  };
  limitations: string[];
  credit: string;
}
export interface WaterAnalysis {
  schema_version: '1.0';
  status: 'exploratory-unvalidated';
  dates: string[];
  overlay_url: string;
  display_bounds: number[];
  no_data_area_km2: number;
  areas: { common_valid_km2: number; before_water_km2: number; after_water_km2: number; persistent_water_km2: number; new_water_km2: number; lost_water_km2: number; net_water_change_km2: number };
  method: { threshold_db: number; threshold_method: string; smoothing: string };
  otsu_reference?: { threshold_db: number; areas: { new_water_km2: number; lost_water_km2: number } };
  sensitivity: { new_water_min_km2: number; new_water_max_km2: number; excluding_10m_existing_water_edge_km2: number };
  downloads: { preview: string; before: string; after: string; classes: string; report: string };
}
export interface ComparisonData {
  manifest: ObservationManifest;
  analysis?: WaterAnalysis;
  boundary: FeatureCollection<Polygon | MultiPolygon>;
}
export function analysisForPair(data: ComparisonData, leftId: string, rightId: string): WaterAnalysis | undefined {
  return data.analysis?.dates[0] === leftId && data.analysis.dates[1] === rightId ? data.analysis : undefined;
}
const DAY = 86_400_000;
export const daysFromEvent = (date: string, event: string) => Math.round((Date.parse(date + 'T00:00:00Z') - Date.parse(event + 'T00:00:00Z')) / DAY);
export const formatDate = (date: string, year = true) => new Date(date + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(year ? { year: 'numeric' as const } : {}), timeZone: 'UTC' });
export const assetUrl = (url: string) => new URL(url, document.baseURI).href;
function record(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function date(value: unknown): value is string { return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value + 'T00:00:00Z')); }
function nonempty(value: unknown): value is string { return typeof value === 'string' && value.trim().length > 0; }
function numbers(value: unknown, length: number): value is number[] { return Array.isArray(value) && value.length === length && value.every((item) => typeof item === 'number' && Number.isFinite(item)); }

function parseManifest(value: unknown): ObservationManifest {
  if (!record(value) || value.schema_version !== '2.0' || value.mode !== 'imagery-comparison') throw new Error('The export must be a real imagery-comparison manifest (version 2.0).');
  const { event, aoi, display, observations } = value;
  if (!record(event) || !date(event.date) || !nonempty(event.name)) throw new Error('The event date or name is missing.');
  if (!record(aoi) || !nonempty(aoi.name) || !numbers(aoi.center, 2) || !numbers(aoi.bounds, 4) || typeof aoi.radius_m !== 'number' || !Number.isFinite(aoi.radius_m) || aoi.radius_m <= 0) throw new Error('The study area metadata is invalid.');
  const [west, south, east, north] = aoi.bounds;
  if (!(west < east && south < north && west >= -180 && east <= 180 && south > -85.05 && north < 85.05 && aoi.center[0] >= west && aoi.center[0] <= east && aoi.center[1] >= south && aoi.center[1] <= north)) throw new Error('The study area bounds or village center are invalid.');
  if (!record(display) || display.crs !== 'EPSG:3857' || !['uncalibrated-preview', 'terrain-corrected-preview', 'calibrated-analysis-preview'].includes(String(display.status)) || !Number.isInteger(display.width) || !Number.isInteger(display.height) || Number(display.width) <= 0 || Number(display.height) <= 0 || !record(display.stretch) || typeof display.stretch.min !== 'number' || typeof display.stretch.max !== 'number' || !(display.stretch.min < display.stretch.max) || !nonempty(display.stretch.unit)) throw new Error('The common image grid or brightness scale is invalid.');
  if (!Array.isArray(observations) || observations.length < 2 || !observations.every((item) => record(item) && date(item.date) && ['baseline', 'post-event'].includes(String(item.role)) && ['id', 'label', 'image_url', 'source_product', 'beam_mode', 'polarization', 'orbit_direction', 'acquisition_utc'].every((key) => nonempty(item[key])))) throw new Error('At least two complete radar observations are required.');
  if (new Set(observations.map((o) => o.id)).size !== observations.length || new Set(observations.map((o) => o.date)).size !== observations.length) throw new Error('Observation dates and identifiers must be unique.');
  const baseline = observations.find((item) => item.role === 'baseline');
  const post = observations.find((item) => item.role === 'post-event');
  if (!baseline || !post || baseline.id === post.id || baseline.date >= event.date || post.date <= event.date) throw new Error('The comparison needs one observation before the event and one after it.');
  if (!nonempty(value.aoi_url) || !nonempty(value.credit) || !Array.isArray(value.limitations) || !value.limitations.every((item) => typeof item === 'string')) throw new Error('Boundary information or source notes are missing.');
  if (display.status === 'calibrated-analysis-preview' && !nonempty(value.analysis_url)) throw new Error('Calibrated analysis metadata is missing.');
  return value as unknown as ObservationManifest;
}
async function json(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(assetUrl(url), { signal });
  if (!response.ok) throw new Error(url + ': HTTP ' + response.status);
  return response.json();
}
function verifyImage(observation: Observation, manifest: ObservationManifest, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const cleanup = () => { image.onload = null; image.onerror = null; signal.removeEventListener('abort', abort); };
    const abort = () => { cleanup(); image.src = ''; reject(new DOMException('Aborted', 'AbortError')); };
    if (signal.aborted) { abort(); return; }
    signal.addEventListener('abort', abort, { once: true });
    image.onload = () => {
      cleanup();
      if (image.naturalWidth !== manifest.display.width || image.naturalHeight !== manifest.display.height) reject(new Error('The ' + observation.date + ' image does not match the common display grid.'));
      else resolve();
    };
    image.onerror = () => { cleanup(); reject(new Error('The radar image for ' + observation.date + ' could not be loaded (' + observation.image_url + ').')); };
    image.src = assetUrl(observation.image_url);
  });
}
function parseAnalysis(value: unknown, manifest: ObservationManifest): WaterAnalysis {
  const invalid = () => { throw new Error('The water analysis is missing, inconsistent, or does not match these observations.'); };
  if (!record(value) || value.schema_version !== '1.0' || value.status !== 'exploratory-unvalidated') return invalid();
  if (!Array.isArray(value.dates) || value.dates.length !== 2 || value.dates[0] === value.dates[1] || !value.dates.every((id) => manifest.observations.some((o) => o.id === id)) || !numbers(value.display_bounds, 4) || JSON.stringify(value.display_bounds) !== JSON.stringify(manifest.aoi.bounds) || !nonempty(value.overlay_url)) return invalid();
  const pair = value.dates.map((id) => manifest.observations.find((o) => o.id === id)!);
  if (pair[0].date >= pair[1].date) return invalid();
  const a = value.areas;
  const areaKeys = ['common_valid_km2', 'before_water_km2', 'after_water_km2', 'persistent_water_km2', 'new_water_km2', 'lost_water_km2', 'net_water_change_km2'];
  if (!record(a) || !areaKeys.every((key) => typeof a[key] === 'number' && Number.isFinite(a[key]) && (key === 'net_water_change_km2' || Number(a[key]) >= 0))) return invalid();
  if (Math.abs(Number(a.before_water_km2) + Number(a.new_water_km2) - Number(a.lost_water_km2) - Number(a.after_water_km2)) > 0.00001 || Math.abs(Number(a.new_water_km2) - Number(a.lost_water_km2) - Number(a.net_water_change_km2)) > 0.00001 || Math.abs(Number(a.before_water_km2) - Number(a.persistent_water_km2) - Number(a.lost_water_km2)) > 0.00001 || Number(a.common_valid_km2) <= 0 || Number(a.common_valid_km2) < Number(a.persistent_water_km2) + Number(a.new_water_km2) + Number(a.lost_water_km2)) return invalid();
  if (!record(value.method) || typeof value.method.threshold_db !== 'number' || !Number.isFinite(value.method.threshold_db) || !nonempty(value.method.smoothing) || !nonempty(value.method.threshold_method)) return invalid();
  if (value.otsu_reference !== undefined) {
    const reference = value.otsu_reference;
    if (!record(reference) || typeof reference.threshold_db !== 'number' || !Number.isFinite(reference.threshold_db) || !record(reference.areas)) return invalid();
    const referenceAreas = reference.areas;
    if (!['new_water_km2', 'lost_water_km2'].every((key) => typeof referenceAreas[key] === 'number' && Number.isFinite(referenceAreas[key]) && Number(referenceAreas[key]) >= 0 && Number(referenceAreas[key]) <= Number(a.common_valid_km2))) return invalid();
  }
  const sensitivity = value.sensitivity;
  const downloads = value.downloads;
  if (!record(sensitivity) || !['new_water_min_km2','new_water_max_km2','excluding_10m_existing_water_edge_km2'].every((k) => typeof sensitivity[k] === 'number' && Number.isFinite(sensitivity[k]) && Number(sensitivity[k]) >= 0)) return invalid();
  if (Number(sensitivity.new_water_min_km2) > Number(a.new_water_km2) || Number(sensitivity.new_water_max_km2) < Number(a.new_water_km2)) return invalid();
  if (!record(downloads) || !['preview','before','after','classes','report'].every((k) => nonempty(downloads[k]))) return invalid();
  if (typeof value.no_data_area_km2 !== 'number' || !Number.isFinite(value.no_data_area_km2) || value.no_data_area_km2 < 0) return invalid();
  return value as unknown as WaterAnalysis;
}
export async function loadComparison(signal: AbortSignal): Promise<ComparisonData> {
  const manifest = parseManifest(await json('./observations/manifest.json', signal));
  const [boundaryValue] = await Promise.all([
    json(manifest.aoi_url, signal),
    ...manifest.observations.map((observation) => verifyImage(observation, manifest, signal)),
  ]);
  const boundary = record(boundaryValue) && boundaryValue.type === 'Feature'
    ? { type: 'FeatureCollection', features: [boundaryValue] }
    : boundaryValue;
  if (!record(boundary) || boundary.type !== 'FeatureCollection' || !Array.isArray(boundary.features) || boundary.features.length === 0 || !boundary.features.every((feature) => record(feature) && feature.type === 'Feature' && record(feature.geometry) && ['Polygon', 'MultiPolygon'].includes(String(feature.geometry.type)) && Array.isArray(feature.geometry.coordinates))) throw new Error('The study boundary must contain GeoJSON polygons.');
  const analysis = manifest.analysis_url ? parseAnalysis(await json(manifest.analysis_url, signal), manifest) : undefined;
  if (analysis) await verifyImage({ ...manifest.observations[1], date: 'water change', image_url: analysis.overlay_url }, manifest, signal);
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  return { manifest, analysis, boundary: boundary as unknown as ComparisonData['boundary'] };
}
