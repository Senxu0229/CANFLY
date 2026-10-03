# Kalari Abdu · Flood footprint study

**Ngadda River vicinity, Borno State, Nigeria | September–November 2024**

A reproducible analysis of how mapped flooding changed around Kalari Abdu, using six UNOSAT VIIRS observation periods. The package includes a short impact report, geographic data and exportable figures.

[Read the short report →](REPORT.md) · [Explore the data](docs/DATA_DICTIONARY.md) · [Methods and sources](docs/METHODS.md)

![Flood extent near Kalari Abdu](figures/flood_extent.png)

| Finding | Result |
| :--- | ---: |
| Largest observed footprint within 5 km | **4.62 km²**, 14–18 September |
| Decline from that maximum to late September | **70.3%** |
| Unique area mapped across all six periods | **6.68 km²** |
| Share of the maximum footprint in the 2–5 km ring | **97.0%** |

These figures describe **mapped inundation**, not casualties, property damage, or financial loss. The combined footprint was not flooded all at once. Source flood classifications are not yet field validated.

## What's inside

```text
REPORT.md                         Short report with figures and citations
figures/                          High-resolution PNG and editable SVG exports
data/flood_summary.csv            Two radii × six observation periods
data/distance_zones.csv           Disjoint 0–2 km and 2–5 km bands
data/spatial_transitions.csv      Shared, newly mapped and no-longer-mapped areas
data/observation_frequency.csv    Area by number of observation periods
data/*.geojson                   Flood footprints, zones and observation frequency
data/source/                     Preserved extraction inputs
data/summary_metrics.json        Report metrics at full calculation precision
data/validation.json             Arithmetic and geometry check results
docs/                            Methods, data dictionary and source fingerprints
scripts/                         Reproducible extraction, analysis and plotting
```

CSV and GeoJSON use explicit units, source periods and readable field names. GeoJSON coordinates use WGS84 longitude/latitude; area calculations use UTM zone 33N. Import the GeoJSON files into QGIS for geographic exploration.

## Reproduce the data and figures

Tested with Python 3.12. Run these commands from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/analyze.py
python scripts/make_figures.py
```

On Windows, activate with `.venv\Scripts\activate`. The source derivatives needed for this workflow are bundled; no download or API key is needed after installing dependencies. These commands update data and figures. Review and update the written report separately if the inputs change.

For the optional first-stage extraction, obtain and unzip the original `FL20240902NGA_gdb.zip`, then run:

```bash
python scripts/extract_geodatabase.py --gdb /path/to/FL20240902NGA.gdb --output data/reextracted
```

The original GDB archive is not included. The bundled raw-source fingerprints identify the exact downloaded inputs. The extraction rerun was compared against all preserved CSV rows and GeoJSON content; the extended analysis also passed 85 internal geometry/arithmetic checks. Neither check establishes ground truth.

## Share on GitHub

Upload this study as `reports/kalari-flood-study/` in [CANFLY](https://github.com/Senxu0229/CANFLY), keeping its relative paths. `REPORT.md` is the main document; `README.md` is the study overview. Both display their figures directly. This placement preserves the existing repository README and `floodwatch` application. Retain the methods, data dictionary and source attribution with the data. This package has not been uploaded or published.

## Sources and interpretation

Derived from the downloaded UNOSAT flood geodatabase and contextualized with the [UNOSAT 13 September assessment](https://unosat.org/static/unosat_filesystem/3967/UNOSAT_Preliminary_Assessment_Report_FL20240902NGA_Maiduguri_13Sep2024.pdf). Kalari Abdu's approximate position comes from an [OpenStreetMap-derived locality record](https://mapcarta.com/N5547360846).

This is an independent analysis, not an official UNOSAT product. Third-party source data retains its original ownership and terms; no additional license is asserted over it. The original satellite imagery is not redistributed. Details and important interpretation limits are in [METHODS.md](docs/METHODS.md).

## Privacy review

The prepared upload files were reviewed for credentials, private keys, personal paths, identifiers, records about individuals, and image metadata. No such sensitive content was detected. The optional local browser app and Finder metadata are excluded. Public village coordinates and flood geometry are intentionally retained. See [the review scope](docs/PRIVACY_REVIEW.md).
