# Data dictionary

The analysis concerns **mapped flood extent near an approximate Kalari Abdu village point**, not a mapped village boundary. The six periods are five-day VIIRS composites in 2024. All areas are calculated in WGS 84 / UTM zone 33N (EPSG:32633). GeoJSON coordinates are longitude, latitude in WGS 84 (EPSG:4326).

Full precision is retained in the files for reproducibility. Display area results to about two decimal places in km²; additional digits are computational precision, not measurement accuracy. A hectare is 0.01 km².

## Files at a glance

| File | Row or feature represents | Intended use |
|---|---|---|
| [`flood_summary.csv`](../data/flood_summary.csv) | One period × one radius; 12 rows | Compare total mapped flood area within 2 km or 5 km |
| [`distance_zones.csv`](../data/distance_zones.csv) | One period × one disjoint distance zone; 12 rows | Compare the inner 0–2 km zone with the outer 2–5 km zone |
| [`spatial_transitions.csv`](../data/spatial_transitions.csv) | One pair of successive supplied periods; 5 rows | Measure overlap, newly mapped area and area no longer mapped |
| [`observation_frequency.csv`](../data/observation_frequency.csv) | One observation count, from 1 to 6 | Quantify land mapped in exactly that many composites |
| [`flood_extents.geojson`](../data/flood_extents.geojson) | One clipped flood geometry per period; 6 features | Map period-specific flood extent |
| [`observation_frequency.geojson`](../data/observation_frequency.geojson) | One geometry per nonzero observation-count category | Map repeat detections |
| [`study_area.geojson`](../data/study_area.geojson) | Locality point, 5 km boundary, or disjoint zone; 4 features | Locate the analysis and its denominators |
| [`summary_metrics.json`](../data/summary_metrics.json) | Selected report statistics and interpretation notes | Reuse headline findings without copying rounded chart labels |
| [`source_manifest.json`](../data/source_manifest.json) | Source lineage, SHA-256 hashes and software metadata | Identify the exact bundled inputs and reconstruction method |
| [`validation.json`](../data/validation.json) | Named data and geometry checks | Inspect the scope and result of computational verification |

## Period and quality fields

These fields occur in the summary tables or feature properties.

| Field | Meaning |
|---|---|
| `period_start`, `period_end` | Inclusive date bounds parsed from the original geodatabase layer name, in `YYYY-MM-DD` form |
| `period_label` | Human-readable version of those date bounds |
| `composite_days` | Inclusive period length; 5 for all six supplied composites |
| `source_layer` | Original VIIRS MaximumFloodExtent layer identifier |
| `source_sensor_date` | Original CSV date attribute, retained as metadata; it is the endpoint for these composites, not evidence that the full extent was observed on a single day |
| `cloud_obstructed_km2` | Area of the matching source cloud-obstruction polygons inside the selected radius; zero in the supplied local extraction, which does not establish complete detection |
| `field_validation_code` | Original geodatabase code; 0 means not yet field validated |
| `field_validation_status` | Decoded label, `Not yet field validated` |

## Flood summary

| Field | Units and definition |
|---|---|
| `radius_km` | 2 or 5 km from the approximate locality point |
| `study_area_km2` | Planar area of that circle; approximately 12.57 or 78.54 km² |
| `mapped_flood_km2` | Polygon area classified as flooded within the selected circle |
| `mapped_flood_ha` | `mapped_flood_km2 × 100` |
| `mapped_flood_share_pct` | `mapped_flood_km2 ÷ study_area_km2 × 100` |

**Do not add the two radius rows together:** the 2 km circle is already inside the 5 km circle. Do not interpret the percentage as the fraction of the village or population affected.

## Disjoint distance zones

| Field | Units and definition |
|---|---|
| `distance_zone` | `0–2 km` circle or `2–5 km` ring |
| `zone_area_km2` | Area of the zone, approximately 12.57 or 65.97 km² |
| `mapped_flood_km2`, `mapped_flood_ha` | Mapped flood area inside this disjoint zone |
| `mapped_flood_share_pct` | Mapped flood area as a percentage of this zone's area |
| `share_of_period_flood_pct` | This zone's contribution to all mapped flood area inside 5 km during the same period; blank when the denominator is zero |

The two zone areas can be added **within a period** to recover the 5 km total. Zone percentages have different denominators and must not be added.

## Spatial transitions

Each row compares the full 5 km geometries for a previous and current composite.

| Field | Meaning |
|---|---|
| `previous_period_*`, `current_period_*` | Dates and labels for the compared composites |
| `days_without_supplied_composite` | Calendar days between these composite windows for which this six-period input set contains no composite; not proof that no satellite observations exist elsewhere |
| `previous_mapped_km2`, `current_mapped_km2` | Total mapped area in each composite |
| `mapped_in_both_km2` | Spatial intersection of the two mapped extents |
| `newly_mapped_km2` | Area in the current extent that is absent from the previous extent |
| `no_longer_mapped_km2` | Area in the previous extent that is absent from the current extent |
| `net_change_km2` | Current total minus previous total; also newly mapped minus no longer mapped |
| `net_change_pct` | Net change divided by previous area × 100; blank if previous area is zero |
| `retained_share_of_previous_pct` | Shared area divided by previous area × 100; blank if previous area is zero |

“Newly mapped” and “no longer mapped” describe changes in satellite classifications. They do not establish exact dates of flood onset or drainage. Periods have unequal gaps and do not support daily rates of change.

## Observation frequency

| Field | Meaning |
|---|---|
| `mapped_in_n_periods` | Number of supplied composites containing each spatial piece, from 1 to 6 |
| `total_periods` | Number of supplied composites, including the zero-detection October period; 6 |
| `area_km2`, `area_ha` | Unique area mapped in **exactly** this many composites |
| `share_of_unique_footprint_pct` | This category's share of the spatial union of all six extents |

Categories are disjoint, so their areas sum to the unique footprint. Areas mapped in two or more periods can be summed to measure repeat detection. **Neither the count nor count × five days measures flood duration.** The unique union was not necessarily flooded simultaneously.

## GeoJSON handling

`flood_extents.geojson` retains the October record with `geometry: null`, `mapped_flood_km2: 0`, and `geometry_status: no_mapped_polygon`. Other features have `geometry_status: mapped_polygon`. This replaces the source's empty polygon coordinate array with a portable null geometry without changing the numerical result. A null geometry here means **no mapped polygon in the supplied extraction**, not proven dry ground or a missing CSV row.

`study_area.geojson` includes overlapping reference geometry: the 5 km boundary and its two disjoint component zones. Filter by `feature_type` (`approximate_locality`, `study_boundary`, `distance_zone`) when displaying or calculating with it. Do not sum every polygon feature.

## Source preservation and verification

`data/source/` preserves the earlier clipped GeoJSON, radius summary, extraction script, layer inventory and source notes without editing them. `source_manifest.json` records their SHA-256 hashes and describes the lineage. The historical extraction script documents the earlier conversion from the supplied geodatabase; the packaged `scripts/analyze.py` rebuilds downstream metrics from those preserved derivatives. The optional raw-geodatabase workflow is documented separately in the repository methods.

The checks cover geometry validity, radius nesting, reconciliation to the original summary, disjoint zone totals, transition balances, union/frequency identities, finite values, and an independent ellipsoidal area calculation. Passing these checks confirms computational consistency within this scope; it does not independently validate satellite classification, field conditions, or later-period analysis coverage.
