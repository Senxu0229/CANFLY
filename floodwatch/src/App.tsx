import { useEffect, useRef, useState } from 'react';
import { ChatAssistant } from './components/ChatAssistant';
import { ContextChart, useContextData, type ContextData } from './components/ContextTimeline';
import { DisplaySettings } from './components/DisplaySettings';
import { LocationPicker } from './components/LocationPicker';
import { ObservationMap, type Basemap, type ViewMode } from './components/ObservationMap';
import { analysisForPair, assetUrl, loadComparison, type ComparisonData, type Observation } from './lib/observations';
import { usePrefs } from './lib/prefs';

export default function App() {
  const { t } = usePrefs();
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
      <h1>{t('Observation data could not be loaded')}</h1>
      <p>{error}</p>
      <p>{t('Check that the real observation export is available in')} <code>public/observations/</code>.</p>
      <button className="button primary" onClick={() => setAttempt((value) => value + 1)}>{t('Try again')}</button>
    </main>
  );
  if (!data) return (
    <main className="status" role="status">
      <span className="eyebrow">FloodWatch · Kalari Abdu</span>
      <h1>{t('Loading radar observations…')}</h1>
      <p>{t('Preparing the available dates and the study boundary.')}</p>
    </main>
  );
  return <Comparison data={data} />;
}

