import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Manifest, UnitCollection, Weights } from './lib/types';
import { PRESETS, rankUnits } from './lib/analysis';
import { MapView, type LayerState } from './components/MapView';
import { KpiStrip } from './components/KpiStrip';
import { LayerPanel } from './components/LayerPanel';
import { PassStrip } from './components/PassStrip';
import { PriorityPanel } from './components/PriorityPanel';
import { PlacePanel } from './components/PlacePanel';

const DATA = './data/';

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [units, setUnits] = useState<UnitCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(DATA + 'manifest.json').then((r) => {
        if (!r.ok) throw new Error(`manifest.json: HTTP ${r.status}`);
        return r.json();
      }),
      fetch(DATA + 'units.geojson').then((r) => {
        if (!r.ok) throw new Error(`units.geojson: HTTP ${r.status}`);
        return r.json();
      }),
    ])
      .then(([m, u]) => {
        setManifest(m);
        setUnits(u);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error)
    return (
      <div className="status">
        <h1>Data not found</h1>
        <p>
          FloodWatch could not load <code>public/data/</code> ({error}). Run <code>npm run mock-data</code> or copy the
          export from the processing server into that folder, then reload.
        </p>
      </div>
    );
  if (!manifest || !units) return <div className="status">Loading flood data…</div>;
  return <Dashboard manifest={manifest} units={units} />;
}

function Dashboard({ manifest, units }: { manifest: Manifest; units: UnitCollection }) {
  const last = manifest.passes.length - 1;
  const [passIndex, setPassIndex] = useState(last);
  const [comparePassIndex, setComparePassIndex] = useState<number | null>(null);
  const [weights, setWeights] = useState<Weights>(PRESETS[0].weights);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const [layers, setLayers] = useState<LayerState>({
    basemap: 'imagery',
    duration: true,
    water: false,
    places: true,
    radar: false,
    aux: null,
    opacity: 0.8,
  });

  const ranked = useMemo(() => rankUnits(units, manifest.passes, passIndex, weights), [units, manifest.passes, passIndex, weights]);
  const selected = ranked.find((r) => r.props.id === selectedId) ?? null;

  const pick = useCallback((id: string) => {
    setSelectedId(id);
    setFocus((f) => ({ id, n: (f?.n ?? 0) + 1 }));
  }, []);

  // Comparing passes only makes sense with the per-pass water layer on.
  const onCompare = useCallback((i: number | null) => {
    setComparePassIndex(i);
    if (i !== null) setLayers((l) => ({ ...l, water: true, duration: false }));
  }, []);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>FloodWatch Maiduguri</h1>
          <p>
            Recovery tracking after the {manifest.event.name.replace(', Maiduguri', '')}, from RADARSAT-2 radar passes
          </p>
        </div>
        {manifest.mock && (
          <p className="mock-flag" role="status">
            Mock data for layout testing. Numbers and shapes are not real.
          </p>
        )}
      </header>

      <KpiStrip manifest={manifest} passIndex={passIndex} />

      <main className="body">
        <LayerPanel manifest={manifest} layers={layers} passIndex={passIndex} onChange={setLayers} />
        <div className="center">
          <MapView
            manifest={manifest}
            ranked={ranked}
            passIndex={passIndex}
            comparePassIndex={comparePassIndex}
            layers={layers}
            selectedId={selectedId}
            focus={focus}
            onSelect={pick}
          />
          <PassStrip
            manifest={manifest}
            passIndex={passIndex}
            comparePassIndex={comparePassIndex}
            onPass={setPassIndex}
            onCompare={onCompare}
          />
        </div>
        <aside className="side" aria-live="polite">
          {selected ? (
            <PlacePanel
              unit={selected}
              passes={manifest.passes}
              passIndex={passIndex}
              auxLayers={manifest.aux_layers ?? []}
              onBack={() => setSelectedId(null)}
            />
          ) : (
            <PriorityPanel
              ranked={ranked}
              pass={manifest.passes[passIndex]}
              weights={weights}
              onWeights={setWeights}
              onPick={pick}
              selectedId={selectedId}
            />
          )}
        </aside>
      </main>

      <footer className="credit">
        <span>{manifest.credit}</span>
        <span>
          Data version {manifest.schema_version}, generated {manifest.generated_at.slice(0, 10)}
        </span>
      </footer>
    </div>
  );
}
