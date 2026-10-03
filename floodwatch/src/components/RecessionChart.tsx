import type { Pass, UnitProps } from '../lib/types';
import { FLOODED_SHARE, fmtDate } from '../lib/analysis';

interface Props {
  unit: UnitProps;
  passes: Pass[];
  passIndex: number;
  dryDate?: string;
}

/** Water left in one place, pass by pass, on a true time axis. */
export function RecessionChart({ unit, passes, passIndex, dryDate }: Props) {
  const W = 320;
  const H = 150;
  const pad = { l: 40, r: 12, t: 12, b: 26 };
  const day = (iso: string) => Date.parse(iso + 'T00:00:00Z') / 86_400_000;
  const d0 = day(passes[0].date);
  const dEnd = Math.max(day(passes[passes.length - 1].date), dryDate ? day(dryDate) : 0);
  const maxY = Math.max(unit.area_ha, 1);
  const X = (iso: string) => pad.l + ((day(iso) - d0) / (dEnd - d0 || 1)) * (W - pad.l - pad.r);
  const Y = (v: number) => pad.t + (1 - v / maxY) * (H - pad.t - pad.b);

  const known = passes.slice(0, passIndex + 1);
  const line = known.map((p, i) => `${i ? 'L' : 'M'}${X(p.date).toFixed(1)},${Y(unit.water_ha_by_pass[i]).toFixed(1)}`).join('');
  const last = known[known.length - 1];
  const lastV = unit.water_ha_by_pass[passIndex];
  const threshold = FLOODED_SHARE * unit.area_ha;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Water remaining in ${unit.name} by pass`}>
      <line x1={pad.l} x2={W - pad.r} y1={Y(0)} y2={Y(0)} className="axis" />
      <line x1={pad.l} x2={W - pad.r} y1={Y(threshold)} y2={Y(threshold)} className="threshold" />
      <text x={pad.l + 4} y={Y(threshold) - 4} className="tick">
        counts as clear
      </text>
      <text x={pad.l - 6} y={Y(maxY) + 4} textAnchor="end" className="tick">
        {Math.round(maxY)} ha
      </text>
      <text x={pad.l - 6} y={Y(0) + 4} textAnchor="end" className="tick">
        0
      </text>
      {passes.map((p, i) => (
        <line key={p.date} x1={X(p.date)} x2={X(p.date)} y1={Y(0)} y2={Y(0) + 4} className={i <= passIndex ? 'axis' : 'axis faint'} />
      ))}
      <text x={X(passes[0].date)} y={H - 6} className="tick">
        {fmtDate(passes[0].date)}
      </text>
      <text x={W - pad.r} y={H - 6} textAnchor="end" className="tick">
        {fmtDate(dryDate && day(dryDate) > day(passes[passes.length - 1].date) ? dryDate : passes[passes.length - 1].date)}
      </text>
      {dryDate && lastV > threshold && (
        <line x1={X(last.date)} y1={Y(lastV)} x2={X(dryDate)} y2={Y(threshold)} className="trend" />
      )}
      <path d={line} className="series" />
      {known.map((p, i) => (
        <circle key={p.date} cx={X(p.date)} cy={Y(unit.water_ha_by_pass[i])} r={i === passIndex ? 4.5 : 3} className={i === passIndex ? 'dot now' : 'dot'} />
      ))}
    </svg>
  );
}
