# FloodWatch — Kalari Abdu

A local, real-data viewer for RADARSAT-2 observations of the same **6 km radius**
area around Kalari Abdu, Nigeria. The active app offers **28 August, 21 September, 15 October and 8 November 2024**.
Choose any two distinct dates with **Left image** and **Right image**, use the
three adjacent-date shortcuts, or **Swap sides**. Maps keep the same camera,
brightness scale and slider position when dates change. **Left only**,
**Compare** and **Right only** refer to screen position, not disaster timing.

The current analysis export shows **calibrated sigma0 HH**, SRTM terrain
correction, a shared 10 m analysis grid, and a 30 m linear-power box mean.
The **Changes** view displays radar threshold classes: cyan for newly low
returns, blue for low returns on both dates, and orange for leaving the low-return
class. Orange does not establish water recession. Areas are computed from the masked UTM
GeoTIFFs, never from PNG brightness or Web Mercator pixels.

These are **not independently validated flood boundaries**. Fine positional
errors, smooth soil and radar shadow can produce false detections; water under
vegetation or in built-up areas may be missed. The app reports threshold
sensitivity, not accuracy. It does not infer affected buildings, duration or
recovery forecasts.
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

## Legacy geometry-only previews (also initializes the web manifest)

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

Two observation dates alone do not measure continuous flood duration or support
a reliable drying forecast. Current water candidates still require independent validation.

## Generate calibrated analysis and candidate water changes

Prerequisites: full original products, existing crop metadata/AOI, external DEM,
SNAP 14, and the web manifest initialized by `export_observations.py` above.
The geometry-only scripts are retained for reproducibility; running that legacy
export again replaces the active analysis manifest with geometry-only previews.
Run the analysis exporter last to restore the calibrated view.

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate forest-gis
cd ~/projects/hackathon/CANFLY/floodwatch
# GDAL and NumPy are already installed in this environment.
python -m pip install scipy matplotlib pillow

python scripts/calibrate_observations.py \
  --dataset-root ~/datasets/hackathon \
  --dem ~/datasets/hackathon/alignment_aux/srtm_kalari_abdu_egm96.tif \
  --gpt ~/projects/.tools/esa-snap-14/bin/gpt \
  --output-dir ~/datasets/hackathon/kalari_abdu_analysis

python scripts/analyze_water.py \
  --dataset-root ~/datasets/hackathon \
  --analysis-dir ~/datasets/hackathon/kalari_abdu_analysis

python scripts/export_water_analysis.py \
  --analysis-dir ~/datasets/hackathon/kalari_abdu_analysis \
  --web-dir public/observations

