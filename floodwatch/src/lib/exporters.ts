import type { Pass, RankedUnit } from './types';

function download(name: string, mime: string, body: string) {
  const url = URL.createObjectURL(new Blob([body], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const row = (r: RankedUnit) => ({
  rank: r.rank,
  id: r.props.id,
  name: r.props.name,
  type: r.props.type,
  lga: r.props.lga,
  priority_score: +r.score.toFixed(3),
  still_flooded: r.floodedNow,
  water_ha: +r.waterNow.toFixed(1),
  buildings_in_water: r.buildingsNow,
  cropland_flooded_ha: +r.croplandNow.toFixed(1),
  dry_estimate: r.dry.label,
  lon: r.props.centroid[0],
  lat: r.props.centroid[1],
});

const stamp = (pass: Pass) => pass.date.replace(/-/g, '');

export function exportCsv(rows: RankedUnit[], pass: Pass) {
  const data = rows.map(row);
  const head = Object.keys(data[0] ?? {});
  const esc = (v: unknown) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [head.join(','), ...data.map((d) => head.map((h) => esc((d as Record<string, unknown>)[h])).join(','))].join('\n');
  download(`floodwatch_priorities_${stamp(pass)}.csv`, 'text/csv', csv);
}

export function exportGeoJson(rows: RankedUnit[], pass: Pass) {
  const fc = {
    type: 'FeatureCollection',
    features: rows.map((r) => ({ type: 'Feature', geometry: r.feature.geometry, properties: row(r) })),
  };
  download(`floodwatch_priorities_${stamp(pass)}.geojson`, 'application/geo+json', JSON.stringify(fc));
}

const xml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** KML opens offline in Google Earth, Organic Maps, OsmAnd: what field teams carry. */
export function exportKml(rows: RankedUnit[], pass: Pass) {
  const placemarks = rows
    .map((r) => {
      const ring = r.feature.geometry.coordinates[0].map(([x, y]) => `${x},${y},0`).join(' ');
      const style = r.floodedNow ? '#flooded' : '#clear';
      const desc = [
        `Priority #${r.rank}`,
        `Water: ${r.waterNow.toFixed(1)} ha`,
        `Buildings in water: ${r.buildingsNow}`,
        `Cropland flooded: ${r.croplandNow.toFixed(1)} ha`,
        r.dry.label,
      ].join('<br/>');
      return `<Placemark><name>${xml(`#${r.rank} ${r.props.name}`)}</name><styleUrl>${style}</styleUrl><description><![CDATA[${desc}]]></description><MultiGeometry><Point><coordinates>${r.props.centroid[0]},${r.props.centroid[1]},0</coordinates></Point><Polygon><outerBoundaryIs><LinearRing><coordinates>${ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>`;
    })
    .join('\n');
  const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>FloodWatch priorities ${pass.date}</name>
<Style id="flooded"><LineStyle><color>ff0e77b9</color><width>2</width></LineStyle><PolyStyle><color>660e77b9</color></PolyStyle></Style>
<Style id="clear"><LineStyle><color>ff4f7d3f</color><width>1</width></LineStyle><PolyStyle><color>334f7d3f</color></PolyStyle></Style>
${placemarks}
</Document></kml>`;
  download(`floodwatch_priorities_${stamp(pass)}.kml`, 'application/vnd.google-earth.kml+xml', kml);
}
