# How possible water is detected

FAQ: How is possible new water detected? How is water area calculated? What threshold identifies water?

For the analysed 2024-08-28 → 2024-09-21 pair, ESA SNAP 14.0.0 read the
complete HH SLC products, calibrated linear sigma0 using the product sigma LUT,
and performed Range-Doppler terrain correction with SRTM elevation and EGM96
conversion. Calibration output spacing is 5 m in EPSG:32633.
Terrain radiometric normalization was not applied. Calibration alone does not
identify water.

The analysis uses EPSG:32633, a 10 m grid. It area-averages
linear power, then applies a 3 × 3 mean (30 m footprint), then converts to dB using
10 × log10(sigma0). It does not measure PNG brightness. Each date's candidate mask
is smoothed sigma0 HH strictly below the common threshold -12.40234375 dB
(approximately -12.4 dB), selected by pooled two-date Otsu.
Connected components with fewer than 9 pixels
are removed separately from each date using 8-neighbour connectivity.
Nine 10 m pixels are 900 m², or 0.09 hectares. Missing/outside-AOI pixels are excluded.

In short: calibrate, terrain-correct, resample to one grid, smooth linear power,
convert to dB and classify with the shared threshold. Below -12.40234375 dB only means
possible water. Statistics come from the analysis TIFFs, not the web PNG previews.
Possible new water means the earlier date did not meet the candidate rule and the
later date did, with small patches removed from both masks; not every new dark
pixel is confirmed flooding. Each analysis pixel is 10 × 10 = 100 m²; the 10 m grid
does not mean an independent 10 m spatial resolution.
Area = retained class pixel count × 100 m² / 1,000,000, expressed in km².
This is approximate ground area from UTM grid pixels, not a validated flood extent.

## Verified local sources

- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
- `scripts/analyze_water.py`; SHA256 `546dc6b0a2691bd003428e8771afe20b43c14dee9324acc837196f76b1b55633`.
- `/home/grad/zqin/datasets/hackathon/kalari_abdu_analysis/calibration_info.json`; SHA256 `a9449cecca94e159051c5ed84e57996c6449dead32c9dbfd74fc65e3a07431d6`.