function Comparison({ data }: { data: ComparisonData }) {
  const { t, fd, fn } = usePrefs();
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
  const context = useContextData();
  // Collapsible header: a slim one-line bar gives the map more room; the choice is remembered.
  const [compact, setCompact] = useState(() => { try { return window.localStorage.getItem('floodwatch.header-compact') === '1'; } catch { return false; } });
  const toggleCompact = () => setCompact((value) => {
    try { window.localStorage.setItem('floodwatch.header-compact', value ? '0' : '1'); } catch { /* Optional preference. */ }
    return !value;
  });
  const noticeTitle = analysis ? t('Possible water changes') : t('Radar previews');
  const noticeText = analysis ? t('Colours highlight areas to check, not confirmed water. Orange does not mean confirmed water loss.') : calibrated ? t('All dates use calibrated radar and the same brightness scale. Water-change analysis has not been prepared for this pair.') : terrainCorrected ? t('Terrain correction applied. Calibration pending; no flood-area estimates.') : t('Calibration and terrain correction pending. Boundaries approximate; no flood-area estimates.');
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
    <div className={'observation-app' + (compact ? ' header-compact' : '')}>
      <nav className="skip-links" aria-label={t('Skip links')}>
        <a href="#map-region">{t('Skip to map')}</a>
        <a href="#results-region">{t('Skip to results')}</a>
      </nav>
      <header className={'top' + (compact ? ' compact' : '')}>
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">≈</div>
          <div>
            {!compact && <span className="eyebrow">{t('FloodWatch · Radar flood monitor')}</span>}
            <h1 className="sr-only">{manifest.aoi.name}</h1>
            <div className="location-row">
              <LocationPicker name={manifest.aoi.name} country="Nigeria" />
              <span className="location-country">{t('Nigeria')}</span>
              {compact && <span className="compact-notice" title={noticeText}>{noticeTitle}</span>}
            </div>
            {!compact && <p>{t('Explore the landscape before and after the September 2024 flood.')}</p>}
            {!compact && <p className="coverage-note">{t('One radar workflow for any site in the RADARSAT-2 tropical archive.')}</p>}
          </div>
        </div>
        <div className="top-right">
          {!compact && <span className="data-badge"><span aria-hidden="true" />{t('Real RADARSAT-2 observations')}</span>}
          <DisplaySettings />
          <button type="button" className="header-toggle" aria-expanded={!compact} onClick={toggleCompact}
            aria-label={compact ? t('Expand header') : t('Collapse header')} title={compact ? t('Expand header') : t('Collapse header')}>
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d={compact ? 'M6 9l6 6 6-6' : 'M6 15l6-6 6 6'} /></svg>
          </button>
        </div>
      </header>
      {!compact && <div className="preview-notice" role="note">
        <strong>{noticeTitle}</strong>
        <span>{noticeText}</span>
      </div>}
      <main className="workspace">
        <aside className="observation-sidebar" id="results-region" tabIndex={-1} aria-label={t('Observations and map settings')}>
          <section className="study-summary">
            <span className="eyebrow">{t('Study area')}</span>
            <h2>{t('A closer look at Kalari Abdu')}</h2>
            <p>{t('A {r} km radius around the village, with {n} observation dates.', { r: manifest.aoi.radius_m / 1000, n: observations.length })}</p>
            <div className="study-facts">
              <div><strong>{manifest.aoi.radius_m / 1000} km</strong><span>{t('Study radius')}</span></div>
              <div><strong>{observations.length}</strong><span>{t('Observations')}</span></div>
            </div>
          </section>
          {analysis && <section className="water-summary" aria-labelledby="water-heading">
            <span className="eyebrow">{fd(baseline.date, false)} → {fd(post.date, false)} · {t('unverified')}</span>
            <p className="analysis-revision" data-testid="analysis-revision"><strong>{t('Shared cutoff')} · {fn(analysis.method.threshold_db, 1)} dB</strong><br />{t('Both dates use the same radar brightness threshold. Water remains unverified.')}</p>
            <h2 id="water-heading">{t('Possible new water')}</h2>
            <strong className="water-area" data-testid="new-water-area">{fn(analysis.areas.new_water_km2, 2)} <small>km²</small></strong>
            <p>{t('This is the light-blue area, not confirmed flooding. Changing the detection settings gives {min}–{max} km². Actual flooding may lie outside this range.', { min: fn(analysis.sensitivity.new_water_min_km2, 2), max: fn(analysis.sensitivity.new_water_max_km2, 2) })}</p>
            <button className="button primary" onClick={() => setMode('change')}>{t('Show changes on the map')}</button>
            <dl className="water-stats">
              <div><dt>{t('Possible water')} · {fd(baseline.date, false)}</dt><dd>{fn(analysis.areas.before_water_km2, 2)} km²</dd></div>
              <div><dt>{t('Possible water')} · {fd(post.date, false)}</dt><dd>{fn(analysis.areas.after_water_km2, 2)} km²</dd></div>
              <div><dt>{t('Orange areas to check')}</dt><dd>{fn(analysis.areas.lost_water_km2, 2)} km²</dd></div>
              <div><dt>{t('Difference between dates')}</dt><dd>{analysis.areas.net_water_change_km2 > 0 ? '+' : ''}{fn(analysis.areas.net_water_change_km2, 2)} km²</dd></div>
              <div><dt>{t('Area compared')}</dt><dd>{fn(analysis.areas.common_valid_km2, 2)} km²</dd></div>
            </dl>
            <p>{t('Orange areas became brighter. This may reflect receding water or changes in fields, soil or vegetation. The area difference is not a confirmed change in water coverage.')}</p>
            <details className="method-details"><summary className="method-summary">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>
              <span>{t('Method and downloads')}</span>
            </summary>
              <div className="method-body">
              <h3 className="method-heading">{t('How this was calculated')}</h3>
              <p>{t('Product calibration → terrain correction → shared 10 m grid → 30 m smoothing → {method} ({db} dB). Low-return components smaller than 9 pixels are removed.', { method: analysis.method.threshold_method, db: fn(analysis.method.threshold_db, 2) })}</p>
              {analysis.otsu_reference && analysis.method.threshold_db !== analysis.otsu_reference.threshold_db && <p data-testid="threshold-comparison">{t('Previous Otsu rule ({otsu} dB) → current rule: light-blue area {newA} → {newB} km²; orange area {lostA} → {lostB} km². Both calculations use the same radar data and study area.', { otsu: fn(analysis.otsu_reference.threshold_db, 2), newA: fn(analysis.otsu_reference.areas.new_water_km2, 2), newB: fn(analysis.areas.new_water_km2, 2), lostA: fn(analysis.otsu_reference.areas.lost_water_km2, 2), lostB: fn(analysis.areas.lost_water_km2, 2) })}</p>}
              <p>{t('Each date’s threshold is varied independently by ±1 dB. Removing candidates within 10 m of the baseline low-return class leaves {edge} km². Missing coverage: {missing} km².', { edge: fn(analysis.sensitivity.excluding_10m_existing_water_edge_km2, 2), missing: fn(analysis.no_data_area_km2, 2) })}</p>
              <p>{t('Smooth soil and shadows may resemble water. Vegetated and built-up flooding may be missed. No same-date ground-truth validation.')}</p>
              <h3 className="method-heading">{t('Downloads')}</h3>
              <ul className="analysis-downloads">
                {[
                  { href: analysis.downloads.preview, label: t('Comparison PNG ↗'), type: 'PNG', open: true },
                  { href: analysis.downloads.report, label: t('Analysis report (JSON)'), type: 'JSON' },
                  { href: analysis.downloads.before, label: t('{date} analysis GeoTIFF', { date: fd(baseline.date, false) }), type: 'TIFF' },
                  { href: analysis.downloads.after, label: t('{date} analysis GeoTIFF', { date: fd(post.date, false) }), type: 'TIFF' },
                  { href: analysis.downloads.classes, label: t('Change classes GeoTIFF'), type: 'TIFF' },
                ].map((file) => <li key={file.href}>
                  <a className="download-row" href={assetUrl(file.href)} {...(file.open ? { target: '_blank', rel: 'noreferrer' } : { download: true })}>
                    <span className="file-badge" aria-hidden="true">{file.type}</span>
                    <span className="download-name">{file.label}</span>
                    <svg className="download-icon" aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{file.open ? <path d="M7 17 17 7M9 7h8v8" /> : <path d="M12 4v11m-5-5 5 5 5-5M5 20h14" />}</svg>
                  </a>
                </li>)}
              </ul>
              </div>
            </details>
          </section>}
          {!analysis && <section className="analysis-unavailable" aria-label={t('Analysis availability')}>
            <h2>{t('Image comparison only')}</h2>
            <p>{t('Colour changes and area estimates have not been prepared for these two dates.')}</p>
            {data.analysis && <button className="button" onClick={() => selectPair(data.analysis!.dates[0], data.analysis!.dates[1])}>{t('View analysed pair')}</button>}
          </section>}
          <section className="map-settings" aria-labelledby="settings-heading">
            <h2 id="settings-heading">{t('Map display')}</h2>
            <label className="select-setting" htmlFor="basemap">{t('Background map')}</label>
            <select id="basemap" value={basemap} onChange={(event) => setBasemap(event.target.value as Basemap)}>
              <option value="plain">{t('Plain · no external tiles')}</option>
              <option value="streets">{t('Street map')}</option>
              <option value="imagery">{t('Satellite basemap')}</option>
            </select>
            {basemap !== 'plain' && <p className="setting-note">{t('Online background for location context; its imagery is not dated to either radar observation.')}</p>}
            <label className="range-setting" htmlFor="radar-opacity">
              <span>{t('Radar opacity')} <output>{Math.round(opacity * 100)}%</output></span>
              <input id="radar-opacity" type="range" min="0" max="100" value={Math.round(opacity * 100)} onChange={(event) => setOpacity(Number(event.target.value) / 100)} />
            </label>
            <label className="checkbox-setting">
              <input type="checkbox" checked={outline} onChange={(event) => setOutline(event.target.checked)} />
              {t('Show study boundary')}
            </label>
          </section>
          <section className="radar-guide" aria-labelledby="guide-heading">
            <h2 id="guide-heading">{t('Reading the radar')}</h2>
            <div className="radar-ramp" aria-hidden="true" />
            <div className="ramp-labels"><span>{t('Weaker return')}</span><span>{t('Stronger return')}</span></div>
            <p>{t('Both dates use the same brightness scale. Dark areas may be open water, but brightness alone does not identify flooding.')}</p>
            <p>{t('Zooming reveals the preview pixels; it does not add new image detail.')}</p>
          </section>
        </aside>
        <section className="map-section" id="map-region" tabIndex={-1} aria-label={t('Date comparison')}>
          <section className="date-picker" aria-label={t('Choose comparison dates')}>
            <div className="date-picker-row">
            <div className="date-selectors">
              <div className="date-choice"><label htmlFor="left-date">{t('Left image')}</label>
                <select id="left-date" value={pair[0]} onChange={(event) => selectPair(event.target.value, pair[1])}>
                  {observations.map((o) => <option key={o.id} value={o.id} disabled={o.id === pair[1]}>{fd(o.date)}</option>)}
                </select>
              </div>
              <button className="swap-dates" aria-label={t('Swap sides')} title={t('Swap sides')} onClick={() => selectPair(pair[1], pair[0])}>⇄<span>{t('Swap sides')}</span></button>
              <div className="date-choice"><label htmlFor="right-date">{t('Right image')}</label>
                <select id="right-date" value={pair[1]} onChange={(event) => selectPair(pair[0], event.target.value)}>
                  {observations.map((o) => <option key={o.id} value={o.id} disabled={o.id === pair[0]}>{fd(o.date)}</option>)}
                </select>
              </div>
            </div>
              <div className="assistant-entry">
                <button ref={assistantTrigger} className="assistant-trigger" type="button" aria-expanded={assistantOpen} aria-controls="assistant-panel" aria-haspopup="dialog" onClick={() => setAssistantOpen((open) => !open)}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Z" /><path d="M8 9h8M8 13h5" /></svg>
                  {t('Ask AI')}
                </button>
              </div>
            </div>
            <div className="quick-pairs" role="group" aria-label={t('Quick comparisons')}>
              <span>{t('Quick compare')}</span>
              {observations.slice(0, -1).map((left, i) => {
                const right = observations[i + 1];
                return <button key={left.id} aria-pressed={pair[0] === left.id && pair[1] === right.id} onClick={() => selectPair(left.id, right.id)}>{fd(left.date, false)} → {fd(right.date, false)}</button>;
              })}
            </div>
          </section>
          <div className="map-toolbar">
            <div className="mode-tabs" role="group" aria-label={t('Observation view')}>
              <button aria-pressed={mode === 'before'} onClick={() => setMode('before')}>{t('Left only')}</button>
              <button aria-pressed={mode === 'compare'} onClick={() => setMode('compare')}>{t('Compare')}</button>
              <button aria-pressed={mode === 'after'} onClick={() => setMode('after')}>{t('Right only')}</button>
              <button aria-pressed={mode === 'change'} disabled={!analysis} title={analysis ? t('Show changes for this pair') : t('Analysis has not been prepared for this pair')} onClick={() => setMode('change')}>{t('Changes')}</button>
            </div>
            <p>{mode === 'compare' ? t('Drag the divider to compare the same place.') : mode === 'change' ? t('Light blue: possible new water. Orange: other changes to check.') : t('Drag to pan. Scroll or use + / − to zoom.')}</p>
          </div>
          <ObservationMap data={data} baseline={baseline} post={post} mode={mode} basemap={basemap} opacity={opacity} outline={outline} />
          <ObservationTimeline observations={observations} baseline={baseline} post={post} event={manifest.event} context={context} />
        </section>
      </main>
      <details className="source-details">
        <summary>{t('Data sources and processing notes')}</summary>
        <p>{calibrated ? t('The grayscale images display calibrated sigma0. Candidate changes are calculated from the analysis GeoTIFFs, not PNG pixels. The classification has not been independently validated.') : t('These are previews of the original complex SAR observations. They support visual exploration, not a validated flood classification.')}</p>
        <dl>
          {[baseline, post].map((item) => <div key={item.id}><dt>{fd(item.date)} · {item.acquisition_utc}</dt><dd>{item.source_product}</dd></div>)}
        </dl>
        {manifest.limitations.length > 0 && <ul>{manifest.limitations.map((note) => <li key={note}>{note}</li>)}</ul>}
        <p>{t('Village center: {lat}° N, {lon}° E. Display: {w} × {h} pixels on one common map grid.', { lat: fn(manifest.aoi.center[1], 6), lon: fn(manifest.aoi.center[0], 6), w: manifest.display.width, h: manifest.display.height })}</p>
      </details>
      <ChatAssistant key={pair.join(':')} open={assistantOpen} onClose={closeAssistant} leftId={baseline.id} rightId={post.id} leftDate={baseline.date} rightDate={post.date} mode={mode} hasAnalysis={Boolean(analysis)} />
      <footer className="credit"><span>{manifest.credit}</span><span>{analysis ? t('Possible water changes · unverified') : t('Visual comparison')} · 2024</span></footer>
    </div>
  );
}

