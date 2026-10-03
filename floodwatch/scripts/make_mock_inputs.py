"""
Write SYNTHETIC input files that look like the real ones, then the normal ingest
turns them into public/data/. Nothing here is real data.

  incoming_mock/water_<date>.tif         water mask per pass (UTM 33N, 1 = water)
  incoming_mock/sigma0_db_<date>.tif     radar backscatter in dB per pass
  incoming_mock/perm_water.tif           permanent river
  incoming_mock/worldcover.tif           land cover (40 = cropland)
  incoming_mock/rain_<date>.tif          rainfall in mm per dekad (EPSG:4326, coarse)
  incoming_mock/places.geojson           settlements and cropland blocks
  incoming_mock/buildings.geojson        building points

Run:  python3 scripts/make_mock_inputs.py   (then it runs the ingest for you)
"""
import json
import math
import os
import random
import subprocess
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
from geotiff_lite import lonlat_to_xy, write_geotiff  # noqa: E402

random.seed(7)
np.random.seed(7)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INC = os.path.join(ROOT, 'incoming_mock')
os.makedirs(INC, exist_ok=True)

EPSG = 32633  # WGS 84 / UTM 33N, what SNAP terrain correction often outputs here
W, S, E, N = 13.05, 11.70, 13.33, 11.93
PASSES = ['2024-10-09', '2024-10-15', '2024-10-22', '2024-10-26', '2024-11-19', '2024-11-26', '2024-12-02', '2025-01-06']
RES = 25.0  # metres per pixel (the real product is 5 m; smaller here to keep the repo light)

# UTM grid covering the bbox
xs, ys = lonlat_to_xy(np.array([W, E, W, E]), np.array([S, S, N, N]), EPSG)
X0, X1, Y0, Y1 = xs.min(), xs.max(), ys.min(), ys.max()
NX, NY = int((X1 - X0) / RES), int((Y1 - Y0) / RES)
gx = X0 + (np.arange(NX) + 0.5) * RES
gy = Y1 - (np.arange(NY) + 0.5) * RES
XX, YY = np.meshgrid(gx, gy)


def to_xy(lon, lat):
    x, y = lonlat_to_xy(np.array([lon]), np.array([lat]), EPSG)
    return float(x[0]), float(y[0])


