import { useEffect, useRef, useState } from 'react';
import { ChatAssistant } from './components/ChatAssistant';
import { ObservationMap, type Basemap, type ViewMode } from './components/ObservationMap';
import { analysisForPair, assetUrl, loadComparison, formatDate, daysFromEvent, type ComparisonData, type Observation } from './lib/observations';

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
      <p>Preparing the available dates and the study boundary.</p>
    </main>
  );
  return <Comparison data={data} />;
}

function Comparison({ data }: { data: ComparisonData }) {
  const { manifest } = data;
  const observations = [...manifest.observations].sort((a, b) => a.date.localeCompare(b.date));
  const [pair, setPair] = useState<[string, string]>([observations[0].id, observations[1].id]);
  const baseline = observations.find((item) => item.id === pair[0])!;
  const post = observations.find((item) => item.id === pair[1])!;
  const analysis = analysisForPair(data, ...pair);
  const calibrated = manifest.display.status === 'calibrated-analysis-preview';
  const terrainCorrected = manifest.display.status === 'terrain-corrected-preview';
  const [mode, setMode] = useState<ViewMode>('compare');
  const [basemap, setBasemap] = useState<Basemap>('plain');
  const [opacity, setOpacity] = useState(1);
  const [outline, setOutline] = useState(true);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const assistantTrigger = useRef<HTMLButtonElement>(null);
  const closeAssistant = () => {
    setAssistantOpen(false);
    assistantTrigger.current?.focus({ preventScroll: true });
  };
  const selectPair = (left: string, right: string) => {
    if (left === right) return;
    setPair([left, right]);
    setMode('compare');
  };
  return (
    <div className="observation-app">
      <header className="top">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">≈</div>
          <div>
            <span className="eyebrow">FloodWatch / Nigeria</span>
            <h1 className="sr-only">{manifest.aoi.name}</h1>
            <div className="location-picker">
              <select className="location-select" aria-label="Location" defaultValue={manifest.aoi.name}>
                <option value={manifest.aoi.name}>{manifest.aoi.name}</option>
                {['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt', 'Maiduguri'].map((city) => (
                  <option key={city} value={city} disabled>{city} — No data yet</option>
                ))}
              </select>
              <span className="location-chevron" aria-hidden="true" />
            </div>
            <p>Explore the landscape before and after the September 2024 flood.</p>
          </div>
        </div>
        <span className="data-badge"><span aria-hidden="true" />Real RADARSAT-2 observations</span>
      </header>
      <div className="preview-notice" role="note">
        <strong>{analysis ? 'Possible water changes' : 'Radar previews'}</strong>
        <span>{analysis ? 'Colours highlight areas to check, not confirmed water. Orange does not mean confirmed water loss.' : calibrated ? 'All dates use calibrated radar and the same brightness scale. Water-change analysis has not been prepared for this pair.' : terrainCorrected ? 'Terrain correction applied. Calibration pending; no flood-area estimates.' : 'Calibration and terrain correction pending. Boundaries approximate; no flood-area estimates.'}</span>
      </div>
      <main className="workspace">
        <aside className="observation-sidebar" aria-label="Observations and map settings">
          <section className="study-summary">
            <span className="eyebrow">Study area</span>
            <h2>A closer look at Kalari Abdu</h2>
            <p>A {manifest.aoi.radius_m / 1000} km radius around the village, with {observations.length} observation dates.</p>
            <div className="study-facts">
              <div><strong>{manifest.aoi.radius_m / 1000} km</strong><span>Study radius</span></div>
              <div><strong>{observations.length}</strong><span>Observations</span></div>
            </div>
          </section>
          {analysis && <section className="water-summary" aria-labelledby="water-heading">
            <span className="eyebrow">{formatDate(baseline.date, false)} → {formatDate(post.date, false)} · unverified</span>
            <p className="analysis-revision" data-testid="analysis-revision"><strong>Shared cutoff · {analysis.method.threshold_db.toFixed(1)} dB</strong><br />Both dates use the same radar brightness threshold. Water remains unverified.</p>
            <h2 id="water-heading">Possible new water</h2>
            <strong className="water-area" data-testid="new-water-area">{analysis.areas.new_water_km2.toFixed(2)} <small>km²</small></strong>
            <p>This is the light-blue area, not confirmed flooding. Changing the detection settings gives {analysis.sensitivity.new_water_min_km2.toFixed(2)}–{analysis.sensitivity.new_water_max_km2.toFixed(2)} km². Actual flooding may lie outside this range.</p>
            <button className="button primary" onClick={() => setMode('change')}>Show changes on the map</button>
            <dl className="water-stats">
              <div><dt>Possible water · {formatDate(baseline.date, false)}</dt><dd>{analysis.areas.before_water_km2.toFixed(2)} km²</dd></div>
              <div><dt>Possible water · {formatDate(post.date, false)}</dt><dd>{analysis.areas.after_water_km2.toFixed(2)} km²</dd></div>
              <div><dt>Orange areas to check</dt><dd>{analysis.areas.lost_water_km2.toFixed(2)} km²</dd></div>
              <div><dt>Difference between dates</dt><dd>{analysis.areas.net_water_change_km2 > 0 ? '+' : ''}{analysis.areas.net_water_change_km2.toFixed(2)} km²</dd></div>
              <div><dt>Area compared</dt><dd>{analysis.areas.common_valid_km2.toFixed(2)} km²</dd></div>
            </dl>
            <p>Orange areas became brighter. This may reflect receding water or changes in fields, soil or vegetation. The area difference is not a confirmed change in water coverage.</p>
            <details><summary>Method and downloads</summary>
              <p>Product calibration → terrain correction → shared 10 m grid → 30 m smoothing → {analysis.method.threshold_method} ({analysis.method.threshold_db.toFixed(2)} dB). Low-return components smaller than 9 pixels are removed.</p>
              {analysis.otsu_reference && analysis.method.threshold_db !== analysis.otsu_reference.threshold_db && <p data-testid="threshold-comparison">Previous Otsu rule ({analysis.otsu_reference.threshold_db.toFixed(2)} dB) → current rule: light-blue area {analysis.otsu_reference.areas.new_water_km2.toFixed(2)} → {analysis.areas.new_water_km2.toFixed(2)} km²; orange area {analysis.otsu_reference.areas.lost_water_km2.toFixed(2)} → {analysis.areas.lost_water_km2.toFixed(2)} km². Both calculations use the same radar data and study area.</p>}
              <p>Each date’s threshold is varied independently by ±1 dB. Removing candidates within 10 m of the baseline low-return class leaves {analysis.sensitivity.excluding_10m_existing_water_edge_km2.toFixed(2)} km². Missing coverage: {analysis.no_data_area_km2.toFixed(2)} km².</p>
              <p>Smooth soil and shadows may resemble water. Vegetated and built-up flooding may be missed. No same-date ground-truth validation.</p>
              <div className="analysis-downloads">
                <a href={assetUrl(analysis.downloads.preview)} target="_blank" rel="noreferrer">Comparison PNG ↗</a>
                <a href={assetUrl(analysis.downloads.report)} download>Analysis report (JSON)</a>
                <a href={assetUrl(analysis.downloads.before)} download>{formatDate(baseline.date, false)} analysis GeoTIFF</a>
                <a href={assetUrl(analysis.downloads.after)} download>{formatDate(post.date, false)} analysis GeoTIFF</a>
                <a href={assetUrl(analysis.downloads.classes)} download>Change classes GeoTIFF</a>
              </div>
            </details>
          </section>}
          {!analysis && <section className="analysis-unavailable" aria-label="Analysis availability">
            <h2>Image comparison only</h2>
            <p>Colour changes and area estimates have not been prepared for these two dates.</p>
            {data.analysis && <button className="button" onClick={() => selectPair(data.analysis!.dates[0], data.analysis!.dates[1])}>View analysed pair</button>}
          </section>}
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
        <section className="map-section" aria-label="Date comparison">
          <section className="date-picker" aria-label="Choose comparison dates">
            <div className="date-picker-row">
            <div className="date-selectors">
              <div className="date-choice"><label htmlFor="left-date">Left image</label>
                <select id="left-date" value={pair[0]} onChange={(event) => selectPair(event.target.value, pair[1])}>
                  {observations.map((o) => <option key={o.id} value={o.id} disabled={o.id === pair[1]}>{formatDate(o.date)}</option>)}
                </select>
              </div>
              <button className="swap-dates" aria-label="Swap sides" title="Swap sides" onClick={() => selectPair(pair[1], pair[0])}>⇄<span>Swap sides</span></button>
              <div className="date-choice"><label htmlFor="right-date">Right image</label>
                <select id="right-date" value={pair[1]} onChange={(event) => selectPair(pair[0], event.target.value)}>
                  {observations.map((o) => <option key={o.id} value={o.id} disabled={o.id === pair[0]}>{formatDate(o.date)}</option>)}
                </select>
              </div>
            </div>
              <div className="assistant-entry">
                <button ref={assistantTrigger} className="assistant-trigger" type="button" aria-expanded={assistantOpen} aria-controls="assistant-panel" aria-haspopup="dialog" onClick={() => setAssistantOpen((open) => !open)}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Z" /><path d="M8 9h8M8 13h5" /></svg>
                  Ask AI
                </button>
              </div>
            </div>
            <div className="quick-pairs" role="group" aria-label="Quick comparisons">
              <span>Quick compare</span>
              {observations.slice(0, -1).map((left, i) => {
                const right = observations[i + 1];
                return <button key={left.id} aria-pressed={pair[0] === left.id && pair[1] === right.id} onClick={() => selectPair(left.id, right.id)}>{formatDate(left.date, false)} → {formatDate(right.date, false)}</button>;
              })}
            </div>
          </section>
          <div className="map-toolbar">
            <div className="mode-tabs" role="group" aria-label="Observation view">
              <button aria-pressed={mode === 'before'} onClick={() => setMode('before')}>Left only</button>
              <button aria-pressed={mode === 'compare'} onClick={() => setMode('compare')}>Compare</button>
              <button aria-pressed={mode === 'after'} onClick={() => setMode('after')}>Right only</button>
              <button aria-pressed={mode === 'change'} disabled={!analysis} title={analysis ? 'Show changes for this pair' : 'Analysis has not been prepared for this pair'} onClick={() => setMode('change')}>Changes</button>
            </div>
            <p>{mode === 'compare' ? 'Drag the divider to compare the same place.' : mode === 'change' ? 'Light blue: possible new water. Orange: other changes to check.' : 'Drag to pan. Scroll or use + / − to zoom.'}</p>
          </div>
          <ObservationMap data={data} baseline={baseline} post={post} mode={mode} basemap={basemap} opacity={opacity} outline={outline} />
          <ObservationTimeline observations={observations} baseline={baseline} post={post} event={manifest.event} />
        </section>
      </main>
      <details className="source-details">
        <summary>Data sources and processing notes</summary>
        <p>{calibrated ? 'The grayscale images display calibrated sigma0. Candidate changes are calculated from the analysis GeoTIFFs, not PNG pixels. The classification has not been independently validated.' : 'These are previews of the original complex SAR observations. They support visual exploration, not a validated flood classification.'}</p>
        <dl>
          {[baseline, post].map((item) => <div key={item.id}><dt>{formatDate(item.date)} · {item.acquisition_utc}</dt><dd>{item.source_product}</dd></div>)}
        </dl>
        {manifest.limitations.length > 0 && <ul>{manifest.limitations.map((note) => <li key={note}>{note}</li>)}</ul>}
        <p>Village center: {manifest.aoi.center[1].toFixed(6)}° N, {manifest.aoi.center[0].toFixed(6)}° E. Display: {manifest.display.width} × {manifest.display.height} pixels on one common map grid.</p>
      </details>
      <ChatAssistant key={pair.join(':')} open={assistantOpen} onClose={closeAssistant} leftId={baseline.id} rightId={post.id} leftDate={baseline.date} rightDate={post.date} mode={mode} hasAnalysis={Boolean(analysis)} />
      <footer className="credit"><span>{manifest.credit}</span><span>{analysis ? 'Possible water changes · unverified' : 'Visual comparison'} · 2024</span></footer>
    </div>
  );
}

