#!/usr/bin/env python3
"""Rebuild local flood metrics from the preserved CSV and clipped GeoJSON.

Run from any directory: python scripts/analyze.py
Source extraction from the original geodatabase is retained for provenance in
data/source/kalari_analysis.py; that historical extraction is not executed here.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import re
from datetime import datetime
from pathlib import Path

import pyproj
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import GeometryCollection, Point, mapping, shape
from shapely.ops import polygonize, transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE = DATA / "source"
LON, LAT = 13.28467, 11.73678
CRS = "EPSG:32633"
AREA_TOLERANCE_KM2 = 1e-5  # 10 m²; below reporting precision.
fwd = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
back = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform
geod = Geod(ellps="WGS84")


def write_json(name, content):
    (DATA / name).write_text(json.dumps(content, indent=2, allow_nan=False) + "\n")


def write_csv(name, rows):
    with (DATA / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def area(geom):
    return geom.area / 1e6


def geodesic_area(geom):
    if geom.is_empty:
        return 0.0
    # Consistent ring orientation is needed for Geod's signed-area summation.
    geographic = shapely.orient_polygons(transform(back, geom))
    return abs(geod.geometry_area_perimeter(geographic)[0]) / 1e6


def geo_feature(geom, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": None if geom.is_empty else mapping(transform(back, geom)),
    }


def collection(features):
    return {"type": "FeatureCollection", "features": features}


def period_from_layer(layer):
    match = re.fullmatch(r"VIIRS_(\d{8})_(\d{8})_MaximumFloodExtent_NGA", layer)
    if match is None:
        raise ValueError(f"Unexpected period layer: {layer}")
    start, end = (datetime.strptime(value, "%Y%m%d").date() for value in match.groups())
    if start.month == end.month:
        label = f"{start.day}–{end.day} {end.strftime('%b %Y')}"
    else:
        label = f"{start.strftime('%d %b')}–{end.strftime('%d %b %Y')}"
    return {"period_start": start.isoformat(), "period_end": end.isoformat(),
            "period_label": label, "composite_days": (end - start).days + 1}


def main():
    source_rows = list(csv.DictReader((SOURCE / "kalari_flood_summary.csv").open()))
    source_geojson = json.loads((SOURCE / "kalari_flood_5km.geojson").read_text())
    center = transform(fwd, Point(LON, LAT))
    circles = {radius: center.buffer(radius * 1000, quad_segs=128) for radius in (2, 5)}
    zones = {"0–2 km": circles[2], "2–5 km": circles[5].difference(circles[2])}
    checks = []

    def check(name, passed, **details):
        checks.append({"check": name, "passed": bool(passed), **details})

    check("source_summary_has_twelve_unique_period_radius_rows",
          len(source_rows) == 12 and len({(r["layer"], r["radius_km"]) for r in source_rows}) == 12)
    source_lookup = {(r["layer"], int(float(r["radius_km"]))): r for r in source_rows}
    periods = []
    empty_source_periods = []
    for feature in source_geojson["features"]:
        properties = feature["properties"]
        layer = properties["layer"]
        geom = shape(feature["geometry"]) if feature["geometry"] else GeometryCollection()
        check(f"source_geometry_valid:{layer}", geom.is_valid)
        if geom.is_empty:
            empty_source_periods.append(layer)
        projected = transform(fwd, shapely.make_valid(geom))
        periods.append({"layer": layer, **period_from_layer(layer), "geometry": projected})
    periods.sort(key=lambda p: p["period_start"])
    check("six_unique_period_geometries", len(periods) == 6 and len({p["layer"] for p in periods}) == 6)
    check("circles_nested", circles[2].difference(circles[5]).area == 0)
    check("disjoint_zones_reconcile_to_outer_circle",
          abs(sum(area(g) for g in zones.values()) - area(circles[5])) <= AREA_TOLERANCE_KM2
          and zones["0–2 km"].intersection(zones["2–5 km"]).area <= 0.01)

    summaries, zone_rows, extent_features = [], [], []
    max_source_difference = 0.0
    max_geodesic_difference_pct = 0.0
    for period in periods:
        layer, geom = period["layer"], period["geometry"]
        metadata = {key: period[key] for key in ("period_start", "period_end", "period_label", "composite_days")}
        check(f"flood_within_outer_study_circle:{layer}", area(geom.difference(circles[5])) <= AREA_TOLERANCE_KM2)
        per_radius = {}
        for radius in (2, 5):
            # Preserve the outer clipped source geometry exactly; derive inner intersection.
            clipped = geom if radius == 5 else geom.intersection(circles[radius])
            km2 = area(clipped)
            expected = float(source_lookup[(layer, radius)]["mapped_flood_km2"])
            delta = abs(km2 - expected)
            max_source_difference = max(max_source_difference, delta)
            check(f"area_reconciles_to_source_csv:{layer}:{radius}km",
                  delta <= AREA_TOLERANCE_KM2, difference_km2=delta)
            geod_km2 = geodesic_area(clipped)
            geod_difference = 100 * abs(geod_km2 - km2) / km2 if km2 else 0.0
            max_geodesic_difference_pct = max(max_geodesic_difference_pct, geod_difference)
            check(f"ellipsoidal_area_agrees_with_projected:{layer}:{radius}km",
                  geod_difference < 0.2, projected_km2=km2,
                  ellipsoidal_km2=geod_km2, relative_difference_pct=geod_difference)
            source_row = source_lookup[(layer, radius)]
            per_radius[radius] = km2
            row = {
                **metadata, "radius_km": radius, "study_area_km2": area(circles[radius]),
                "mapped_flood_km2": km2, "mapped_flood_ha": km2 * 100,
                "mapped_flood_share_pct": km2 / area(circles[radius]) * 100,
                "cloud_obstructed_km2": float(source_row["cloud_obstructed_km2"])
                    if source_row["cloud_obstructed_km2"] else None,
                "field_validation_code": int(source_row["field_validation"]),
                "field_validation_status": "Not yet field validated",
                "source_sensor_date": source_row["sensor_date"], "source_layer": layer,
            }
            check(f"unvalidated_field_code:{layer}:{radius}km", row["field_validation_code"] == 0)
            check(f"share_reconciles_to_source_csv:{layer}:{radius}km",
                  abs(row["mapped_flood_share_pct"] - float(source_row["percent_buffer_mapped_flood"])) < 0.001)
            summaries.append(row)
        check(f"inner_area_not_greater_than_outer:{layer}", per_radius[2] <= per_radius[5] + AREA_TOLERANCE_KM2)
        for label, zone in zones.items():
            km2 = area(geom.intersection(zone))
            zone_rows.append({**metadata, "distance_zone": label,
                              "zone_area_km2": area(zone), "mapped_flood_km2": km2,
                              "mapped_flood_ha": km2 * 100,
                              "mapped_flood_share_pct": km2 / area(zone) * 100,
                              "share_of_period_flood_pct": km2 / per_radius[5] * 100 if per_radius[5] else None})
        check(f"distance_zone_areas_sum_to_five_km_total:{layer}",
              abs(sum(row["mapped_flood_km2"] for row in zone_rows[-2:]) - per_radius[5]) <= AREA_TOLERANCE_KM2)
        extent_features.append(geo_feature(geom, {**summaries[-1],
                                                 "geometry_status": "no_mapped_polygon" if geom.is_empty else "mapped_polygon"}))

    transitions = []
    for previous, current in zip(periods, periods[1:]):
        before, after = previous["geometry"], current["geometry"]
        common = area(before.intersection(after))
        added = area(after.difference(before))
        removed = area(before.difference(after))
        elapsed = (datetime.fromisoformat(current["period_start"]) - datetime.fromisoformat(previous["period_end"])).days - 1
        row = {"previous_period_start": previous["period_start"], "previous_period_end": previous["period_end"],
               "previous_period_label": previous["period_label"], "current_period_start": current["period_start"],
               "current_period_end": current["period_end"], "current_period_label": current["period_label"],
               "days_without_supplied_composite": elapsed, "previous_mapped_km2": area(before),
               "current_mapped_km2": area(after), "mapped_in_both_km2": common,
               "newly_mapped_km2": added, "no_longer_mapped_km2": removed,
               "net_change_km2": area(after) - area(before),
               "net_change_pct": (area(after) / area(before) - 1) * 100 if area(before) else None,
               "retained_share_of_previous_pct": common / area(before) * 100 if area(before) else None}
        check(f"spatial_transition_balance:{previous['period_end']}:{current['period_end']}",
              abs(common + added - area(after)) <= AREA_TOLERANCE_KM2
              and abs(common + removed - area(before)) <= AREA_TOLERANCE_KM2
              and abs(added - removed - row["net_change_km2"]) <= AREA_TOLERANCE_KM2)
        transitions.append(row)

    all_geometries = [p["geometry"] for p in periods if not p["geometry"].is_empty]
    unique_footprint = unary_union(all_geometries)
    # Polygonize boundaries into disjoint pieces and count containing composites.
    # A count is observation frequency, never elapsed duration or consecutive days.
    pieces_by_count = {count: [] for count in range(1, len(periods) + 1)}
    boundaries = unary_union([g.boundary for g in all_geometries])
    for piece in polygonize(boundaries):
        representative = piece.representative_point()
        count = sum(g.covers(representative) for g in all_geometries)
        if count:
            pieces_by_count[count].append(piece)
    frequency_rows, frequency_features = [], []
    for count, pieces in pieces_by_count.items():
        geom = unary_union(pieces)
        km2 = area(geom)
        frequency_rows.append({"mapped_in_n_periods": count, "total_periods": len(periods),
                               "area_km2": km2, "area_ha": km2 * 100,
                               "share_of_unique_footprint_pct": km2 / area(unique_footprint) * 100})
        if pieces:
            frequency_features.append(geo_feature(geom, frequency_rows[-1]))
    check("frequency_areas_reconcile_to_unique_union",
          abs(sum(r["area_km2"] for r in frequency_rows) - area(unique_footprint)) <= AREA_TOLERANCE_KM2)
    check("frequency_weighted_areas_reconcile_to_sum_of_period_areas",
          abs(sum(r["area_km2"] * r["mapped_in_n_periods"] for r in frequency_rows)
              - sum(area(g) for g in all_geometries)) <= AREA_TOLERANCE_KM2)
    check("unique_union_at_least_each_period_area",
          area(unique_footprint) + AREA_TOLERANCE_KM2 >= max(area(g) for g in all_geometries))

    outer = [row for row in summaries if row["radius_km"] == 5]
    peak = max(outer, key=lambda row: row["mapped_flood_km2"])
    peak_inner = next(row for row in summaries if row["radius_km"] == 2 and row["period_end"] == peak["period_end"])
    late_september = next(row for row in outer if row["period_end"] == "2024-09-30")
    repeated = sum(row["area_km2"] for row in frequency_rows if row["mapped_in_n_periods"] >= 2)
    metrics = {
        "study": {"name": "Kalari Abdu flood footprint study", "location_lon": LON, "location_lat": LAT,
                  "location_type": "approximate village point; not a settlement boundary",
                  "area_crs": CRS, "analysis_radius_km": 5, "study_area_km2": area(circles[5]),
                  "period_count": len(periods), "first_period_start": periods[0]["period_start"],
                  "last_period_end": periods[-1]["period_end"], "composite_days_each": 5},
        "peak": {"period_start": peak["period_start"], "period_end": peak["period_end"],
                 "period_label": peak["period_label"], "mapped_flood_km2": peak["mapped_flood_km2"],
                 "mapped_flood_ha": peak["mapped_flood_ha"], "share_of_study_area_pct": peak["mapped_flood_share_pct"],
                 "within_two_km_km2": peak_inner["mapped_flood_km2"],
                 "between_two_and_five_km_km2": peak["mapped_flood_km2"] - peak_inner["mapped_flood_km2"],
                 "between_two_and_five_km_share_pct": 100 * (1 - peak_inner["mapped_flood_km2"] / peak["mapped_flood_km2"])},
        "change": {"early_september_to_peak_increase_pct": 100 * (peak["mapped_flood_km2"] / outer[0]["mapped_flood_km2"] - 1),
                   "peak_to_late_september_decline_pct": 100 * (1 - late_september["mapped_flood_km2"] / peak["mapped_flood_km2"]),
                   "peak_to_late_september_decline_km2": peak["mapped_flood_km2"] - late_september["mapped_flood_km2"],
                   "late_september_mapped_km2": late_september["mapped_flood_km2"],
                   "november_mapped_km2": outer[-1]["mapped_flood_km2"]},
        "spatial": {"unique_mapped_footprint_km2": area(unique_footprint),
                    "unique_mapped_footprint_ha": area(unique_footprint) * 100,
                    "unique_footprint_share_of_study_area_pct": area(unique_footprint) / area(circles[5]) * 100,
                    "mapped_in_at_least_two_periods_km2": repeated,
                    "mapped_in_at_least_two_periods_share_of_union_pct": repeated / area(unique_footprint) * 100,
                    "maximum_period_count": max(row["mapped_in_n_periods"] for row in frequency_rows if row["area_km2"] > AREA_TOLERANCE_KM2)},
        "interpretation": [
            "Areas describe mapped flood extent inside a 5 km circular study area, not the village administrative area.",
            "Peak means the largest extent among six supplied five-day composites; the exact flood peak date is unknown.",
            "Spatial overlap across composites is repeat detection, not continuous inundation or measured duration.",
            "Newly mapped and no longer mapped compare classifications, not proven onset or drainage times.",
            "Zero mapped area does not demonstrate dry or safe conditions; later-period spatial coverage is not independently verified.",
            "All source flood records are marked not yet field validated. No local people, buildings or loss figures can be inferred.",
        ],
    }
    check("all_numeric_metrics_finite", all(math.isfinite(v) for row in summaries for v in row.values() if isinstance(v, float)))
    manifest = {
        "lineage": "Supplied FL20240902NGA.gdb → prior local extraction → preserved source CSV and 5 km clipped GeoJSON → this analysis.",
        "reproduction_scope": "All packaged derived data are reproducible from the bundled derivative inputs. This script does not reread or independently validate the original geodatabase.",
        "source_files": [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in sorted(SOURCE.iterdir()) if p.is_file()],
        "source_description": "VIIRS MaximumFloodExtent polygons from FL20240902NGA; six five-day periods in September–November 2024.",
        "location_source": "https://mapcarta.com/N5547360846",
        "upstream_report": "https://unosat.org/static/unosat_filesystem/3967/UNOSAT_Preliminary_Assessment_Report_FL20240902NGA_Maiduguri_13Sep2024.pdf",
        "method": {"area_crs": CRS, "geojson_crs": "EPSG:4326 (RFC 7946)",
                   "buffer_quadrant_segments": 128, "empty_geometry": "Converted empty coordinate arrays to null; zero summary rows retained.",
                   "spatial_transitions": "Intersection and directional differences of successive clipped period geometries.",
                   "observation_frequency": "Planar partition of all polygon boundaries; count of composites covering each piece.",
                   "no_count_to_duration_conversion": True},
        "software": {"python": platform.python_version(), "shapely": shapely.__version__, "pyproj": pyproj.__version__},
    }
    validation = {
        "status": "passed" if all(c["passed"] for c in checks) else "failed",
        "scope": "Internal arithmetic, geometry, source-derivative reconciliation and independent ellipsoidal area check. Not field validation or independent source mapping verification.",
        "check_count": len(checks), "passed_count": sum(c["passed"] for c in checks),
        "area_tolerance_km2": AREA_TOLERANCE_KM2,
        "maximum_source_area_difference_km2": max_source_difference,
        "maximum_projected_vs_geodesic_difference_pct": max_geodesic_difference_pct,
        "source_empty_geometry_periods_normalized_to_null": empty_source_periods,
        "checks": checks,
    }
    write_csv("flood_summary.csv", summaries)
    write_csv("distance_zones.csv", zone_rows)
    write_csv("spatial_transitions.csv", transitions)
    write_csv("observation_frequency.csv", frequency_rows)
    write_json("flood_extents.geojson", collection(extent_features))
    write_json("observation_frequency.geojson", collection(frequency_features))
    write_json("study_area.geojson", collection([
        geo_feature(center, {"feature_type": "approximate_locality", "name": "Kalari Abdu"}),
        geo_feature(circles[5], {"feature_type": "study_boundary", "radius_km": 5, "area_km2": area(circles[5])}),
        *[geo_feature(geom, {"feature_type": "distance_zone", "distance_zone": label, "area_km2": area(geom)})
          for label, geom in zones.items()],
    ]))
    write_json("summary_metrics.json", metrics)
    write_json("source_manifest.json", manifest)
    write_json("validation.json", validation)
    print(json.dumps({"validation": validation["status"], "checks": len(checks),
                      "peak_km2": metrics["peak"]["mapped_flood_km2"],
                      **metrics["spatial"]}, indent=2))
    if validation["status"] != "passed":
        raise SystemExit("Data validation failed; see data/validation.json")


if __name__ == "__main__":
    main()
