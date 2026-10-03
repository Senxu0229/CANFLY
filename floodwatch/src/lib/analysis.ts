import type { DryEstimate, Pass, RankedUnit, UnitCollection, UnitProps, Weights } from './types';

/** A place counts as "still flooded" when more than 5% of it is under water. */
export const FLOODED_SHARE = 0.05;

export const isFlooded = (p: UnitProps, i: number) => p.water_ha_by_pass[i] > FLOODED_SHARE * p.area_ha;

const DAY = 86_400_000;
const toDay = (iso: string) => Date.parse(iso + 'T00:00:00Z') / DAY;
const fromDay = (d: number) => new Date(Math.round(d) * DAY).toISOString().slice(0, 10);

/**
 * When will this place be dry? Uses only passes up to the selected one,
 * so scrubbing the timeline back shows what was knowable on that date.
 */
export function estimateDry(p: UnitProps, passes: Pass[], upto: number): DryEstimate {
  const series = p.water_ha_by_pass.slice(0, upto + 1);
  const everWet = series.some((_, i) => isFlooded(p, i));
  if (!everWet) return { kind: 'never', label: 'Not flooded in any pass so far' };
  if (!isFlooded(p, upto)) {
    let first = upto;
    while (first > 0 && !isFlooded(p, first - 1)) first--;
    return { kind: 'cleared', date: passes[first].date, label: `Cleared by ${fmtDate(passes[first].date)}` };
  }
  // Linear trend over the last 3 passes.
  const idx = [upto - 2, upto - 1, upto].filter((i) => i >= 0);
  if (idx.length < 2) return { kind: 'stalled', label: 'Need two passes to estimate' };
  const xs = idx.map((i) => toDay(passes[i].date));
  const ys = idx.map((i) => series[i]);
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
  const my = ys.reduce((a, b) => a + b, 0) / ys.length;
  let num = 0;
  let den = 0;
  xs.forEach((x, k) => {
    num += (x - mx) * (ys[k] - my);
    den += (x - mx) ** 2;
  });
  const slope = den === 0 ? 0 : num / den; // ha per day
  if (slope >= -0.01) return { kind: 'stalled', label: 'Water is not receding' };
  const target = FLOODED_SHARE * p.area_ha;
  const dryDay = xs[xs.length - 1] + (ys[ys.length - 1] - target) / -slope;
  const date = fromDay(dryDay);
  return { kind: 'estimate', date, label: `Likely dry around ${fmtDate(date)}` };
}

export const PRESETS: { id: string; name: string; hint: string; weights: Weights }[] = [
  {
    id: 'balanced',
    name: 'Balanced',
    hint: 'Equal weight on every factor.',
    weights: { water: 1, buildings: 1, cropland: 1, duration: 1 },
  },
  {
    id: 'shelter',
    name: 'Shelter',
    hint: 'Homes standing in water come first.',
    weights: { water: 1, buildings: 3, cropland: 0, duration: 2 },
  },
  {
    id: 'drainage',
    name: 'Drainage & health',
    hint: 'Standing water near homes, held the longest.',
    weights: { water: 3, buildings: 2, cropland: 0, duration: 2 },
  },
  {
    id: 'farmland',
    name: 'Farmland',
    hint: 'Cropland that is still waterlogged.',
    weights: { water: 1, buildings: 0, cropland: 3, duration: 1 },
  },
];

export function rankUnits(units: UnitCollection, passes: Pass[], i: number, w: Weights): RankedUnit[] {
  const rows = units.features.map((feature) => {
    const p = feature.properties;
    return {
      feature,
      props: p,
      waterNow: p.water_ha_by_pass[i],
      buildingsNow: p.buildings_in_water_by_pass[i],
      croplandNow: p.cropland_flooded_ha_by_pass[i],
      floodedNow: isFlooded(p, i),
      // days in water as of this pass
      daysNow: lastWetDay(p, passes, i),
    };
  });
  const max = (f: (r: (typeof rows)[number]) => number) => Math.max(1e-9, ...rows.map(f));
  const mW = max((r) => r.waterNow);
  const mB = max((r) => r.buildingsNow);
  const mC = max((r) => r.croplandNow);
  const mD = max((r) => r.daysNow);
  const total = w.water + w.buildings + w.cropland + w.duration || 1;
  const scored = rows.map((r) => {
    const score = r.floodedNow
      ? (w.water * (r.waterNow / mW) +
          w.buildings * (r.buildingsNow / mB) +
          w.cropland * (r.croplandNow / mC) +
          w.duration * (r.daysNow / mD)) /
        total
      : 0;
    return { ...r, score, dry: estimateDry(r.props, passes, i) };
  });
  scored.sort((a, b) => b.score - a.score || b.waterNow - a.waterNow);
  return scored.map((r, k) => ({
    props: r.props,
    feature: r.feature,
    rank: k + 1,
    score: r.score,
    waterNow: r.waterNow,
    buildingsNow: r.buildingsNow,
    croplandNow: r.croplandNow,
    floodedNow: r.floodedNow,
    dry: r.dry,
  }));
}

function lastWetDay(p: UnitProps, passes: Pass[], upto: number) {
  let d = 0;
  for (let k = 0; k <= upto; k++) if (isFlooded(p, k)) d = passes[k].days_since_event;
  return d;
}

export function fmtDate(iso: string, withYear = false) {
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
    timeZone: 'UTC',
  });
}

export const fmtNum = (n: number) => Math.round(n).toLocaleString('en-US');

/** Which item of a dated layer to show for a pass: the latest one on or before it, else the first. */
export function itemForDate<T extends { date: string | null }>(items: T[], passDate: string): T | undefined {
  const dated = items.filter((i) => i.date).sort((a, b) => (a.date! < b.date! ? -1 : 1));
  if (!dated.length) return items[0];
  const before = dated.filter((i) => i.date! <= passDate);
  return before.length ? before[before.length - 1] : dated[0];
}

export const kindLabel = (t: string) => (t === 'settlement' ? 'settlement' : t === 'cropland' ? 'cropland' : 'area');

/** One plain-language sentence a coordinator can read aloud in a meeting. */
export function summarise(r: RankedUnit, passes: Pass[], i: number): string {
  const p = r.props;
  const first = p.water_ha_by_pass.findIndex((_, k) => isFlooded(p, k));
  if (first === -1 || first > i) return `${p.name} has not been under water in any pass up to ${fmtDate(passes[i].date)}.`;
  const start = p.water_ha_by_pass[first];
  const fell = start > 0 ? Math.round((1 - r.waterNow / start) * 100) : 0;
  if (!r.floodedNow) {
    return `${p.name} is clear of floodwater as of ${fmtDate(passes[i].date)}. It was flooded on ${fmtDate(passes[first].date)}.`;
  }
  const parts = [`On ${fmtDate(passes[i].date)}, ${fmtNum(r.waterNow)} ha of ${p.name} is still under water`];
  if (r.buildingsNow > 0) parts.push(`${fmtNum(r.buildingsNow)} of ${fmtNum(p.buildings_total)} buildings stand in it`);
  if (r.croplandNow >= 1) parts.push(`${fmtNum(r.croplandNow)} ha of cropland cannot be planted`);
  let s = parts.join('; ') + '.';
  if (i > first) s += ` Water has fallen ${fell}% since ${fmtDate(passes[first].date)}.`;
  return s;
}
