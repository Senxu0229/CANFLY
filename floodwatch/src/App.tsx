import { useEffect, useState } from 'react';
import { ObservationMap, type Basemap, type ViewMode } from './components/ObservationMap';
import { loadComparison, formatDate, daysFromEvent, type ComparisonData, type Observation } from './lib/observations';

export default function App() {
  const [data, setData] = useState<ComparisonData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setData(null);
    loadComparison(controller.signal).then(setData).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unknown data error');
    });
    return () => controller.abort();
  }, [attempt]);
  if (error) return (
    <main className="status" role="alert">
      <span className="eyebrow">FloodWatch · Kalari Abdu</span>
      <h1>Observation data could not be loaded</h1>
      <p>{error}</p>
      <p>Check that the real observation export is available in <code>public/observations/</code>.</p>
      <button className="button primary" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
    </main>
  );
  if (!data) return (
    <main className="status" role="status">
      <span className="eyebrow">FloodWatch · Kalari Abdu</span>
      <h1>Loading radar observations…</h1>
      <p>Preparing the two images and the study boundary.</p>
    </main>
  );
  return <Comparison data={data} />;
}

function Comparison({ data }: { data: ComparisonData }) {
  const { manifest } = data;
  const terrainCorrected = manifest.display.status === 'terrain-corrected-preview';
  const [mode, setMode] = useState<ViewMode>('compare');
  const [basemap, setBasemap] = useState<Basemap>('plain');
  const [opacity, setOpacity] = useState(1);
  const [outline, setOutline] = useState(true);
  const baseline = manifest.observations.find((item) => item.role === 'baseline')!;
  const post = manifest.observations.find((item) => item.role === 'post-event')!;
  return (
    <div className="observation-app">
      <header className="top">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">≈</div>
          <div>
            <span className="eyebrow">FloodWatch / Nigeria</span>
            <h1>{manifest.aoi.name}</h1>
            <p>Explore the landscape before and after the September 2024 flood.</p>
          </div>
        </div>
        <span className="data-badge"><span aria-hidden="true" />Real RADARSAT-2 observations</span>
      </header>
      <div className="preview-notice" role="note">
        <strong>Radar previews</strong>
        <span>{terrainCorrected ? 'Terrain correction applied. Calibration pending; no flood-area estimates.' : 'Calibration and terrain correction pending. Boundaries approximate; no flood-area estimates.'}</span>
      </div>
      <main className="workspace">
        <aside className="observation-sidebar" aria-label="Observations and map settings">
          <section className="study-summary">
            <span className="eyebrow">Study area</span>
            <h2>A closer look at Kalari Abdu</h2>
            <p>A {manifest.aoi.radius_m / 1000} km radius around the village, observed on two dates.</p>
            <div className="study-facts">
              <div><strong>{manifest.aoi.radius_m / 1000} km</strong><span>Study radius</span></div>
              <div><strong>2</strong><span>Observations</span></div>
            </div>
          </section>
          <section className="observation-list" aria-label="Acquisition dates">
            <ObservationCard observation={baseline} eventDate={manifest.event.date} side="before" />
            <ObservationCard observation={post} eventDate={manifest.event.date} side="after" />
          </section>
          <section className="map-settings" aria-labelledby="settings-heading">
            <h2 id="settings-heading">Map display</h2>
            <label className="select-setting" htmlFor="basemap">Background map</label>
            <select id="basemap" value={basemap} onChange={(event) => setBasemap(event.target.value as Basemap)}>
              <option value="plain">Plain · no external tiles</option>
              <option value="streets">Street map</option>
              <option value="imagery">Satellite basemap</option>
            </select>
            {basemap !== 'plain' && <p className="setting-note">Online background for location context; its imagery is not dated to either radar observation.</p>}
            <label className="range-setting" htmlFor="radar-opacity">
              <span>Radar opacity <output>{Math.round(opacity * 100)}%</output></span>
              <input id="radar-opacity" type="range" min="0" max="100" value={Math.round(opacity * 100)} onChange={(event) => setOpacity(Number(event.target.value) / 100)} />
            </label>
            <label className="checkbox-setting">
              <input type="checkbox" checked={outline} onChange={(event) => setOutline(event.target.checked)} />
              Show study boundary
            </label>
          </section>
          <section className="radar-guide" aria-labelledby="guide-heading">
            <h2 id="guide-heading">Reading the radar</h2>
            <div className="radar-ramp" aria-hidden="true" />
            <div className="ramp-labels"><span>Weaker return</span><span>Stronger return</span></div>
            <p>Both dates use the same brightness scale. Dark areas may be open water, but brightness alone does not identify flooding.</p>
            <p>Zooming reveals the preview pixels; it does not add new image detail.</p>
          </section>
        </aside>
        <section className="map-section" aria-label="Before and after comparison">
          <div className="map-toolbar">
            <div className="mode-tabs" role="group" aria-label="Observation view">
              <button aria-pressed={mode === 'before'} onClick={() => setMode('before')}>Before</button>
              <button aria-pressed={mode === 'compare'} onClick={() => setMode('compare')}>Compare</button>
              <button aria-pressed={mode === 'after'} onClick={() => setMode('after')}>After</button>
            </div>
            <p>{mode === 'compare' ? 'Drag the divider to compare the same place.' : 'Drag to pan. Scroll or use + / − to zoom.'}</p>
          </div>
          <ObservationMap data={data} baseline={baseline} post={post} mode={mode} basemap={basemap} opacity={opacity} outline={outline} />
          <ObservationTimeline baseline={baseline} post={post} event={manifest.event} mode={mode} onMode={setMode} />
        </section>
      </main>
      <details className="source-details">
        <summary>Data sources and processing notes</summary>
        <p>These are previews of the original complex SAR observations. They support visual exploration, not a validated flood classification.</p>
        <dl>
          {[baseline, post].map((item) => <div key={item.id}><dt>{formatDate(item.date)} · {item.acquisition_utc}</dt><dd>{item.source_product}</dd></div>)}
        </dl>
        {manifest.limitations.length > 0 && <ul>{manifest.limitations.map((note) => <li key={note}>{note}</li>)}</ul>}
        <p>Village center: {manifest.aoi.center[1].toFixed(6)}° N, {manifest.aoi.center[0].toFixed(6)}° E. Display: {manifest.display.width} × {manifest.display.height} pixels on one common map grid.</p>
      </details>
      <footer className="credit"><span>{manifest.credit}</span><span>Visual comparison · 2024</span></footer>
    </div>
  );
}

