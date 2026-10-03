import type { Manifest } from '../lib/types';
import type { LayerState, Basemap } from './MapView';
import { fmtDate, itemForDate } from '../lib/analysis';

interface Props {
  manifest: Manifest;
  layers: LayerState;
  passIndex: number;
  onChange: (l: LayerState) => void;
}

export function LayerPanel({ manifest, layers, passIndex, onChange }: Props) {
  const radar = manifest.layers.radar;
  const auxLayers = manifest.aux_layers ?? [];
  const passDate = manifest.passes[passIndex].date;
  const aux = auxLayers.find((a) => a.id === layers.aux) ?? null;
  const auxItem = aux ? itemForDate(aux.items, passDate) : undefined;
  const lg = manifest.layers.flood_duration.legend;
  const gridUnits = manifest.units_source?.startsWith('grid') ?? false;
  const set = <K extends keyof LayerState>(k: K, v: LayerState[K]) => onChange({ ...layers, [k]: v });
  return (
    <aside className="layer-panel" aria-label="Map layers">
      <h2>Map layers</h2>

      <label className="layer">
        <input type="checkbox" checked={layers.duration} onChange={(e) => set('duration', e.target.checked)} />
        <span>
          <strong>How long it stayed flooded</strong>
          <small>Days under water after the dam failed, from all RADARSAT-2 passes</small>
        </span>
      </label>
      <div className="legend" aria-hidden={!layers.duration}>
        <div className="ramp" style={{ background: `linear-gradient(90deg, ${lg.colors.join(',')})` }} />
        <div className="ramp-labels">
          <span>{lg.min_days} days</span>
          <span>{lg.max_days}+ days</span>
        </div>
      </div>

      <label className="layer">
        <input type="checkbox" checked={layers.water} onChange={(e) => set('water', e.target.checked)} />
        <span>
          <strong>Water at the selected pass</strong>
          <small>What the radar saw on that date</small>
        </span>
      </label>

      <label className="layer">
        <input type="checkbox" checked={layers.places} onChange={(e) => set('places', e.target.checked)} />
        <span>
          <strong>{gridUnits ? `Flooded ground, ${manifest.units_source!.replace('grid ', '')} cells` : 'Settlements and cropland'}</strong>
          <small>
            <i className="swatch flooded" /> still flooded <i className="swatch clear" /> clear.
            {gridUnits ? ' Add place polygons to the ingest to rank named places.' : ' Dashed outline is cropland.'}
          </small>
        </span>
      </label>

      {radar && (
        <label className="layer">
          <input type="checkbox" checked={layers.radar} onChange={(e) => set('radar', e.target.checked)} />
          <span>
            <strong>Radar image</strong>
            <small>
              RADARSAT-2 backscatter on this pass. Water is dark, buildings bright ({radar.legend.min_db} to {radar.legend.max_db} dB).
            </small>
          </span>
        </label>
      )}

      {auxLayers.length > 0 && (
        <fieldset className="context">
          <legend>Context data</legend>
          <label>
            <input type="radio" name="aux" checked={layers.aux === null} onChange={() => set('aux', null)} />
            None
          </label>
          {auxLayers.map((a) => (
            <label key={a.id}>
              <input type="radio" name="aux" checked={layers.aux === a.id} onChange={() => set('aux', a.id)} />
              {a.name}
            </label>
          ))}
          {aux && (
            <div className="legend">
              <div className="ramp" style={{ background: `linear-gradient(90deg, ${aux.legend.colors.join(',')})` }} />
              <div className="ramp-labels">
                <span>
                  {aux.legend.min} {aux.unit}
                </span>
                <span>
                  {aux.legend.max} {aux.unit}
                </span>
              </div>
              <small className="muted">
                {auxItem?.date ? `Showing ${fmtDate(auxItem.date, true)}, the latest before this pass.` : 'Single date.'}
                {aux.note ? ` ${aux.note}.` : ''}
              </small>
            </div>
          )}
        </fieldset>
      )}

      <label className="opacity">
        Flood layer opacity
        <input
          type="range"
          min={0.2}
          max={1}
          step={0.05}
          value={layers.opacity}
          onChange={(e) => set('opacity', Number(e.target.value))}
        />
      </label>

      <fieldset className="basemap">
        <legend>Background</legend>
        {(['imagery', 'streets'] as Basemap[]).map((b) => (
          <label key={b}>
            <input type="radio" name="basemap" checked={layers.basemap === b} onChange={() => set('basemap', b)} />
            {b === 'imagery' ? 'Satellite imagery' : 'Streets'}
          </label>
        ))}
      </fieldset>

      <p className="method">
        Water is detected from RADARSAT-2 HH backscatter (5 m), which sees through cloud. Permanent rivers and lakes are
        removed with a reference water mask.
      </p>
    </aside>
  );
}
