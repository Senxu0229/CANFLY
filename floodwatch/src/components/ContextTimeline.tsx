import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { assetUrl, type Observation } from '../lib/observations';
import { usePrefs } from '../lib/prefs';

// Public context only (rainfall + UNOSAT VIIRS). No RADARSAT-2 values are read here;
// radar dates come from the observation manifest the app already loaded.
export interface ContextData {
  schema_version: '1.0';
  domain: [string, string];
  rain: { source: string; unit: string; coverage: [string, string]; days: [string, number][] };
  viirs: { source: string; radius_km: number; periods: { start: string; end: string; km2: number }[] };
  caveat: string;
}

const DAY = 86_400_000;
const ms = (date: string) => Date.parse(date + 'T00:00:00Z');
const iso = (time: number) => new Date(time).toISOString().slice(0, 10);

function valid(value: unknown): value is ContextData {
  const v = value as ContextData;
  return !!v && v.schema_version === '1.0' && Array.isArray(v.domain) && Array.isArray(v.rain?.days) && Array.isArray(v.viirs?.periods)
    && v.rain.days.every((d) => Array.isArray(d) && typeof d[0] === 'string' && Number.isFinite(d[1]))
    && v.viirs.periods.every((p) => typeof p.start === 'string' && typeof p.end === 'string' && Number.isFinite(p.km2));
}

/** Loads the optional context file. Missing or invalid data simply hides the feature. */
export function useContextData(): ContextData | null {
  const [data, setData] = useState<ContextData | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(assetUrl('./context/kalari_context.json'), { signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((value: unknown) => { if (valid(value)) setData(value); })
      .catch(() => { /* Optional layer: the observation timeline still works without it. */ });
    return () => controller.abort();
  }, []);
  return data;
}

interface Props {
  data: ContextData;
  observations: Observation[];
  leftId: string;
  rightId: string;
  event: { name: string; date: string };
}

