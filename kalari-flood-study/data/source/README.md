# Ngadda River near Kalari Abdu — downloaded-data findings

Location used: 11.73678 N, 13.28467 E, the OpenStreetMap-derived village point shown at https://mapcarta.com/N5547360846. This is an approximate locality point, not a village boundary or surveyed river position.

The supplied UNOSAT_Maiduguri_Flood_Assessment_2024-09-13.pdf identifies increased water along the Ngadda River (page 5) and inundated agricultural areas close to Kalari Abdu and Ngawo Fato Bulamari as of 11 September 2024 (page 12). The local image is GeoEye-1, acquired 11 September 2024 at 10:01 UTC, listed resolution 50 cm. Report publication date is 13 September 2024.

## Local calculations

Read the six VIIRS MaximumFloodExtent layers in FL20240902NGA.gdb, repair geometries where necessary, and intersect them with circles of radius 2 km and 5 km around the locality point. Areas were calculated in WGS84 / UTM zone 33N (EPSG:32633); buffer curves use 128 segments per quadrant. CSV retains unrounded calculations; interpret results at approximately two decimal places in square kilometres. The 5 km circle covers 78.54 square kilometres. The GeoJSON contains clipped flood polygons for that circle, one feature per period. Ellipsoidal areas were independently checked and agree with projected results within approximately 0.1%.

Within 5 km, the largest mapped flood extent among the supplied periods was 4.62 km2 (about 462 hectares) on 14–18 September, up from 2.89 km2 on 5–9 September (about 60%). By 26–30 September it was 1.37 km2, about 70% below the observed maximum. These are differences between period composites, not measurements of continuously flooded land or discharge.

Matching cloud-obstruction polygons intersected neither circle in all six periods. This does not establish complete detection or ground validation. All flood records have Field_Validation=0, decoded by the geodatabase table as Not yet field validated. No mapped flood polygon does not establish absence of water or safe conditions. These layers do not provide river depth, flow rate, water quality, river centreline, or crop-loss amounts. The 5 km circle may include other water bodies; results cannot be attributed entirely to the river or agricultural land. The September analysis-extent layer is national; separate later-period analysis-extent layers are absent, limiting independent coverage verification.

## State context

borno_state_context.csv extracts Borno's row from the supplied population-exposure XLSX. Its figures apply to Borno State, not Kalari Abdu. Column headers span September–November despite the sheet being named September 2024. The October header says 27–31 October, while the filename says 27–30 October; use explicit headers and geodatabase layer periods. Do not sum population-exposure estimates across periods because people may recur.

Files: kalari_flood_summary.csv (two radii, six periods); kalari_flood_5km.geojson (QGIS-ready polygons); borno_state_context.csv; layers.json; kalari_analysis.py (reproduction script, requires pyogrio, shapely, pyproj).
