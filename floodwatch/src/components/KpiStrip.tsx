import type { Manifest } from '../lib/types';
import { fmtDate, fmtNum } from '../lib/analysis';

interface Props {
  manifest: Manifest;
  passIndex: number;
}

export function KpiStrip({ manifest, passIndex }: Props) {
  const now = manifest.kpis_by_pass[passIndex];
  const prev = passIndex > 0 ? manifest.kpis_by_pass[passIndex - 1] : null;
  const pass = manifest.passes[passIndex];

  const items: { label: string; value: string; unit: string; key: keyof typeof now }[] = [
    { label: 'Floodwater on the ground', value: fmtNum(now.flood_water_ha), unit: 'ha', key: 'flood_water_ha' },
    { label: 'Cropland under water', value: fmtNum(now.cropland_flooded_ha), unit: 'ha', key: 'cropland_flooded_ha' },
    { label: 'Buildings standing in water', value: fmtNum(now.buildings_in_water), unit: '', key: 'buildings_in_water' },
    { label: 'Places still flooded', value: fmtNum(now.places_still_flooded), unit: '', key: 'places_still_flooded' },
  ];

  return (
    <section className="kpis" aria-label={`Situation on ${fmtDate(pass.date, true)}`}>
      <div className="kpi-when">
        <span className="kpi-day">Day {pass.days_since_event}</span>
        <span className="kpi-date">after the dam failed, pass of {fmtDate(pass.date, true)}</span>
      </div>
      {items.map((it) => {
        const before = prev ? (prev[it.key] as number) : null;
        const after = now[it.key] as number;
        const change = before && before > 0 ? Math.round(((after - before) / before) * 100) : null;
        return (
          <div className="kpi" key={it.key}>
            <span className="kpi-value">
              {it.value}
              {it.unit && <span className="kpi-unit"> {it.unit}</span>}
            </span>
            <span className="kpi-label">{it.label}</span>
            {change !== null && (
              <span className={`kpi-change ${change <= 0 ? 'better' : 'worse'}`}>
                {change <= 0 ? `${Math.abs(change)}% less` : `${change}% more`} than {fmtDate(manifest.passes[passIndex - 1].date)}
              </span>
            )}
          </div>
        );
      })}
    </section>
  );
}
