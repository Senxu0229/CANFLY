import type { Pass, RankedUnit, Weights } from '../lib/types';
import { PRESETS, fmtDate, fmtNum, kindLabel } from '../lib/analysis';
import { exportCsv, exportGeoJson, exportKml } from '../lib/exporters';

interface Props {
  ranked: RankedUnit[];
  pass: Pass;
  weights: Weights;
  onWeights: (w: Weights) => void;
  onPick: (id: string) => void;
  selectedId: string | null;
}

const FACTORS: { key: keyof Weights; label: string }[] = [
  { key: 'water', label: 'Water still standing' },
  { key: 'buildings', label: 'Buildings in water' },
  { key: 'cropland', label: 'Cropland flooded' },
  { key: 'duration', label: 'Time spent under water' },
];

export function PriorityPanel({ ranked, pass, weights, onWeights, onPick, selectedId }: Props) {
  const active = PRESETS.find((p) => FACTORS.every((f) => p.weights[f.key] === weights[f.key]));
  const flooded = ranked.filter((r) => r.floodedNow);
  const clear = ranked.length - flooded.length;
  return (
    <div className="priorities">
      <h2>Where to act first</h2>
      <p className="muted">
        {flooded.length} places still flooded on {fmtDate(pass.date, true)}, {clear} clear. Choose what matters to your team.
      </p>

      <div className="presets" role="radiogroup" aria-label="Ranking focus">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            role="radio"
            aria-checked={active?.id === p.id}
            className={`chip ${active?.id === p.id ? 'on' : ''}`}
            onClick={() => onWeights(p.weights)}
            title={p.hint}
          >
            {p.name}
          </button>
        ))}
      </div>
      <p className="hint">{active ? active.hint : 'Custom weighting.'}</p>

      <details className="weights">
        <summary>Adjust the weighting</summary>
        {FACTORS.map((f) => (
          <label key={f.key} className="weight">
            <span>{f.label}</span>
            <input
              type="range"
              min={0}
              max={3}
              step={1}
              value={weights[f.key]}
              onChange={(e) => onWeights({ ...weights, [f.key]: Number(e.target.value) })}
            />
            <output>{['off', 'low', 'medium', 'high'][weights[f.key]]}</output>
          </label>
        ))}
      </details>

      <ol className="rank-list">
        {flooded.map((r) => (
          <li key={r.props.id}>
            <button className={`rank-row ${selectedId === r.props.id ? 'selected' : ''}`} onClick={() => onPick(r.props.id)}>
              <span className="rank-num">{r.rank}</span>
              <span className="rank-body">
                <span className="rank-name">
                  {r.props.name}
                  <span className="muted"> {kindLabel(r.props.type)}</span>
                </span>
                <span className="rank-facts">
                  {fmtNum(r.waterNow)} ha in water
                  {r.buildingsNow > 0 && `, ${fmtNum(r.buildingsNow)} buildings`}
                  {r.croplandNow >= 1 && `, ${fmtNum(r.croplandNow)} ha cropland`}
                </span>
                <span className="score" aria-hidden="true">
                  <span style={{ width: `${Math.round(r.score * 100)}%` }} />
                </span>
              </span>
            </button>
          </li>
        ))}
        {flooded.length === 0 && <li className="empty">No place is flooded at this pass. Pick an earlier pass on the timeline.</li>}
      </ol>

      <div className="exports">
        <span>Send this list to the field</span>
        <button className="btn" onClick={() => exportKml(ranked, pass)}>
          KML for phones
        </button>
        <button className="btn" onClick={() => exportCsv(ranked, pass)}>
          CSV
        </button>
        <button className="btn" onClick={() => exportGeoJson(ranked, pass)}>
          GeoJSON
        </button>
      </div>
    </div>
  );
}