python -m unittest discover -s scripts -p 'test_water_analysis.py'
conda activate floodwatch-dev
npm run build
npm run test:e2e
```

The first command applies the product's sigma calibration LUT through SNAP to
both original I/Q components, then geocodes in linear power. It writes a
buffered 5 m sigma0/elevation product. No additional terrain radiometric
normalization, thermal-noise subtraction, or empirical image translation is
applied. This is not a claim that every possible SAR correction has been done.

The analysis script averages linear power onto one aligned EPSG:32633 10 m
grid, applies a 3 × 3 linear mean, and masks the exact geographic 6 km AOI and
common coverage. Its three-band `analysis_YYYYMMDD_10m.tif` files contain:

1. Calibrated sigma0 linear power, 10 m area average.
2. The same quantity after a 3 × 3 box mean (30 m footprint).
3. Band 2 converted using `10 log10(sigma0)`, in dB.

All bands use -9999 for nodata. Grid spacing is not independent spatial
resolution. Mean filtering reduces speckle but can blur shorelines. The
`water_change_classes.tif` values are 0=nodata, 1=neither date below threshold,
2=both dates, 3=new candidate, 4=lost candidate. Neither-date pixels are not
confirmed dry land. The default mask again uses the shared pooled two-date Otsu
threshold, restored at the user's request (−12.40234375 dB for this pair).
`--threshold-method valley` retains the experimental histogram-valley method as
an explicit option; `--threshold-db` permits an explicit exploratory cutoff.
The report records the actual method. Water components smaller than 9 pixels (900 m²) are removed with
8-neighbour connectivity before comparing dates; change fragments can be
smaller. Thresholding is an exploratory brightness partition, not a trained
or validated land-cover classifier.

The report records all parameters, hashes, area accounting, largest new patch
centroids, and nine independent ±1 dB threshold combinations. This parameter
range is **not a confidence interval** and excludes other sources of error.
A 10 m buffer around baseline water provides an additional shoreline sensitivity
check; it does not establish registration accuracy. A stricter candidate core
uses before ≥ threshold+1 dB and after < threshold−1 dB, with small patches
removed. The original products remain unchanged.

For this pair, the restored **−12.40234375 dB** cutoff gives approximately
**1.72 km² possible new water**, **6.28 km² orange areas to check** and
−4.56 km² net *class-area* change within 113.10 km² common coverage.
Before/after candidate areas are 24.60/20.04 km². Independent ±1 dB threshold
sensitivity for new candidates is 1.16–2.65 km². These are radar classes, not
confirmed water extent or flood damage.

The experimental −15.0 dB run is archived under
`kalari_abdu_analysis/history/valley_before_otsu_restore_*/`; the original Otsu
outputs are retained in `history/otsu_before_histogram_valley_revision/`.
The active website uses the restored Otsu result.

The exporter verifies analysis hashes and grid/date/AOI consistency, uses
content-versioned image URLs, and publishes the manifest last. The frontend
checks area identities and missing artifacts rather than showing made-up
fallback statistics. All real derived data and downloadable files remain in
the ignored local `public/observations/` directory.

Methods: [ESA SNAP calibration documentation](https://step.esa.int/main/wp-content/help/versions/10.0.0/snap-toolboxes/eu.esa.microwavetbx.sar.op.calibration.ui/operators/CalibrationOp.html)
, [UN-SPIDER minimum-histogram flood mapping](https://un-spider.github.io/flood-mapping-python/)
and [UN-SPIDER radar flood mapping](https://un-spider.org/advisory-support/recommended-practices/recommended-practice-radar-based-flood-mapping).
These support the method family; neither validates these local results.

### Interpretation correction after inspecting orange areas

The area values above describe the chosen radar threshold classes, **not measured
water extent or recession**. The initial narrative of net water-area decrease
is withdrawn pending independent validation. Leaving a low-return class can
also reflect crops, vegetation, soil or other scattering changes.

A diagnostic of the existing orange class found that 65.5% of its pixels had
baseline values within 2 dB below the −12.402 dB threshold. Applying the same
−14 dB threshold to both dates gives 3.09 km² orange rather than 6.28 km²;
−16 dB gives 1.90 km². These were sensitivity examples during review; the histogram-valley
experiment also remained unvalidated and has since been reverted. They do not prove that the orange pixels are farmland either.
The diagnostic is saved beside the rasters as
`threshold_interpretation_diagnostic.json`. The previous class raster is archived and original
calibrated data are retained; colours are relabelled by their measured signal
meaning in the UI, report and preview. Existing JSON keys containing `water`
are retained for compatibility and denote threshold classes only.

Validation should sample both dark water-like areas and suspected fields using
independent, appropriately dated observations. An agricultural land-cover label
must not automatically exclude flooding: farmland can also be inundated.

## Additional observations: 15 October and 8 November 2024

The additional-date preparation reuses the same SNAP calibration and terrain
correction graph, the existing full 6 km AOI mask, and the 10 m UTM analysis grid.
It generates one local `kalari_abdu_6km_YYYYMMDD/` directory per date and refuses
to overwrite existing output directories:

```bash
conda activate forest-gis
python scripts/prepare_additional_observations.py \
  --dataset-root ~/datasets/hackathon \
  --reference-dir ~/datasets/hackathon/kalari_abdu_analysis \
  --display-manifest public/observations/manifest.json \
  --dem ~/datasets/hackathon/alignment_aux/srtm_kalari_abdu_egm96.tif \
  --gpt ~/projects/.tools/esa-snap-14/bin/gpt \
  --dates 20241015 20241108
```

Each output directory contains `kalari_abdu_6km_sigma0_10m.tif` (the same three
analysis bands described above), `kalari_abdu_6km_preview.png`, the georeferenced
RGBA display TIFF, the geographic AOI, a processing record, and a SNAP graph/log.
The PNG uses the current common EPSG:3857 display grid and −25 to −5 dB stretch.
The analysis GeoTIFF retains only valid pixels in the geographic 6 km circle;
outside pixels are nodata. It contains calibrated intensity, not raw complex
I/Q. Complete original products are preserved. Temporary buffered geocoding
products are discarded after validation. Executing the saved SNAP graph alone
recreates that intermediate; this preparation script also performs the final
masking and display steps.

This step does not classify water or alter the active two-date web manifest.

## Add prepared dates to the comparison

After generating the additional-date crops, append their verified previews:

```bash
conda activate forest-gis
python scripts/append_observations.py \
  --dataset-root ~/datasets/hackathon \
  --web-dir public/observations \
  --dates 20241015 20241108
conda activate floodwatch-dev
npm run build
npm run test:e2e
```

The append step checks processed-file hashes, common AOI mask, grid, image size,
brightness range and acquisition settings. It copies content-versioned local
PNGs and provenance, then replaces the manifest last. Repeating it updates the
same IDs without duplicates. It does not run additional water classification.
`export_water_analysis.py` now preserves dates outside its analysis pair.

Analysis is specific to an **ordered pair**: the current report applies only to
28 Aug on the left and 21 Sep on the right. Other pairs, including the reversed
pair, show **Image comparison only**, hide area statistics and disable Changes.
Selecting a pair returns to Compare; View analysed pair restores the supported
order. This prevents the August–September estimates from being attributed to
October or November. The four-date timeline is an observation reference;
automatic playback and interpolated imagery are not part of this version.


## Local RAG map assistant

**Ask AI** opens the local Qwen3.5-4B chat panel with the currently selected dates,
verified project documents and clickable citations. The model is reused from the
server cache; no model download is needed. A small Python API runs on port 8787,
proxied through Vite. Generation and embedding settings are separate; the initial
small bilingual knowledge base uses local TF-IDF vectors, with an optional
separate semantic embedding API configuration.

See [CHAT_ASSISTANT.md](docs/CHAT_ASSISTANT.md) for startup, model paths/settings,
knowledge-base updates, grounding rules and verification commands.
