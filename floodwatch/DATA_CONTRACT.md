# Active contract: real observation previews (schema 2.0)

The active frontend reads `public/observations/manifest.json`, the referenced
PNG images, and `aoi.geojson`. It never falls back to legacy mock data.

Required manifest fields:

- `schema_version: "2.0"`, `mode: "imagery-comparison"`.
- `event`: event name and reference date (`2024-09-10`). This is a timeline
  reference, not an inferred flood-onset date for every pixel.
- `aoi`: `name`, `center` in `[longitude, latitude]` order, `radius_m`, and
  `bounds` in `[west, south, east, north]` order.
- `observations`: baseline and post-event records with `id`, acquisition
  `date`, `role`, `label`, `image_url`, source-product identifier, beam mode,
  polarization, orbit direction, and acquisition timestamp.
- `aoi_url`: GeoJSON Polygon in EPSG:4326 for the 6 km radius study boundary.
- `display`: common output grid and stretch. Status is `terrain-corrected-preview`
  for the current DEM-based export, or `uncalibrated-preview` for legacy GCP
  placement. Both remain radiometrically uncalibrated; the exporter records
  `radiometrically_calibrated: false` and `geometry_method`.
- `limitations` and `credit`: provenance/context, not unsupported accuracy claims.

## Coordinate and display requirements

1. Both PNGs are warped to exactly the same north-up **EPSG:3857** raster grid.
2. Their common map bounds are the geographic coordinates of that grid's
   corners. MapLibre image coordinates are NW, NE, SE, SW.
3. Alpha represents valid display coverage. Transparent/out-of-AOI pixels are
   not dry land and must never enter flood statistics.
4. Both previews use the same original log-raw-power display stretch. These
   are display bytes, not calibrated sigma0 values in dB.
5. Web Mercator map-unit spacing is not the same as ground spacing or sensor
   resolving power. Preview resampling does not add spatial detail.
6. Current placement uses SNAP Range-Doppler terrain correction of original
   intensity with SRTM elevations and EGM96-to-ellipsoid conversion. The AOI
   remains fixed on the ground. Legacy exports use zero-height product GCPs.
   Neither status promises surveyed absolute accuracy or independently verified
   fine registration between dates; changing shoreline positions are not control points.
7. The basemap is contextual. Its imagery date is unrelated to the selected
   RADARSAT-2 date. The circle is an AOI, not a village boundary or flood extent.

`provenance.json` records export validation, source hashes, and the optional
`terrain_processing` record (DEM, software, graph method, source checks, and
corrected output hashes). Current image URLs end in `_tc.png`, avoiding stale
uncorrected image caches. Keep the full
original product directory for future SAR processing; the cropped complex TIFF
is not a complete SNAP product.

## What this stage deliberately does not infer

There is no water mask, change classification, flood-area estimate, building
impact count, continuously observed flood duration, or drying forecast in this
contract. The August baseline is a selected observation, not proof that all
pixels were flood-free. Introduce such products only with a separate, verified
analysis contract and explicit missing-data handling.

---

# Legacy mock/recovery contract (not loaded by the active app)

The following documents the retained prototype pipeline. Its "flood duration"
implementation uses the event-relative day of the last wet observation, not
measured continuous inundation duration. Its default threshold is a prototype
setting and is not validated for our RADARSAT-2 scenes. Raw complex SLC and our
AEQD preview GeoTIFFs are not valid direct inputs to this importer.

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
