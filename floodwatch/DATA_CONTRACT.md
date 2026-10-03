# Data: from the processing server to FloodWatch

There are two layers to this contract.

1. **What the server sends** (GeoTIFFs and optional GeoJSON). You put them in `incoming/` and run the ingest.
2. **What the web app reads** (`public/data/`). The ingest writes it; nobody edits it by hand.

Only derived products leave the server. Raw RADARSAT-2 SLC stays there (EULA).

## 1. What to send (for the processing side)

Put the date in every file name as `YYYYMMDD` or `YYYY-MM-DD`. The ingest sorts files by name keywords:

| File | Name contains | Content | Required |
|---|---|---|---|
| Water per pass | anything else, e.g. `water_20241009.tif` | Water mask (1 = water, 0 = dry), **or** calibrated sigma0 in dB (water = below `db_threshold`, default -18 dB), **or** water probability 0 to 1 | Yes, one per pass |
| Radar image per pass | `sigma0`, `_db`, `backscatter` or `radar` | Calibrated backscatter in dB (or linear) for display | Optional, recommended |
| Permanent water | `perm`, `ref`, `jrc` | 1 = river/lake that is always water | Optional, recommended |
| Land cover | `worldcover`, `crop`, `landcover` | Classes; cropland = 40 (ESA WorldCover) | Optional |
| Rainfall | `rain`, `chirps`, `precip`, `era5` | mm per period, one file per date | Optional |
| Places | any `.geojson` | Polygons in EPSG:4326 with `name`, `type` (`settlement` or `cropland`), `lga` | Optional (else 1 km grid cells) |
| Buildings | `.geojson` with `build` in the name | Points or polygons in EPSG:4326 | Optional |

Raster rules:

- GeoTIFF in **EPSG:4326, EPSG:3857 or WGS 84 UTM** (e.g. EPSG:32633). SNAP terrain correction output works as is. Anything else: `gdalwarp -t_srs EPSG:4326 in.tif out.tif`.
- North up, no rotation. Single band (the first band is used).
- Same water definition for every pass, so the comparison between dates is fair.
- Any size works; the ingest resamples to about 3000 px across (`max_size`). At 5 m input over 15 km that keeps full resolution.

## 2. Running the ingest

```bash
pip install -r scripts/requirements.txt   # numpy, pillow, scipy, tifffile
npm run ingest:init    # scans incoming/, writes ingest.config.json
# open ingest.config.json: check each file landed in the right list, set the event date
npm run ingest         # writes public/data/
```

Config keys worth knowing:

| Key | Default | Meaning |
|---|---|---|
| `event.date` | `2024-09-10` | Day zero for "days since the dam failed" |
| `water_mode` | `auto` | `mask`, `db`, `linear`, `probability`, or `auto` (guesses from the values and prints what it chose) |
| `db_threshold` | `-18` | Water if backscatter is below this (dB), for `db` / `linear` |
| `max_size` | `3000` | Output grid size in px on the long side |
| `bbox` | from the water files | `[west, south, east, north]` to crop |
| `grid_km` | `1` | Cell size when no place polygons are given |
| `aux[].range` | data min/max | Fixed colour range, e.g. `[0, 150]` mm |
| `credit` | | The credit line required by the RADARSAT-2 EULA |

## 3. What the web app reads (`public/data/`, written by the ingest)

`manifest.json` (schema 1.1): `event`, `aoi.bounds`, `passes[] {date, scene_id, days_since_event}`,
`layers.flood_duration` (the VAP), `layers.water` (per pass), `layers.radar` (optional),
`aux_layers[] {id, name, unit, legend, items[{date, url}]}`, `kpis_by_pass[]`, `credit`, `units_source`.

`units.geojson`: one polygon per place with `id, name, type, lga, area_ha, centroid,
water_ha_by_pass[], flooded_days, buildings_total, buildings_in_water_by_pass[],
cropland_ha, cropland_flooded_ha_by_pass[], aux{id: [value per pass]}`.

Images: `flood_duration.png`, `water_<date>.png`, `radar_<date>.webp`, `aux_<id>_<date>.png`, all north-up over `aoi.bounds`.

A place counts as "still flooded" when water covers more than 5% of it (`FLOODED_SHARE` in `src/lib/analysis.ts`).