function ObservationCard({ observation, eventDate, side }: { observation: Observation; eventDate: string; side: 'before' | 'after' }) {
  const offset = daysFromEvent(observation.date, eventDate);
  return <article className={'observation-card ' + side}>
    <span className="observation-role">{side === 'before' ? 'Before flood · baseline' : 'After flood · observation'}</span>
    <h3>{formatDate(observation.date)}</h3>
    <p>{Math.abs(offset)} days {offset < 0 ? 'before' : 'after'} the reference date</p>
    <div className="acquisition-tags"><span>{observation.beam_mode}</span><span>{observation.polarization}</span><span>{observation.orbit_direction}</span></div>
  </article>;
}

function ObservationTimeline({ baseline, post, event, mode, onMode }: {
  baseline: Observation; post: Observation; event: { name: string; date: string }; mode: ViewMode; onMode: (value: ViewMode) => void;
}) {
  const beforeDays = daysFromEvent(baseline.date, event.date);
  const afterDays = daysFromEvent(post.date, event.date);
  const eventPosition = -beforeDays / (afterDays - beforeDays) * 100;
  return <section className="observation-timeline" aria-label="Observation timeline">
    <div className="timeline-heading"><h2>Two views of the same place</h2><span>Dates relative to {formatDate(event.date)}</span></div>
    <div className="date-line">
      <button className={'timeline-date before ' + (mode !== 'after' ? 'selected' : '')} aria-pressed={mode === 'before'} onClick={() => onMode('before')}>
        <span className="timeline-dot" /><strong>{formatDate(baseline.date, false)}</strong><small>{beforeDays} days</small>
      </button>
      <div className="timeline-event" style={{ left: eventPosition + '%' }}><span className="event-tick" /><strong>{formatDate(event.date, false)}</strong><small>Flood reference</small></div>
      <button className={'timeline-date after ' + (mode !== 'before' ? 'selected' : '')} aria-pressed={mode === 'after'} onClick={() => onMode('after')}>
        <span className="timeline-dot" /><strong>{formatDate(post.date, false)}</strong><small>+{afterDays} days</small>
      </button>
    </div>
    <p className="timeline-caption">Observation dates are snapshots, not measurements of how long flooding lasted.</p>
  </section>;
}
