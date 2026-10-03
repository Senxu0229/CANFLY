"""
Turn processed GeoTIFFs from the server into the files the web app reads.

    python3 scripts/ingest.py --init      # scan incoming/ and write a draft ingest.config.json
    python3 scripts/ingest.py             # build public/data/ from ingest.config.json

Inputs (all optional except the water rasters):
  water        one GeoTIFF per RADARSAT-2 pass: a water mask (1 = water), or calibrated
               backscatter in dB (water = below a threshold)
  radar        one backscatter GeoTIFF per pass, shown as a grey radar image under the flood layers
  reference_water   permanent rivers/lakes to exclude (1 = water)
  cropland     land-cover GeoTIFF (e.g. ESA WorldCover; class 40 = cropland)
  units        GeoJSON polygons of settlements / fields (EPSG:4326). Without it a 1 km grid is used.
  buildings    GeoJSON points or polygons of buildings (EPSG:4326)
  aux          any number of context datasets (rainfall, ...): one GeoTIFF per date

Outputs: public/data/manifest.json, units.geojson, flood_duration.png, water_<date>.png,
         radar_<date>.png, aux_<id>_<date>.png. See DATA_CONTRACT.md.

Needs: numpy, pillow, scipy (tifffile optional, recommended).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from datetime import date, datetime, timezone

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
from geotiff_lite import read_geotiff  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

DURATION_COLORS = ['#d6eaf5', '#96c4e6', '#5392cd', '#2660a8', '#183678', '#131c52']
RAMPS = {
    'rain': ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
    'heat': ['#ffffcc', '#fed976', '#fd8d3c', '#e31a1c', '#800026'],
    'green': ['#f7fcf5', '#c7e9c0', '#74c476', '#238b45', '#00441b'],
    'grey': ['#000000', '#ffffff'],
}
WATER_RGBA = (31, 111, 178, 200)
REF_RGBA = (90, 120, 140, 140)


def log(*a):
    print(*a, flush=True)


def hex_rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def colorize(values, vmin, vmax, colors, alpha=215):
    """Map a float array to RGBA with a linear ramp; NaN -> transparent."""
    ramp = np.array([hex_rgb(c) for c in colors], np.float32)
    t = np.clip((values - vmin) / (vmax - vmin if vmax != vmin else 1), 0, 1) * (len(ramp) - 1)
    t = np.nan_to_num(t, nan=0.0)
    lo = np.floor(t).astype(int)
    hi = np.minimum(lo + 1, len(ramp) - 1)
    f = (t - lo)[..., None]
    rgb = ramp[lo] * (1 - f) + ramp[hi] * f
    out = np.zeros(values.shape + (4,), np.uint8)
    out[..., :3] = rgb.astype(np.uint8)
    out[..., 3] = np.where(np.isnan(values), 0, alpha)
    return out


def save_png(rgba, path):
    Image.fromarray(rgba, 'RGBA').save(path, optimize=True)


def save_radar(rgba, out_dir, stem):
    """Radar speckle does not compress as PNG; use WebP when Pillow supports it."""
    from PIL import features
    im = Image.fromarray(rgba, 'RGBA')
    if features.check('webp'):
        name = stem + '.webp'
        im.save(os.path.join(out_dir, name), quality=72, method=4)
    else:
        name = stem + '.png'
        im.convert('LA').save(os.path.join(out_dir, name), optimize=True)
    return name


DATE_RE = re.compile(r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2})')


def find_date(name):
    m = DATE_RE.search(os.path.basename(name))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


# --- step 0: draft a config from whatever is in incoming/ ------------------------
def init_config(incoming, out_path):
    files = sorted(glob.glob(os.path.join(incoming, '**', '*.tif*'), recursive=True))
    geo = sorted(glob.glob(os.path.join(incoming, '**', '*.geojson'), recursive=True))
    cfg = {
        'event': {'name': 'Alau Dam failure, Maiduguri', 'date': '2024-09-10'},
        'aoi_name': 'Maiduguri, Borno State, Nigeria',
        'bbox': None,
        'max_size': 3000,
        'water_mode': 'auto',
        'db_threshold': -18.0,
        'radar_db_range': [-25.0, 0.0],
        'water': [], 'radar': [], 'reference_water': None,
        'cropland': None, 'cropland_values': [40],
        'units': None, 'buildings': None, 'grid_km': 1.0,
        'aux': [],
        'credit': 'RADARSAT-2 Data and Products (c) MDA. Replace with the credit line required by the RADARSAT-2 EULA.',
    }
    aux = {}
    for f in files:
        rel = os.path.relpath(f, ROOT)
        low = os.path.basename(f).lower()
        d = find_date(f)
        if any(k in low for k in ('rain', 'chirps', 'precip', 'era5')):
            aux.setdefault('rainfall', []).append({'date': d, 'file': rel})
        elif any(k in low for k in ('ref', 'perm', 'jrc', 'occurrence')):
            cfg['reference_water'] = rel
        elif any(k in low for k in ('crop', 'worldcover', 'landcover', 'lc_')):
            cfg['cropland'] = rel
        elif any(k in low for k in ('_db', 'sigma', 'backscatter', 'sig0', 'radar')):
            cfg['radar'].append({'date': d, 'file': rel})
        else:
            cfg['water'].append({'date': d, 'file': rel, 'scene_id': os.path.splitext(os.path.basename(f))[0]})
    for g in geo:
        low = os.path.basename(g).lower()
        if 'build' in low:
            cfg['buildings'] = os.path.relpath(g, ROOT)
        else:
            cfg['units'] = os.path.relpath(g, ROOT)
    if 'rainfall' in aux:
        cfg['aux'].append({'id': 'rainfall', 'name': 'Rainfall', 'unit': 'mm', 'ramp': 'rain',
                           'range': None, 'items': sorted(aux['rainfall'], key=lambda x: x['date'] or '')})
    cfg['water'].sort(key=lambda x: x['date'] or '')
    cfg['radar'].sort(key=lambda x: x['date'] or '')
    with open(out_path, 'w') as fh:
        json.dump(cfg, fh, indent=2)
    log(f'Wrote {os.path.relpath(out_path, ROOT)} from {len(files)} GeoTIFFs and {len(geo)} GeoJSON files.')
    missing = [w['file'] for w in cfg['water'] + cfg['radar'] if not w['date']]
    if missing:
        log('No date found in these file names; fill in "date" by hand:', *missing, sep='\n  ')
    log('Check the classification, then run:  python3 scripts/ingest.py')


# --- the analysis grid ---------------------------------------------------------------
class Grid:
    """A north-up lon/lat grid all inputs are resampled onto."""

    def __init__(self, bbox, max_size):
        w, s, e, n = bbox
        mid = math.radians((s + n) / 2)
        width_m = (e - w) * 111_320 * math.cos(mid)
        height_m = (n - s) * 110_574
        scale = max(width_m, height_m) / max_size
        self.nx = max(1, int(round(width_m / scale)))
        self.ny = max(1, int(round(height_m / scale)))
        self.bbox = bbox
        self.dlon = (e - w) / self.nx
        self.dlat = (n - s) / self.ny
        lons = w + (np.arange(self.nx) + 0.5) * self.dlon
        lats = n - (np.arange(self.ny) + 0.5) * self.dlat
        self.lon, self.lat = np.meshgrid(lons, lats)
        # hectares per pixel, per row (pixels shrink east-west away from the equator)
        row_ha = (self.dlon * 111_320 * np.cos(np.radians(lats))) * (self.dlat * 110_574) / 10_000
        self.pix_ha = np.repeat(row_ha[:, None], self.nx, axis=1).astype(np.float32)
        self.res_m = scale

    def sample(self, raster):
        return raster.sample(self.lon, self.lat)

    def to_px(self, lon, lat):
        w, s, e, n = self.bbox
        return (lon - w) / self.dlon, (n - lat) / self.dlat

    def to_lonlat(self, x, y):
        w, s, e, n = self.bbox
        return w + x * self.dlon, n - y * self.dlat

    def rasterize(self, ring):
        img = Image.new('L', (self.nx, self.ny), 0)
        ImageDraw.Draw(img).polygon([self.to_px(lon, lat) for lon, lat in ring], fill=1)
        return np.array(img, bool)


def water_mask(values, mode, threshold):
    v = values
    valid = ~np.isnan(v)
    if mode == 'auto':
        finite = v[valid]
        uniq = np.unique(finite[:100000]) if finite.size else np.array([])
        if uniq.size and np.all(np.isin(uniq, [0, 1, 255])):
            mode = 'mask'
        elif finite.size and np.nanmedian(finite) < 0:
            mode = 'db'
        elif finite.size and np.nanmax(finite) <= 1.0:
            mode = 'probability'
        else:
            mode = 'linear'
    if mode == 'mask':
        m = valid & (v > 0) & (v != 255)
    elif mode == 'probability':
        m = valid & (v >= 0.5)
    elif mode == 'db':
        m = valid & (v < threshold)
    elif mode == 'linear':  # calibrated sigma0 in linear power
        with np.errstate(divide='ignore', invalid='ignore'):
            m = valid & (10 * np.log10(np.where(v > 0, v, np.nan)) < threshold)
    else:
        raise ValueError(f'unknown water_mode {mode}')
    return m, valid, mode


def load_geojson(path):
    with open(path) as fh:
        g = json.load(fh)
    return g['features'] if g.get('type') == 'FeatureCollection' else [g]


def outer_rings(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates'][0]]
    if geom['type'] == 'MultiPolygon':
        return [p[0] for p in geom['coordinates']]
    return []


def representative_point(geom):
    if geom['type'] == 'Point':
        return geom['coordinates'][:2]
    rings = outer_rings(geom)
    if not rings:
        return None
    ring = np.array(rings[0])[:, :2]
    return ring.mean(axis=0).tolist()


def build(cfg_path):
    with open(cfg_path) as fh:
        cfg = json.load(fh)
    p = lambda rel: os.path.join(ROOT, rel)  # noqa: E731
    out = os.path.join(ROOT, 'public', 'data')
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, '*')):
        if re.match(r'^(water_|radar_|aux_).*\.(png|webp)$|^flood_duration\.png$|^manifest\.json$|^units\.geojson$', os.path.basename(old)):
            os.remove(old)

    water_items = [w for w in cfg['water'] if w.get('file')]
    if not water_items:
        sys.exit('No water rasters listed in the config.')
    for w in water_items:
        if not w.get('date'):
            sys.exit(f"Missing date for {w['file']}. Add it in {os.path.relpath(cfg_path, ROOT)}.")
    water_items.sort(key=lambda x: x['date'])

    log(f'Reading {len(water_items)} water rasters')
    rasters = [read_geotiff(p(w['file'])) for w in water_items]
    if cfg.get('bbox'):
        bbox = tuple(cfg['bbox'])
    else:
        fps = np.array([r.footprint_lonlat() for r in rasters])
        bbox = tuple(float(v) for v in (fps[:, 0].min(), fps[:, 1].min(), fps[:, 2].max(), fps[:, 3].max()))
    grid = Grid(bbox, int(cfg.get('max_size', 3000)))
    log(f'Grid {grid.nx} x {grid.ny} px, about {grid.res_m:.1f} m per px, bbox {tuple(round(float(b), 5) for b in bbox)}')

    event_day = date.fromisoformat(cfg['event']['date'])
    passes, masks, valids = [], [], []
    for w, r in zip(water_items, rasters):
        vals = grid.sample(r)
        m, valid, mode = water_mask(vals, cfg.get('water_mode', 'auto'), float(cfg.get('db_threshold', -18)))
        masks.append(m)
        valids.append(valid)
        passes.append({'date': w['date'], 'scene_id': w.get('scene_id') or os.path.basename(w['file']),
                       'days_since_event': (date.fromisoformat(w['date']) - event_day).days})
        log(f"  {w['date']}: read as {mode}, water {float((m * grid.pix_ha).sum()):,.0f} ha, covered {valid.mean() * 100:.0f}% of grid")

    ref = np.zeros((grid.ny, grid.nx), bool)
    if cfg.get('reference_water'):
        rv = grid.sample(read_geotiff(p(cfg['reference_water'])))
        ref = ~np.isnan(rv) & (rv > 0) & (rv != 255)
        log(f'Reference water: {float((ref * grid.pix_ha).sum()):,.0f} ha excluded')
    flood = [m & ~ref for m in masks]
    covered_all = np.logical_and.reduce(valids)

    # water layers
    for ps, m in zip(passes, masks):
        rgba = np.zeros((grid.ny, grid.nx, 4), np.uint8)
        rgba[m & ~ref] = WATER_RGBA
        rgba[ref] = REF_RGBA
        save_png(rgba, os.path.join(out, f"water_{ps['date']}.png"))

    # VAP: flood duration (days since event at the last pass a pixel was flooded)
    duration = np.full((grid.ny, grid.nx), np.nan, np.float32)
    for ps, f in zip(passes, flood):
        duration[f] = ps['days_since_event']
    dmin, dmax = passes[0]['days_since_event'], passes[-1]['days_since_event']
    save_png(colorize(duration, dmin, dmax, DURATION_COLORS), os.path.join(out, 'flood_duration.png'))
    log('Wrote flood_duration.png (the VAP)')

    # radar images
    radar_layer = None
    if cfg.get('radar'):
        lo, hi = cfg.get('radar_db_range', [-25, 0])
        dates, ext = [], 'png'
        for item in cfg['radar']:
            if not item.get('date'):
                log(f"  skipped radar {item['file']}: no date")
                continue
            v = grid.sample(read_geotiff(p(item['file'])))
            if np.nanmedian(v) > 0:  # linear power -> dB
                with np.errstate(divide='ignore', invalid='ignore'):
                    v = 10 * np.log10(np.where(v > 0, v, np.nan))
            name = save_radar(colorize(v, lo, hi, RAMPS['grey'], alpha=255), out, f"radar_{item['date']}")
            ext = name.rsplit('.', 1)[1]
            dates.append(item['date'])
        radar_layer = {'type': 'image', 'url_template': 'data/radar_{date}.' + ext, 'bounds': list(bbox),
                       'dates': sorted(dates), 'legend': {'min_db': lo, 'max_db': hi}}
        log(f'Wrote {len(dates)} radar images')

    # cropland
    crop = None
    if cfg.get('cropland'):
        cv = grid.sample(read_geotiff(p(cfg['cropland'])))
        crop = np.isin(np.nan_to_num(cv, nan=-1), cfg.get('cropland_values', [40]))
        log(f'Cropland: {float((crop * grid.pix_ha).sum()):,.0f} ha in the area')

    # buildings -> pixel indices
    bpx = None
    if cfg.get('buildings'):
        pts = [representative_point(f['geometry']) for f in load_geojson(p(cfg['buildings']))]
        pts = np.array([q for q in pts if q is not None])
        if pts.size:
            bx, by = grid.to_px(pts[:, 0], pts[:, 1])
            bx, by = np.floor(bx).astype(int), np.floor(by).astype(int)
            ok = (bx >= 0) & (bx < grid.nx) & (by >= 0) & (by < grid.ny)
            bpx = (by[ok], bx[ok])
            log(f'Buildings: {ok.sum():,} inside the area')

    # auxiliary datasets (rainfall, ...)
    aux_layers, aux_grids = [], {}
    for a in cfg.get('aux', []):
        items = [i for i in a.get('items', []) if i.get('file')]
        vals = [(i.get('date'), grid.sample(read_geotiff(p(i['file'])))) for i in items]
        if not vals:
            continue
        rng = a.get('range') or [float(np.nanmin([np.nanmin(v) for _, v in vals])), float(np.nanmax([np.nanmax(v) for _, v in vals]))]
        colors = RAMPS.get(a.get('ramp', 'rain'), RAMPS['rain'])
        out_items = []
        for d, v in vals:
            name = f"aux_{a['id']}_{d or 'static'}.png"
            save_png(colorize(v, rng[0], rng[1], colors, alpha=190), os.path.join(out, name))
            out_items.append({'date': d, 'url': f'data/{name}'})
        aux_layers.append({'id': a['id'], 'name': a.get('name', a['id']), 'unit': a.get('unit', ''),
                           'bounds': list(bbox), 'legend': {'min': rng[0], 'max': rng[1], 'colors': colors},
                           'items': out_items, 'note': a.get('note', '')})
        aux_grids[a['id']] = vals
        log(f"Aux '{a['id']}': {len(out_items)} rasters, range {rng[0]:.1f} to {rng[1]:.1f} {a.get('unit', '')}")

    def aux_for_pass(aid, pass_date):
        vals = aux_grids[aid]
        dated = [(d, v) for d, v in vals if d]
        if not dated:
            return vals[0][1]
        before = [x for x in dated if x[0] <= pass_date]
        return (before[-1] if before else dated[0])[1]

    # units: given polygons, or a grid of cells over flooded ground
    ever = np.logical_or.reduce(flood)
    units_in = []
    if cfg.get('units'):
        for k, f in enumerate(load_geojson(p(cfg['units']))):
            rings = outer_rings(f['geometry'])
            if not rings:
                continue
            props = f.get('properties') or {}
            units_in.append({
                'id': str(props.get('id') or props.get('osm_id') or f'U{k + 1:03d}'),
                'name': props.get('name') or props.get('NAME') or f'Place {k + 1}',
                'type': props.get('type') if props.get('type') in ('settlement', 'cropland') else 'settlement',
                'lga': props.get('lga') or props.get('LGA') or props.get('admin2') or '',
                'geometry': f['geometry'], 'rings': rings,
            })
        log(f'Units: {len(units_in)} polygons from {cfg["units"]}')
    else:
        km = float(cfg.get('grid_km', 1.0))
        step = max(1, int(round(km * 1000 / grid.res_m)))
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for gy in range(0, grid.ny, step):
            for gx in range(0, grid.nx, step):
                cell = ever[gy:gy + step, gx:gx + step]
                if cell.mean() < 0.05:
                    continue
                x1, y1 = min(gx + step, grid.nx), min(gy + step, grid.ny)
                ring = [grid.to_lonlat(gx, gy), grid.to_lonlat(x1, gy), grid.to_lonlat(x1, y1), grid.to_lonlat(gx, y1), grid.to_lonlat(gx, gy)]
                r_i, c_i = gy // step, gx // step
                label = f"{letters[r_i % 26]}{'' if r_i < 26 else r_i // 26}{c_i + 1}"
                units_in.append({'id': f'G{label}', 'name': f'Grid cell {label}', 'type': 'area', 'lga': '',
                                 'geometry': {'type': 'Polygon', 'coordinates': [[[round(a, 6), round(b, 6)] for a, b in ring]]},
                                 'rings': [ring]})
        log(f'Units: no polygons given, using {len(units_in)} grid cells of {km:g} km over flooded ground')

    features = []
    for u in units_in:
        m = np.zeros((grid.ny, grid.nx), bool)
        for ring in u['rings']:
            m |= grid.rasterize(ring)
        m &= ~ref
        if not m.any():
            continue
        area = float((m * grid.pix_ha).sum())
        water_series = [round(float(((f & m) * grid.pix_ha).sum()), 2) for f in flood]
        days = 0
        for ps, ws in zip(passes, water_series):
            if ws > 0.05 * area:
                days = ps['days_since_event']
        crop_ha = float(((crop & m) * grid.pix_ha).sum()) if crop is not None else 0.0
        crop_series = [round(float(((crop & m & f) * grid.pix_ha).sum()), 2) for f in flood] if crop is not None else [0.0] * len(flood)
        if bpx is not None:
            inside = m[bpx]
            btotal = int(inside.sum())
            bseries = [int((inside & f[bpx]).sum()) for f in flood]
        else:
            btotal, bseries = 0, [0] * len(flood)
        aux = {}
        for aid in aux_grids:
            series = []
            for ps in passes:
                v = aux_for_pass(aid, ps['date'])[m]
                v = v[~np.isnan(v)]
                series.append(round(float(v.mean()), 2) if v.size else None)
            aux[aid] = series
        ys, xs = np.nonzero(m)
        clon, clat = grid.to_lonlat(xs.mean() + 0.5, ys.mean() + 0.5)
        features.append({'type': 'Feature', 'geometry': u['geometry'], 'properties': {
            'id': u['id'], 'name': u['name'], 'type': u['type'], 'lga': u['lga'],
            'area_ha': round(area, 2), 'centroid': [round(clon, 6), round(clat, 6)],
            'water_ha_by_pass': water_series, 'flooded_days': days,
            'buildings_total': btotal, 'buildings_in_water_by_pass': bseries,
            'cropland_ha': round(crop_ha, 2), 'cropland_flooded_ha_by_pass': crop_series,
            'aux': aux,
        }})
    with open(os.path.join(out, 'units.geojson'), 'w') as fh:
        json.dump({'type': 'FeatureCollection', 'features': features}, fh)

    kpis = []
    for i, (ps, f) in enumerate(zip(passes, flood)):
        kpis.append({
            'date': ps['date'],
            'flood_water_ha': round(float((f * grid.pix_ha).sum()), 1),
            'cropland_flooded_ha': round(float(((crop & f) * grid.pix_ha).sum()), 1) if crop is not None
            else round(sum(ft['properties']['cropland_flooded_ha_by_pass'][i] for ft in features), 1),
            'buildings_in_water': int(f[bpx].sum()) if bpx is not None
            else sum(ft['properties']['buildings_in_water_by_pass'][i] for ft in features),
            'places_still_flooded': sum(1 for ft in features
                                        if ft['properties']['water_ha_by_pass'][i] > 0.05 * ft['properties']['area_ha']),
        })

    manifest = {
        'schema_version': '1.1',
        'mock': bool(cfg.get('mock', False)),
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'event': cfg['event'],
        'aoi': {'name': cfg.get('aoi_name', ''), 'bounds': list(bbox)},
        'grid': {'width': grid.nx, 'height': grid.ny, 'pixel_m': round(grid.res_m, 2),
                 'observed_share': round(float(covered_all.mean()), 3)},
        'passes': passes,
        'layers': {
            'flood_duration': {'type': 'image', 'url': 'data/flood_duration.png', 'bounds': list(bbox),
                               'legend': {'min_days': dmin, 'max_days': dmax, 'colors': DURATION_COLORS}},
            'water': {'type': 'image', 'url_template': 'data/water_{date}.png', 'bounds': list(bbox)},
            **({'radar': radar_layer} if radar_layer else {}),
        },
        'aux_layers': aux_layers,
        'kpis_by_pass': kpis,
        'credit': cfg.get('credit', ''),
        'units_source': 'polygons' if cfg.get('units') else f"grid {cfg.get('grid_km', 1.0)} km",
    }
    with open(os.path.join(out, 'manifest.json'), 'w') as fh:
        json.dump(manifest, fh, indent=2)
    log(f'Done: {len(features)} units, {len(passes)} passes -> public/data/')
    for k in kpis:
        log(f"  {k['date']}: {k['flood_water_ha']:,.0f} ha flood water, {k['places_still_flooded']} places flooded")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=os.path.join(ROOT, 'ingest.config.json'))
    ap.add_argument('--init', action='store_true', help='scan --incoming and write a draft config')
    ap.add_argument('--incoming', default=os.path.join(ROOT, 'incoming'))
    a = ap.parse_args()
    if a.init:
        init_config(a.incoming, a.config)
    else:
        if not os.path.exists(a.config):
            sys.exit(f'No config at {a.config}. Run with --init first.')
        build(a.config)


if __name__ == '__main__':
    main()
