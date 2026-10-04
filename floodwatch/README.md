# FloodWatch — Kalari Abdu

A local, real-data viewer for RADARSAT-2 observations of the same **6 km radius**
area around Kalari Abdu, Nigeria. The active app compares **28 August 2024**
(baseline) and **21 September 2024** (post-event), with a village marker, AOI
boundary, synchronized maps, and an accessible before/after slider.

The two previews share one display grid and brightness range. They show
**uncalibrated radar intensity with SRTM-based terrain correction**, not a
validated flood classification. Fine positional errors may remain; no surveyed
absolute accuracy is claimed. The app does not display flood-area estimates, affected
building counts, recovery priorities, flood duration, or drying forecasts.
The timeline uses 10 September 2024 as a regional event reference, following
[UNICEF’s September situation report](https://www.unicef.org/media/162556/file/NigeriaSitRep%28MaiduguriFloodResponse%29September2024.pdf.pdf).
It does not establish the exact flood onset in the village.
The optional street/satellite basemaps provide location context, not imagery
from the selected observation date. The default plain background works offline.

## Run on the lab server

The environments below have been prepared on `damlr-w08`:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate floodwatch-dev
cd ~/projects/hackathon/CANFLY/floodwatch
npm ci
npm run dev -- --host 127.0.0.1
```

From a terminal on your own computer, keep this SSH tunnel running:

```bash
ssh -N -L 5173:127.0.0.1:5173 zqin@damlr-w08
```

Then open **http://localhost:5173** in your computer's browser. If you already
use an SSH alias or jump host to reach the lab, use that same connection target.
VS Code Remote SSH port forwarding can also forward port 5173.

On another machine, install Node.js 22+ and run `npm ci`. A fresh checkout also
needs the real preview export described next. The app reports missing data
instead of substituting mock observations.

## Generate the real map previews

Run with Python, NumPy, and GDAL (`forest-gis`). The current workflow also uses
ESA SNAP 14, installed locally at `~/projects/.tools/esa-snap-14`. First generate
terrain-corrected intensity from the **complete original products**:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate forest-gis
cd ~/projects/hackathon/CANFLY/floodwatch
python scripts/terrain_correct_observations.py \
  --dataset-root ~/datasets/hackathon \
  --dem ~/datasets/hackathon/alignment_aux/srtm_kalari_abdu_egm96.tif \
  --gpt ~/projects/.tools/esa-snap-14/bin/gpt \
  --output-dir ~/datasets/hackathon/kalari_abdu_terrain_corrected

python scripts/export_observations.py \
  --dataset-root ~/datasets/hackathon \
  --terrain-dir ~/datasets/hackathon/kalari_abdu_terrain_corrected \
  --output-dir public/observations
```

The existing `kalari_abdu_6km_20240828` and `kalari_abdu_6km_20240921`
directories supply the AOI, source product references, and original common
brightness range. The complete original product directories must remain under
`--dataset-root` for SNAP to read the orbit, timing and complex measurements.

The local DEM is a crop of [SRTMGL1 N11E013](https://step.esa.int/auxdata/dem/SRTMGL1/N11E013.SRTMGL1.hgt.zip),
in EPSG:4326, EGM96 orthometric metres, with nodata -32768. SNAP converts these
heights to the ellipsoid and performs Range-Doppler terrain correction. It writes
5 m UTM 33N intensity/elevation grids; this spacing is not a claim of sensor
resolution. Geocoding precedes subsetting to preserve original range metadata.
In this SNAP version, subsetting the decreasing-range SLC first yielded invalid
range metadata and empty terrain-correction output.

The exporter verifies recorded source/output hashes, averages corrected intensity
onto the common EPSG:3857 web grid, applies the existing log-power brightness
range, and masks the actual geographic 6 km circle. Zero intensity remains valid;
alpha encodes coverage. It does **not** calibrate backscatter, filter speckle,
classify water, or apply an empirical image shift. The processing records and
SNAP graphs are retained alongside the corrected TIFFs.

Omitting `--terrain-dir` deliberately regenerates the older zero-height GCP
previews; their manifest/UI identify terrain correction as pending. The previous
web export is archived at
`~/datasets/hackathon/kalari_abdu_before_terrain_correction_web/`.

The original SAR products and the original cropped datasets are not changed.
Generated files in `public/observations/` are local and ignored by Git. Review
data-sharing terms before publishing any real derived imagery.

## Validate and build

```bash
conda activate floodwatch-dev
npm run build
npx playwright install chromium --only-shell   # once per machine
npm run test:e2e
```

The end-to-end tests run against the built app and exercise actual exported
images, dates, comparison controls, mobile layout, and missing-data behavior.
Export the real observations before running the image integration tests.
On this server, Chromium uses `alsa-lib` from `floodwatch-dev`; the test
configuration adds the active Conda library directory for the browser only.
A production build is written to `dist/`; no deployment is performed.

## Code and data flow

| Responsibility | Location |
|---|---|
| Active frontend | `src/App.tsx` and real comparison components |
| Original-product terrain correction | `scripts/terrain_correct_observations.py` |
| Display export | `scripts/export_observations.py` |
| Real manifest, PNGs, AOI and provenance | `public/observations/` |
| Data formats and limitations | `DATA_CONTRACT.md` |

The earlier recovery dashboard modules, `scripts/ingest.py`, and mock
`public/data/` files remain available for reference. They are **not** the
active app's data source. `npm run mock-data` regenerates legacy mock data and
does not supply real observations or enable scientific statistics.

A later analysis stage can add calibrated backscatter, validated water masks,
and consistently defined area statistics. Two observation dates alone do not
measure continuous flood duration or support a reliable drying forecast.