const CONTEXT_KEY = 'floodwatch.context-open';
function ObservationTimeline({ observations, baseline, post, event, context }: {
  observations: Observation[]; baseline: Observation; post: Observation; event: { name: string; date: string }; context: ContextData | null;
}) {
  const { t, fd } = usePrefs();
  // Progressive disclosure: the compact date list stays the default; the context chart
  // replaces it when opened (it shows the same radar dates on a true time axis).
  const [showContext, setShowContext] = useState(() => { try { return window.localStorage.getItem(CONTEXT_KEY) === '1'; } catch { return false; } });
  const toggle = () => setShowContext((value) => {
    try { window.localStorage.setItem(CONTEXT_KEY, value ? '0' : '1'); } catch { /* Preference is optional. */ }
    return !value;
  });
  const open = showContext && context !== null;
  return <section className="observation-timeline" aria-label={t('Observation timeline')}>
    <div className="timeline-heading">
      <h2>{open ? t('Rain, regional flood signal and radar dates') : t('Available observations')}</h2>
      <span>{t('Flood reference: {date}', { date: fd(event.date) })}</span>
      {context && <button type="button" className="context-toggle" aria-expanded={open} aria-controls="context-panel" onClick={toggle}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 19h16M7 16V9m5 7V5m5 11v-4" /></svg>
        {open ? t('Hide rain & flood context') : t('Show rain & flood context')}
      </button>}
    </div>
    {open && context
      ? <ContextChart data={context} observations={observations} leftId={baseline.id} rightId={post.id} event={event} />
      : <ol className="observation-dates">
        {observations.map((observation) => {
          const side = observation.id === baseline.id ? 'Left' : observation.id === post.id ? 'Right' : '';
          return <li key={observation.id} className={side.toLowerCase()}>
            <span className="timeline-dot" aria-hidden="true" /><strong>{fd(observation.date, false)}</strong><small>{side ? t(side) : t('Available')}</small>
          </li>;
        })}
      </ol>}
    {!open && <p className="timeline-caption">{t('Each date is a separate observation. Changes between observations are not measured.')}</p>}
  </section>;
}