# synthetic valley from the dam (south-east) through the city (north-west)
river = [to_xy(13.30, 11.72), to_xy(13.22, 11.79), to_xy(13.16, 11.83), to_xy(13.10, 11.87), to_xy(13.05, 11.91)]
dist = np.full((NY, NX), 1e12)
for (x0, y0), (x1, y1) in zip(river, river[1:]):
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((XX - x0) * dx + (YY - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    dist = np.minimum(dist, np.hypot(XX - (x0 + t * dx), YY - (y0 + t * dy)))
noise = ndimage.gaussian_filter(np.random.rand(NY, NX), 18)
noise = (noise - noise.min()) / (noise.max() - noise.min())
elev = dist / 1500.0 + noise * 2.2
for lon, lat, r in [(13.20, 11.80, 1000), (13.13, 11.86, 850), (13.25, 11.76, 750), (13.17, 11.89, 650)]:
    cx, cy = to_xy(lon, lat)
    elev -= 1.6 * np.exp(-((XX - cx) ** 2 + (YY - cy) ** 2) / (2 * r * r))
perm = dist < 100
levels = [2.55, 2.35, 2.12, 2.02, 1.45, 1.30, 1.18, 0.55]

write_geotiff(os.path.join(INC, 'perm_water.tif'), perm.astype(np.uint8), EPSG, X0, Y1, RES, RES)
for d, lv in zip(PASSES, levels):
    wet = ndimage.binary_opening((elev < lv) | perm, iterations=1)
    tag = d.replace('-', '')
    write_geotiff(os.path.join(INC, f'water_{tag}.tif'), wet.astype(np.uint8), EPSG, X0, Y1, RES, RES)
    db = np.where(wet, -22.0, -8.0) + np.random.normal(0, 2.2, wet.shape)  # speckle-like noise
    db += ndimage.gaussian_filter(np.random.rand(NY, NX), 40) * 4 - 2
    write_geotiff(os.path.join(INC, f'sigma0_db_{tag}.tif'), db.astype(np.float32), EPSG, X0, Y1, RES, RES, nodata=-9999)

# land cover: cropland (40) in patches along the valley, else grass (30) / built (50)
lc = np.full((NY, NX), 30, np.uint8)
lc[(ndimage.gaussian_filter(np.random.rand(NY, NX), 25) > 0.5) & (dist < 6000)] = 40
cxy = to_xy(13.15, 11.84)
lc[np.hypot(XX - cxy[0], YY - cxy[1]) < 3500] = 50
write_geotiff(os.path.join(INC, 'worldcover.tif'), lc, EPSG, X0, Y1, RES, RES)

# rainfall: coarse lon/lat grid (like CHIRPS, 0.05 deg), heavy early, tapering into the dry season
RW, RS_, RE, RN = 12.9, 11.55, 13.5, 12.1
rnx, rny = int((RE - RW) / 0.05), int((RN - RS_) / 0.05)
for d, base in [('2024-09-01', 140), ('2024-09-11', 95), ('2024-09-21', 60), ('2024-10-01', 35), ('2024-10-11', 18),
                ('2024-10-21', 6), ('2024-11-01', 1), ('2024-12-01', 0), ('2025-01-01', 0)]:
    field = base * (0.7 + 0.6 * np.random.rand(rny, rnx))
    write_geotiff(os.path.join(INC, f"rain_{d.replace('-', '')}.tif"), field.astype(np.float32), 4326, RW, RN, 0.05, 0.05)

# places and buildings
lgas = ['Maiduguri (mock LGA)', 'Jere (mock LGA)', 'Konduga (mock LGA)']
feats, bfeats = [], []
lon_of = lambda x: W + (x - X0) / (X1 - X0) * (E - W)  # noqa: E731  (approximation is fine for mock shapes)
lat_of = lambda y: S + (y - Y0) / (Y1 - Y0) * (N - S)  # noqa: E731


def near_valley():
    while True:
        x, y = random.uniform(X0 + 1000, X1 - 1000), random.uniform(Y0 + 1000, Y1 - 1000)
        i, j = int((Y1 - y) / RES), int((x - X0) / RES)
        if 0 <= i < NY and 0 <= j < NX and dist[i, j] < random.choice([750, 1500, 2250, 3500]):
            return x, y


for k in range(24):
    kind = 'settlement' if k < 14 else 'cropland'
    cx, cy = near_valley()
    r = random.uniform(350, 650) if kind == 'settlement' else random.uniform(450, 850)
    sides = 9 if kind == 'settlement' else 6
    ring = []
    for a in range(sides):
        ang = 2 * math.pi * a / sides + random.uniform(-0.15, 0.15)
        rr = r * (1 + random.uniform(-0.25, 0.25))
        ring.append([round(lon_of(cx + rr * math.cos(ang)), 6), round(lat_of(cy + rr * math.sin(ang)), 6)])
    ring.append(ring[0])
    name = f'Settlement {k + 1:02d}' if kind == 'settlement' else f'Cropland block {chr(65 + k - 14)}'
    feats.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]},
                  'properties': {'id': f'{"S" if kind == "settlement" else "C"}{k + 1:02d}', 'name': name, 'type': kind,
                                 'lga': random.choice(lgas)}})
    nb = int(r * r / 1500) if kind == 'settlement' else random.randint(0, 6)
    for _ in range(nb):
        a, rr = random.uniform(0, 2 * math.pi), r * math.sqrt(random.random()) * 0.8
        bfeats.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [
            round(lon_of(cx + rr * math.cos(a)), 6), round(lat_of(cy + rr * math.sin(a)), 6)]}, 'properties': {}})
with open(os.path.join(INC, 'places.geojson'), 'w') as fh:
    json.dump({'type': 'FeatureCollection', 'features': feats}, fh)
with open(os.path.join(INC, 'buildings.geojson'), 'w') as fh:
    json.dump({'type': 'FeatureCollection', 'features': bfeats}, fh)
print(f'Wrote synthetic inputs to incoming_mock/ ({NX} x {NY} px at {RES:.0f} m, EPSG:{EPSG})')

# draft a config from the folder, mark it as mock, then build public/data
cfg_path = os.path.join(ROOT, 'scripts', 'mock.config.json')
ingest = os.path.join(ROOT, 'scripts', 'ingest.py')
subprocess.run([sys.executable, ingest, '--init', '--incoming', INC, '--config', cfg_path], check=True)
with open(cfg_path) as fh:
    cfg = json.load(fh)
cfg['mock'] = True
cfg['max_size'] = 1400
cfg['aux'][0]['range'] = [0, 150]
cfg['aux'][0]['note'] = 'Mock rainfall in mm per 10 days (shaped like CHIRPS dekads)'
cfg['credit'] = 'MOCK DATA. Replace with the credit line required by the RADARSAT-2 EULA.'
with open(cfg_path, 'w') as fh:
    json.dump(cfg, fh, indent=2)
subprocess.run([sys.executable, ingest, '--config', cfg_path], check=True)
