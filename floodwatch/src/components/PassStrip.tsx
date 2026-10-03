import { useEffect, useState } from 'react';
import type { Manifest } from '../lib/types';
import { fmtDate, fmtNum } from '../lib/analysis';

interface Props {
  manifest: Manifest;
  passIndex: number;
  comparePassIndex: number | null;
  onPass: (i: number) => void;
  onCompare: (i: number | null) => void;
}

/**
 * The satellite passes laid out on a true time axis, from the dam failure onward.
 * Bar height = floodwater still on the ground at that pass.
 */
export function PassStrip({ manifest, passIndex, comparePassIndex, onPass, onCompare }: Props) {
  const [playing, setPlaying] = useState(false);
  const passes = manifest.passes;
  const kpis = manifest.kpis_by_pass;
  const maxDay = passes[passes.length - 1].days_since_event;
  const maxHa = Math.max(...kpis.map((k) => k.flood_water_ha));
  const x = (d: number) => (d / maxDay) * 100;

  // Passes can be 4 days apart: label only those with room, always the selected ones.
  const labelled = new Set<number>();
  const pos = passes.map((p) => x(p.days_since_event));
  const room = (i: number) => [...labelled].every((j) => Math.abs(pos[i] - pos[j]) >= 6);
  [passIndex, comparePassIndex].forEach((i) => i !== null && labelled.add(i));
  passes.forEach((_, i) => room(i) && labelled.add(i));

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      onPass(passIndex >= passes.length - 1 ? 0 : passIndex + 1);
    }, 1100);
    return () => clearInterval(t);
  }, [playing, passIndex, passes.length, onPass]);

  useEffect(() => {
    if (playing && passIndex === passes.length - 1) {
      const t = setTimeout(() => setPlaying(false), 1100);
      return () => clearTimeout(t);
    }
  }, [playing, passIndex, passes.length]);

  return (
    <section className="pass-strip" aria-label="Satellite passes">
      <div className="pass-controls">
        <button className="btn" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
          {playing ? 'Pause' : 'Play recession'}
        </button>
        <label className="compare-toggle">
          <input
            type="checkbox"
            checked={comparePassIndex !== null}
            onChange={(e) => onCompare(e.target.checked ? (passIndex === 0 ? passes.length - 1 : 0) : null)}
          />
          Compare two passes
        </label>
        {comparePassIndex !== null && (
          <label className="compare-select">
            Left side
            <select value={comparePassIndex} onChange={(e) => onCompare(Number(e.target.value))}>
              {passes.map((p, i) => (
                <option key={p.date} value={i}>
                  {fmtDate(p.date, true)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="timeline" role="listbox" aria-label="Choose a pass">
        <div className="timeline-event" style={{ left: '0%' }}>
          <span className="event-mark" />
          <span className="event-label">Dam fails, {fmtDate(manifest.event.date)}</span>
        </div>
        {passes.map((p, i) => {
          const k = kpis[i];
          const h = Math.max(4, (k.flood_water_ha / maxHa) * 100);
          const active = i === passIndex;
          const isCompare = i === comparePassIndex;
          return (
            <button
              key={p.date}
              role="option"
              aria-selected={active}
              className={`pass ${active ? 'active' : ''} ${isCompare ? 'compare' : ''}`}
              style={{ left: `${x(p.days_since_event)}%` }}
              onClick={() => onPass(i)}
              title={`${fmtDate(p.date, true)}: ${fmtNum(k.flood_water_ha)} ha of floodwater`}
            >
              <span className="bar" style={{ height: `${h}%` }} />
              {labelled.has(i) && <span className="pass-date">{fmtDate(p.date)}</span>}
            </button>
          );
        })}
      </div>
      <p className="timeline-note">
        Bars show floodwater still on the ground at each RADARSAT-2 pass, placed by days since the dam failed.
      </p>
    </section>
  );
}
