# Methods, sources and interpretation

## Scope

The study measures mapped flood extent around Kalari Abdu, near the Ngadda River in Borno State, Nigeria. It uses six five-day composites from 5–9 September through 9–13 November 2024. It is a retrospective analysis, not a live flood warning or a damage assessment. Report prepared 3 October 2026.

The centre is longitude **13.28467**, latitude **11.73678**, an approximate locality point from [Mapcarta's OpenStreetMap-derived Kalari Abdu record](https://mapcarta.com/N5547360846), which identifies OSM node 5547360846. No village boundary is supplied. Analytical circles have radii of 2 km and 5 km; results depend on this location and chosen scope.

## Source chain

1. **Downloaded geodatabase:** `FL20240902NGA_gdb.zip`, extracted as `FL20240902NGA.gdb`. Six `VIIRS_*_MaximumFloodExtent_NGA` layers supply flood geometry; the corresponding `CloudObstruction_NGA` layers supply obstruction geometry. The original archive is retained in the user's workspace and is not bundled in this package.
2. **First-stage extraction:** `scripts/extract_geodatabase.py` produces the original CSV/GeoJSON derivatives preserved under `data/source/`. An optional full rerun from the downloaded GDB was checked against these files.
3. **Cleaned and extended analysis:** `scripts/analyze.py` reads the preserved source derivatives, standardizes periods and units, calculates disjoint zones, compares geometry, and writes the package's reviewed datasets.
4. **Context report:** [UNOSAT preliminary flood assessment, 13 September 2024](https://unosat.org/static/unosat_filesystem/3967/UNOSAT_Preliminary_Assessment_Report_FL20240902NGA_Maiduguri_13Sep2024.pdf), supplied locally as `UNOSAT_Maiduguri_Flood_Assessment_2024-09-13.pdf`. Page 5 identifies increased water along the Ngadda near Kalari Abdu in GeoEye-1 imagery acquired 11 September at 10:01 UTC. This is separate corroborating context, not the source of the computed VIIRS footprints. Its 50 cm image resolution does not apply to our derived flood layers.
5. **Optional state context:** the supplied UNOSAT population-exposure workbook contains state-level estimates. The earlier Borno extraction is not bundled because it is not used in this local report. The preserved historical `data/source/README.md` describes the original workspace and references that unbundled file and the earlier layer inventory. These figures cannot estimate local population impacts. October headers say 27–31 October despite 27–30 in the workbook filename; explicit headers and layer dates control.

Source file hashes are in `data/source_manifest.json` where provided by the analysis script, and raw input fingerprints in `docs/raw_source_hashes.json`. Source branding and ownership are retained; this is an independent derivative analysis, not an official UNOSAT publication. No new license is asserted over third-party inputs; consult their source terms before redistribution or reuse. The original commercial satellite imagery is not included.

## Calculations

- Coordinate transformation: WGS84 longitude/latitude to **EPSG:32633**, WGS84 / UTM zone 33N, with longitude first.
- Circle approximation: 128 segments per quadrant. Areas are about 12.57 km² and 78.54 km².
- Mapped extent: area of the intersection of flood polygons with a study circle. All calculations retain floating precision; the report rounds km² to two decimals.
- Disjoint distance bands: inner 0–2 km circle and outer 2–5 km ring. The ring is the 5 km circle minus the 2 km circle. These two bands can be added; the nested circle totals cannot.
- Spatial transitions for earlier footprint A and later footprint B: shared = intersection(A,B); newly mapped = B minus A; no longer mapped = A minus B. Earlier area equals shared plus no-longer-mapped; later area equals shared plus newly mapped.
- Unique footprint: union of all six period geometries. It counts each location once, regardless of how many times it appeared, and does not indicate simultaneous inundation.
- Observation frequency: number of period footprints covering each spatial fragment. It is not a count of flood events or days underwater. Multiple dates may describe the same flood event.
- Period change: `(later − earlier) / earlier × 100`. Percentage change from zero is undefined and stored as null/blank, not infinity or an arbitrary percentage.
- The source October empty polygon is normalized to GeoJSON `geometry: null` with zero mapped area. Null geometry here represents no mapped flood polygon; coverage remains separately uncertain.

## Validation

The calculation pipeline checks unique period/radius rows, valid geometries, source area reconciliation, nested circles, mutually exclusive zones, transition balances, observation-frequency reconciliation and ellipsoidal area comparison. The output `data/validation.json` records the results and scope. Projected and independently calculated ellipsoidal areas differ by less than 0.01% for the supplied 5 km footprints. This is an arithmetic/geometric check, not field validation or proof of the source classification's accuracy.

## Limits that affect interpretation

All source flood records have `Field_Validation = 0`: **not yet field validated**. No supplied cloud-obstruction polygons intersect either circle, but this does not guarantee complete detection. The GDB contains a September national analysis extent, with separate later-period extents absent; later spatial coverage cannot be independently confirmed from these outputs.

The composites span five days and there are gaps of up to 26 days between supplied windows. A zero or a disappearance from the map does not establish dry conditions. Repeated detection does not establish uninterrupted inundation. Differences can reflect both actual water changes and detection/classification differences.

These polygons provide no water depth, flow speed, river centreline, population, building damage or financial-loss measurement. The study circle may include water away from the river. Study boundaries, mapping scale and the approximate locality position limit conclusions about individual buildings and small sites. The largest observed footprint is not necessarily the true event maximum.
