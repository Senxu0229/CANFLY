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
  display: {
    crs: 'EPSG:3857'; width: number; height: number;
    stretch: { min: number; max: number; unit: string };
    status: 'uncalibrated-preview' | 'terrain-corrected-preview';
  };
  limitations: string[];
  credit: string;
}
export interface ComparisonData {
  manifest: ObservationManifest;
  boundary: FeatureCollection<Polygon | MultiPolygon>;
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
  if (!record(display) || display.crs !== 'EPSG:3857' || !['uncalibrated-preview', 'terrain-corrected-preview'].includes(String(display.status)) || !Number.isInteger(display.width) || !Number.isInteger(display.height) || Number(display.width) <= 0 || Number(display.height) <= 0 || !record(display.stretch) || typeof display.stretch.min !== 'number' || typeof display.stretch.max !== 'number' || !(display.stretch.min < display.stretch.max) || !nonempty(display.stretch.unit)) throw new Error('The common image grid or brightness scale is invalid.');
  if (!Array.isArray(observations) || observations.length !== 2 || !observations.every((item) => record(item) && date(item.date) && ['baseline', 'post-event'].includes(String(item.role)) && ['id', 'label', 'image_url', 'source_product', 'beam_mode', 'polarization', 'orbit_direction', 'acquisition_utc'].every((key) => nonempty(item[key])))) throw new Error('Two complete radar observations are required.');
  const baseline = observations.find((item) => item.role === 'baseline');
  const post = observations.find((item) => item.role === 'post-event');
  if (!baseline || !post || baseline.id === post.id || baseline.date >= event.date || post.date <= event.date) throw new Error('The comparison needs one observation before the event and one after it.');
  if (!nonempty(value.aoi_url) || !nonempty(value.credit) || !Array.isArray(value.limitations) || !value.limitations.every((item) => typeof item === 'string')) throw new Error('Boundary information or source notes are missing.');
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
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  return { manifest, boundary: boundary as unknown as ComparisonData['boundary'] };
}
