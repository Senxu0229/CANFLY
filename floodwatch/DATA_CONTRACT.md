# Active contract: calibrated observations and exploratory changes

The frontend reads `public/observations/manifest.json` (schema `2.0`, mode
`imagery-comparison`), at least two dated PNGs, and an EPSG:4326 AOI polygon. It never
falls back to legacy mock data. IDs and dates must be unique. Current records
identify baseline 2024-08-28 and post-event 2024-09-21, 2024-10-15, 2024-11-08,
all HH/XF0W2/descending. The 2024-09-10 event is a regional
timeline reference, not a per-pixel flood-onset date.

The AOI center is `[13.2846742, 11.7367804]`, radius 6000 m. Bounds are geographic
`[west,south,east,north]` coordinates of the common north-up EPSG:3857 display
grid. MapLibre corners are NW, NE, SE, SW. Both previews and the change overlay
must share its dimensions and bounds. Alpha encodes coverage; PNG values are
for display only. Optional online basemaps are not contemporaneous references.

`display.status` supports:

- `uncalibrated-preview`: legacy zero-height GCP preview.
- `terrain-corrected-preview`: geometry corrected, still uncalibrated.
- `calibrated-analysis-preview`: calibrated sigma0 display, common −25 to −5 dB
  stretch; requires an `analysis_url`.

`analysis_url` references a content-versioned report with schema `1.0` and
status `exploratory-unvalidated`. `dates` contains exactly two distinct observation
IDs in chronological order, a subset of the manifest observations. Its ordered
pair must exactly match the selected left/right IDs before any analysis is
shown. Reversing the pair does not reinterpret its classes or statistics.
Required fields also include
`display_bounds`, `overlay_url`, `areas`, `method`, `sensitivity`,
`no_data_area_km2`, and `downloads` (preview, before, after, classes, report).
The loader verifies finite areas, matching dates/bounds, area identities,
coverage, sensitivity ordering and both radar/overlay image sizes. Missing or
inconsistent analysis produces a visible error, never fallback statistics. A valid
report for a different selected pair stays hidden; the UI shows image comparison
only and disables Changes. All dates use the same display scale and grid.
Switching dates changes layer visibility on existing maps, preserving the camera.
The date selector disallows selecting the same observation on both sides.

Areas are approximate square kilometres from 100 m² UTM 33N analysis pixels:

- before = persistent + lost
- after = persistent + new
- net = new − lost = after − before
- missing and outside-AOI pixels are excluded, never treated as dry

The analysis GeoTIFFs use a shared 10 m grid; three bands hold 10 m linear
sigma0, 30 m box-mean linear sigma0, and its dB conversion. Nodata is −9999.
The Byte change raster uses 0=nodata, 1=neither-date candidate, 2=both-date
candidate, 3=new candidate, 4=lost candidate. A common pooled Otsu threshold (restored to −12.40234375 dB for this pair)
and removal of water components smaller than 9 pixels define this exploratory
classification. `method.threshold_method` and `method.threshold_db` identify
the actual rule. `method.threshold_selection` is null for Otsu; the optional valley method records
histogram parameters and bin-width stability; optional `otsu_reference` contains the previous Otsu rule's
cutoff and areas recomputed on the same inputs. The UI reads these values from
the report. No class means verified water or verified dry land.

Overlay colours: blue=both dates, cyan=new, orange=lost; 0 and 1 are transparent.
These colours describe radar threshold classes only; orange does not establish
water recession. Existing area keys containing `water` are compatibility names,
not semantic ground truth. The Changes view shows this overlay on post-event radar, without a divider.
Gray previews are always separate from the analytical classifications.

Sensitivity varies the thresholds independently by ±1 dB on each date. It is
not a statistical confidence interval. Local reports retain calibration input
hashes, SNAP graphs/logs, analysis raster hashes, largest-patch centroids,
parameters and limitations. Public reports remove private absolute input paths.
The old `provenance.json` belongs to the legacy geometry-only export; the active
analysis report and its local `calibration_info.json` supply current provenance.

The original full complex product remains necessary for calibration/geometry.
No surveyed absolute geolocation or fine registration accuracy is promised.
Smooth soil and shadows can appear water-like, while vegetated/urban flooding
can be missed. No independent same-date ground truth is supplied. The baseline
may already contain water and neither date necessarily represents peak flooding.
There are no building-impact, continuous-duration or drying-forecast claims.

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