export function ContextChart({ data, observations, leftId, rightId, event }: Props) {
  const { t, fd, fn } = usePrefs();
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    if (!wrap.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(wrap.current);
    return () => observer.disconnect();
  }, []);

  const t0 = ms(data.domain[0]);
  const t1 = ms(data.domain[1]) + DAY;
  const left = 46, right = 14;
  const inner = width - left - right;
  const x = (time: number) => left + (time - t0) / (t1 - t0) * inner;
  const dayW = inner / ((t1 - t0) / DAY);

  // Vertical layout (px).
  const top = 22, rainH = 56, gap = 12, viirsH = 40, trackY = top + rainH + gap + viirsH + 18, axisY = trackY + 20, height = axisY + 18;
  const rainBase = top + rainH, viirsTop = rainBase + gap, viirsBase = viirsTop + viirsH;

  const rainMax = Math.max(10, ...data.rain.days.map((d) => d[1]));
  const rainTick = Math.ceil(rainMax / 10) * 10;
  const peak = data.viirs.periods.reduce((best, p) => p.km2 > best.km2 ? p : best, data.viirs.periods[0]);
  const viirsTick = Math.max(1, Math.ceil(peak.km2));
  const coverageEnd = ms(data.rain.coverage[1]) + DAY;
  const months = useMemo(() => {
    const list: number[] = [];
    const d = new Date(t0);
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.getTime() < t1) { list.push(d.getTime()); d.setUTCMonth(d.getUTCMonth() + 1); }
    return list;
  }, [t0, t1]);

  // Plain-language takeaway, derived from the data rather than written by hand.
  const during = observations.find((o) => data.viirs.periods.some((p) => p.km2 >= peak.km2 * 0.5 && ms(o.date) >= ms(p.start) - 3 * DAY && ms(o.date) <= ms(p.end) + 3 * DAY));
  const periodLabel = (p: { start: string; end: string }) => fd(p.start, false) + ' – ' + fd(p.end, false);
  const takeaway = t('The regional flood signal peaked {period} ({area} km² within {r} km of the village).', { period: periodLabel(peak), area: fn(peak.km2, 1), r: data.viirs.radius_km })
    + (during ? ' ' + t('The {date} radar image was taken during this high-water period.', { date: fd(during.date, false) }) : '');

  const monthLabel = (time: number) => new Date(time).toLocaleDateString(document.documentElement.lang === 'fr' ? 'fr-CA' : 'en-GB', { month: 'short', timeZone: 'UTC' });

  const onMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - box.left) * (width / box.width);
    if (px < left || px > width - right) { setHover(null); return; }
    setHover(Math.floor((t0 + (px - left) / inner * (t1 - t0)) / DAY) * DAY);
  };
  const hoverInfo = hover === null ? null : (() => {
    const date = iso(hover);
    const rain = data.rain.days.find((d) => d[0] === date);
    const period = data.viirs.periods.find((p) => date >= p.start && date <= p.end);
    const obs = observations.find((o) => o.date === date);
    return { date, rain, period, obs };
  })();

  const descId = 'context-desc';
  return <figure className="context-figure" id="context-panel">
    <p className="context-takeaway">{takeaway}</p>
    <ul className="context-legend" aria-label={t('Chart legend')}>
      <li><i className="key rain" aria-hidden="true" />{t('Daily rainfall (mm)')}</li>
      <li><i className="key viirs" aria-hidden="true" />{t('VIIRS mapped flood area (km², 5-day, {r} km radius)', { r: data.viirs.radius_km })}</li>
      <li><i className="key radar" aria-hidden="true" />{t('RADARSAT-2 image')}</li>
      <li><i className="key event" aria-hidden="true" />{t('Dam failure')}</li>
    </ul>
    <div className="context-chart" ref={wrap}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('Rainfall, regional flood signal and radar dates')} aria-describedby={descId}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <desc id={descId}>{takeaway + ' ' + t('Rainfall data cover {a} to {b}.', { a: fd(data.rain.coverage[0]), b: fd(data.rain.coverage[1]) }) + ' ' + t('Use the data table button for all values.')}</desc>
        <defs>
          <pattern id="nodata-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="hatch" />
          </pattern>
        </defs>
        {months.map((m) => <g key={m}>
          <line className="grid" x1={x(m)} x2={x(m)} y1={top} y2={trackY + 8} />
          <text className="axis" x={x(m) + 3} y={axisY + 11}>{monthLabel(m)}</text>
        </g>)}
        {/* Rain panel */}
        <text className="panel-label" x={left - 6} y={top + 8} textAnchor="end">{rainTick}</text>
        <text className="panel-label" x={left - 6} y={rainBase} textAnchor="end">0</text>
        <text className="panel-unit" x={4} y={top + rainH / 2 + 3}>{t('mm')}</text>
        <line className="baseline" x1={left} x2={width - right} y1={rainBase} y2={rainBase} />
        {coverageEnd < t1 && <g>
          <rect x={x(coverageEnd)} y={top} width={x(t1) - x(coverageEnd)} height={rainH} fill="url(#nodata-hatch)" className="nodata" />
          <text className="nodata-label" x={(x(coverageEnd) + x(t1)) / 2} y={top + rainH / 2 + 3} textAnchor="middle">{t('No rainfall data yet')}</text>
        </g>}
        {data.rain.days.map(([date, mm]) => {
          const h = mm / rainTick * rainH;
          return mm > 0 ? <rect key={date} className="bar rain" x={x(ms(date)) + 0.5} y={rainBase - h} width={Math.max(1, dayW - 1)} height={h} /> : null;
        })}
        {/* VIIRS panel */}
        <text className="panel-label" x={left - 6} y={viirsTop + 8} textAnchor="end">{viirsTick}</text>
        <text className="panel-label" x={left - 6} y={viirsBase} textAnchor="end">0</text>
        <text className="panel-unit" x={4} y={viirsTop + viirsH / 2 + 3}>{t('km²')}</text>
        <line className="baseline" x1={left} x2={width - right} y1={viirsBase} y2={viirsBase} />
        {data.viirs.periods.map((p) => {
          const x0 = x(ms(p.start)), x1 = x(ms(p.end) + DAY), h = p.km2 / viirsTick * viirsH;
          return <g key={p.start}>
            {p.km2 > 0
              ? <rect className="bar viirs" x={x0} y={viirsBase - h} width={Math.max(2, x1 - x0)} height={h} />
              : <line className="viirs-zero" x1={x0} x2={x1} y1={viirsBase - 1.5} y2={viirsBase - 1.5} />}
            {p === peak && <text className="peak-label" x={(x0 + x1) / 2} y={viirsBase - h - 4} textAnchor="middle">{fn(p.km2, 1)}</text>}
          </g>;
        })}
        {/* Event line */}
        <line className="event-line" x1={x(ms(event.date))} x2={x(ms(event.date))} y1={top - 6} y2={trackY + 8} />
        <text className="event-label" x={x(ms(event.date)) + 4} y={top - 8}>{t('Dam failure')} · {fd(event.date, false)}</text>
        {/* Radar track */}
        <text className="panel-unit" x={4} y={trackY + 4}>{t('Radar')}</text>
        <line className="track" x1={left} x2={width - right} y1={trackY} y2={trackY} />
        {observations.map((o) => {
          const cx = x(ms(o.date) + DAY / 2);
          const side = o.id === leftId ? 'left' : o.id === rightId ? 'right' : '';
          return <g key={o.id} className={'radar-mark ' + side}>
            <path d={`M ${cx} ${trackY - 9} L ${cx + 9} ${trackY} L ${cx} ${trackY + 9} L ${cx - 9} ${trackY} Z`} />
            {side && <text x={cx} y={trackY + 3.5} textAnchor="middle">{side === 'left' ? t('L') : t('R')}</text>}
          </g>;
        })}
        {hover !== null && <line className="hover-line" x1={x(hover + DAY / 2)} x2={x(hover + DAY / 2)} y1={top} y2={trackY + 8} />}
      </svg>
      {hoverInfo && hover !== null && <div className="context-tooltip" aria-hidden="true" style={{ left: x(hover) + 196 > width ? x(hover) - 192 : x(hover) + 12, top: top + 4 }}>
        <strong>{fd(hoverInfo.date)}</strong>
        <span>{t('Rain')}: {hoverInfo.rain ? fn(hoverInfo.rain[1], 1) + ' ' + t('mm') : t('no data')}</span>
        <span>VIIRS: {hoverInfo.period ? fn(hoverInfo.period.km2, 2) + ' km²' : t('no composite')}</span>
        {hoverInfo.obs && <span>{t('RADARSAT-2 image')}</span>}
      </div>}
    </div>
    <figcaption className="context-caption">
      <span>{t('Rain: {source}.', { source: t(data.rain.source) })} {t('Flood signal: {source}, {r} km radius.', { source: data.viirs.source, r: data.viirs.radius_km })}</span>
      <span>{t('Different sensors and footprints from the radar analysis: timing context only. No VIIRS detection does not prove dry ground.')}</span>
      <button type="button" className="link-button" aria-expanded={table} aria-controls="context-table" onClick={() => setTable((v) => !v)}>{table ? t('Hide data table') : t('Show data table')}</button>
    </figcaption>
    {table && <div id="context-table" className="context-tables">
      <table>
        <caption>{t('Flood signal and radar dates')}</caption>
        <thead><tr><th scope="col">{t('Date')}</th><th scope="col">{t('Item')}</th><th scope="col">{t('Value')}</th></tr></thead>
        <tbody>
          {[
            ...data.viirs.periods.map((p) => ({ key: 'v' + p.start, sort: p.start, date: periodLabel(p), item: t('VIIRS mapped flood area'), value: fn(p.km2, 2) + ' km²' })),
            ...observations.map((o) => ({ key: 'r' + o.id, sort: o.date, date: fd(o.date), item: t('RADARSAT-2 image'), value: o.id === leftId ? t('Left image') : o.id === rightId ? t('Right image') : '—' })),
            { key: 'event', sort: event.date, date: fd(event.date), item: t('Dam failure'), value: '—' },
          ].sort((a, b) => a.sort.localeCompare(b.sort)).map((row) => <tr key={row.key}><td>{row.date}</td><td>{row.item}</td><td>{row.value}</td></tr>)}
        </tbody>
      </table>
      <div className="rain-table" tabIndex={0} role="region" aria-label={t('Daily rainfall (mm)')}>
        <table>
          <caption>{t('Daily rainfall (mm)')}</caption>
          <thead><tr><th scope="col">{t('Date')}</th><th scope="col">{t('mm')}</th></tr></thead>
          <tbody>{data.rain.days.map(([date, mm]) => <tr key={date}><td>{fd(date)}</td><td>{fn(mm, 1)}</td></tr>)}</tbody>
        </table>
      </div>
    </div>}
  </figure>;
}
