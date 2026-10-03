import type { AuxLayer, Pass, RankedUnit } from '../lib/types';
import { fmtDate, fmtNum, isFlooded, kindLabel, summarise } from '../lib/analysis';
import { RecessionChart } from './RecessionChart';

interface Props {
  unit: RankedUnit;
  passes: Pass[];
  passIndex: number;
  auxLayers: AuxLayer[];
  onBack: () => void;
}

export function PlacePanel({ unit, passes, passIndex, auxLayers, onBack }: Props) {
  const p = unit.props;
  const dryDate = unit.dry.kind === 'estimate' ? unit.dry.date : undefined;
  let daysSoFar = 0;
  for (let k = 0; k <= passIndex; k++) if (isFlooded(p, k)) daysSoFar = passes[k].days_since_event;
  return (
    <div className="place">
      <button className="link" onClick={onBack}>
        Back to priority list
      </button>
      <header className="place-head">
        <span className={`rank ${unit.floodedNow ? 'flooded' : 'clear'}`}>{unit.floodedNow ? `#${unit.rank}` : 'Clear'}</span>
        <div>
          <h2>{p.name}</h2>
          <p className="muted">
            {kindLabel(p.type).replace(/^./, (c) => c.toUpperCase())}
            {p.lga ? ` in ${p.lga}` : ''}, {fmtNum(p.area_ha)} ha
          </p>
        </div>
      </header>

      <p className="summary">{summarise(unit, passes, passIndex)}</p>

      <h3>Water left in this place</h3>
      <RecessionChart unit={p} passes={passes} passIndex={passIndex} dryDate={dryDate} />
      <p className={`dry ${unit.dry.kind}`}>
        {unit.dry.label}
        {unit.dry.kind === 'estimate' && <small> Estimate from the last three passes, not a forecast.</small>}
      </p>

      <dl className="facts">
        <div>
          <dt>Under water now</dt>
          <dd>{fmtNum(unit.waterNow)} ha</dd>
        </div>
        <div>
          <dt>Buildings in water</dt>
          <dd>
            {fmtNum(unit.buildingsNow)} <span className="muted">of {fmtNum(p.buildings_total)}</span>
          </dd>
        </div>
        <div>
          <dt>Cropland flooded</dt>
          <dd>
            {fmtNum(unit.croplandNow)} <span className="muted">of {fmtNum(p.cropland_ha)} ha</span>
          </dd>
        </div>
        <div>
          <dt>Days in water so far</dt>
          <dd>{daysSoFar}</dd>
        </div>
      </dl>

      {auxLayers
        .filter((a) => p.aux?.[a.id]?.some((v) => v !== null))
        .map((a) => {
          const series = p.aux![a.id];
          const max = Math.max(1e-9, ...series.map((v) => v ?? 0));
          const now = series[passIndex];
          return (
            <section className="aux" key={a.id}>
              <h3>{a.name} over this place</h3>
              <p className="aux-now">
                {now === null ? 'No data' : `${now.toFixed(1)} ${a.unit}`}
                <span className="muted"> around {fmtDate(passes[passIndex].date)}</span>
              </p>
              <div className="aux-bars" role="img" aria-label={`${a.name} for each pass`}>
                {series.map((v, i) => (
                  <span
                    key={passes[i].date}
                    className={i === passIndex ? 'now' : ''}
                    style={{ height: `${v === null ? 0 : Math.max(3, (v / max) * 100)}%` }}
                    title={`${fmtDate(passes[i].date)}: ${v === null ? 'no data' : `${v.toFixed(1)} ${a.unit}`}`}
                  />
                ))}
              </div>
            </section>
          );
        })}
    </div>
  );
}
