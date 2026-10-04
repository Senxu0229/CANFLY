#!/usr/bin/env python3
"""Write SYNTHETIC observation files so the frontend can run on a laptop without
the lab-server export (for UI work only).

  python3 scripts/make_mock_observations.py            # writes public/observations/

* Output follows the schema the app validates (manifest 2.0, analysis 1.0).
* Every value is invented; the credit line and notice say MOCK.
* public/observations/ is git-ignored. The script refuses to overwrite a real
  export (any manifest whose credit does not start with "MOCK") unless --force.
* Standard library only (no numpy / GDAL).
"""
import argparse
import json
import math
import random
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CENTER = (13.2846742, 11.7367804)
RADIUS = 6000
DATES = ['20240828', '20240921', '20241015', '20241108']
SIZE = 512


def png(path, width, height, rows):
    """rows: iterable of bytes objects, each width*4 RGBA bytes."""
    raw = b''.join(b'\x00' + row for row in rows)
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def inside(x, y):
    cx = cy = (SIZE - 1) / 2
    return (x - cx) ** 2 + (y - cy) ** 2 <= (SIZE / 2 - 1) ** 2


def radar(seed, wet):
    rnd = random.Random(seed)
    rows = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            if not inside(x, y):
                row += b'\x00\x00\x00\x00'
                continue
            # smooth "fields" plus speckle; a dark river band that widens when wet
            base = 120 + 40 * math.sin(x / 37) * math.cos(y / 53)
            river = abs((y - SIZE * .55) - 30 * math.sin(x / 60))
            width = 14 + wet * 22
            v = 25 if river < width else base
            v = max(0, min(255, v + rnd.gauss(0, 22)))
            row += bytes((int(v),) * 3) + b'\xff'
        rows.append(bytes(row))
    return rows


def change_overlay():
    rows = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            river = abs((y - SIZE * .55) - 30 * math.sin(x / 60))
            if not inside(x, y):
                row += b'\x00\x00\x00\x00'
            elif river < 14:
                row += bytes((23, 106, 175, 175))      # both dates
            elif river < 36:
                row += bytes((0, 220, 235, 235))       # new candidate
            elif (x // 40 + y // 40) % 9 == 0:
                row += bytes((238, 166, 75, 205))      # brighter, to check
            else:
                row += b'\x00\x00\x00\x00'
        rows.append(bytes(row))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'public/observations')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    out = args.out
    manifest_path = out / 'manifest.json'
    if manifest_path.exists() and not args.force:
        try:
            credit = json.loads(manifest_path.read_text()).get('credit', '')
        except ValueError:
            credit = ''
        if not credit.startswith('MOCK'):
            raise SystemExit(f'{manifest_path} looks like a real export. Refusing to overwrite (use --force only if you are sure).')
    out.mkdir(parents=True, exist_ok=True)

    dlat = RADIUS / 111_320
    dlon = dlat / math.cos(math.radians(CENTER[1]))
    bounds = [CENTER[0] - dlon, CENTER[1] - dlat, CENTER[0] + dlon, CENTER[1] + dlat]
    ring = [[CENTER[0] + dlon * math.cos(a), CENTER[1] + dlat * math.sin(a)] for a in (i / 64 * 2 * math.pi for i in range(65))]
    (out / 'aoi.geojson').write_text(json.dumps({'type': 'Feature', 'properties': {'name': 'Kalari Abdu (mock)'}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}))

    observations = []
    for i, date in enumerate(DATES):
        name = f'radar_{date}_mock.png'
        png(out / name, SIZE, SIZE, radar(i, wet=[0, 1, .5, .2][i]))
        iso = f'{date[:4]}-{date[4:6]}-{date[6:]}'
        observations.append({'id': date, 'date': iso, 'role': 'baseline' if i == 0 else 'post-event', 'label': iso,
                             'image_url': f'observations/{name}', 'source_product': 'MOCK_PRODUCT_' + date,
                             'beam_mode': 'MOCK', 'polarization': 'HH', 'orbit_direction': 'MOCK',
                             'acquisition_utc': iso + 'T05:00:00Z'})
    png(out / 'water_change_mock.png', SIZE, SIZE, change_overlay())
    for name in ['water_change_preview_mock.png']:
        png(out / name, 4, 4, [b'\x00' * 16] * 4)
    for name in ['analysis_20240828_mock.tif', 'analysis_20240921_mock.tif', 'water_change_classes_mock.tif']:
        (out / name).write_text('MOCK placeholder, not a GeoTIFF\n')

    persistent, new, lost = 10.0, 2.0, 3.0
    report = {
        'schema_version': '1.0', 'status': 'exploratory-unvalidated', 'dates': DATES[:2], 'pixel_size_m': 10,
        'overlay_url': 'observations/water_change_mock.png', 'display_bounds': bounds, 'no_data_area_km2': 0.5,
        'areas': {'common_valid_km2': 110.0, 'before_water_km2': persistent + lost, 'after_water_km2': persistent + new,
                  'persistent_water_km2': persistent, 'new_water_km2': new, 'lost_water_km2': lost, 'net_water_change_km2': new - lost},
        'method': {'threshold_db': -12.5, 'threshold_method': 'MOCK threshold', 'smoothing': 'MOCK'},
        'sensitivity': {'new_water_min_km2': 1.5, 'new_water_max_km2': 2.5, 'excluding_10m_existing_water_edge_km2': 1.8},
        'downloads': {'preview': 'observations/water_change_preview_mock.png', 'before': 'observations/analysis_20240828_mock.tif',
                      'after': 'observations/analysis_20240921_mock.tif', 'classes': 'observations/water_change_classes_mock.tif',
                      'report': 'observations/analysis_report_mock.json'},
        'limitations': ['MOCK DATA: synthetic values for interface development only.'],
    }
    (out / 'analysis_report_mock.json').write_text(json.dumps(report, indent=1))
    manifest = {
        'schema_version': '2.0', 'mode': 'imagery-comparison',
        'event': {'name': 'Alau Dam flood', 'date': '2024-09-10'},
        'aoi': {'name': 'Kalari Abdu', 'center': list(CENTER), 'radius_m': RADIUS, 'bounds': bounds},
        'observations': observations, 'aoi_url': 'observations/aoi.geojson', 'analysis_url': 'observations/analysis_report_mock.json',
        'display': {'crs': 'EPSG:3857', 'width': SIZE, 'height': SIZE, 'stretch': {'min': -25, 'max': -5, 'unit': 'dB (mock)'},
                    'status': 'calibrated-analysis-preview'},
        'limitations': ['MOCK DATA: synthetic images and numbers for interface development. Not RADARSAT-2.'],
        'credit': 'MOCK DATA — synthetic, not RADARSAT-2. For interface development only.',
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    print(f'Wrote synthetic observations to {out}')


if __name__ == '__main__':
    main()