function ObservationCard({ observation, eventDate, side }: { observation: Observation; eventDate: string; side: 'before' | 'after' }) {
  const offset = daysFromEvent(observation.date, eventDate);
  return <article className={'observation-card ' + side}>
    <span className="observation-role">{side === 'before' ? 'Left image' : 'Right image'}</span>
    <h3>{formatDate(observation.date)}</h3>
    <p>{Math.abs(offset)} days {offset < 0 ? 'before' : 'after'} the reference date</p>
    <div className="acquisition-tags"><span>{observation.beam_mode}</span><span>{observation.polarization}</span><span>{observation.orbit_direction}</span></div>
  </article>;
}

function ObservationTimeline({ observations, baseline, post, event }: {
  observations: Observation[]; baseline: Observation; post: Observation; event: { name: string; date: string };
}) {
  return <section className="observation-timeline" aria-label="Observation timeline">
    <div className="timeline-heading"><h2>Available observations</h2><span>Flood reference: {formatDate(event.date)}</span></div>
    <ol className="observation-dates">
      {observations.map((observation) => {
        const side = observation.id === baseline.id ? 'Left' : observation.id === post.id ? 'Right' : '';
        return <li key={observation.id} className={side.toLowerCase()}>
          <span className="timeline-dot" aria-hidden="true" /><strong>{formatDate(observation.date, false)}</strong><small>{side || 'Available'}</small>
        </li>;
      })}
    </ol>
    <p className="timeline-caption">Each date is a separate observation. Changes between observations are not measured.</p>
  </section>;
}
