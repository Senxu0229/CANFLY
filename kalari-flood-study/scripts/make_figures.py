#!/usr/bin/env python3
"""Render the repository's static flood-extent figures from the preserved inputs.

Run from any directory: python scripts/make_figures.py
Dependencies: matplotlib, numpy, pyproj, shapely (see requirements.txt).
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re

# Figures use Matplotlib's bundled DejaVu font; avoid a slow platform font scan.
os.environ.setdefault("MPL_IGNORE_SYSTEM_FONTS", "1")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, PathPatch
from matplotlib.path import Path as MplPath
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from shapely.ops import transform


ROOT = Path(__file__).resolve().parents[1]
INK = "#153547"
MUTED = "#586B74"
TEAL = "#146C78"
LIGHT_BLUE = "#A9CED9"
GRID = "#DEE5E6"
PAPER = "#FCFCF9"
VILLAGE_LON = 13.28467
VILLAGE_LAT = 11.73678


def label_for_layer(layer: str) -> str:
    match = re.search(r"VIIRS_(\d{8})_(\d{8})_", layer)
    if match is None:
        raise ValueError(f"Cannot derive observation window from {layer!r}")
    start, end = [datetime.strptime(value, "%Y%m%d") for value in match.groups()]
    if (start.year, start.month) != (end.year, end.month):
        raise ValueError("Update date labels before plotting cross-month windows")
    return f"{start.day}–{end.day} {end:%b} {end.year}"


def load_sources(source_dir: Path):
    with (source_dir / "kalari_flood_summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    grouped: dict[str, dict[float, dict]] = {}
    for row in rows:
        radius = float(row["radius_km"])
        if radius in grouped.setdefault(row["layer"], {}):
            raise ValueError("Duplicate period/radius row")
        grouped[row["layer"]][radius] = row
    layers = sorted(grouped)
    if len(layers) != 6:
        raise ValueError("These figure layouts require the six supplied periods")
    for layer in layers:
        if set(grouped[layer]) != {2.0, 5.0}:
            raise ValueError("Expected nested 2 km and 5 km measurements")

    with (source_dir / "kalari_flood_5km.geojson").open() as stream:
        source_geojson = json.load(stream)
    geometries = {}
    project = Transformer.from_crs(4326, 32633, always_xy=True).transform
    for feature in source_geojson["features"]:
        layer = feature["properties"]["layer"]
        if layer in geometries:
            raise ValueError("Expected exactly one geometry per period")
        geometry = transform(project, shape(feature["geometry"]))
        if not geometry.is_valid:
            raise ValueError(f"Invalid input geometry: {layer}")
        csv_area = float(grouped[layer][5.0]["mapped_flood_km2"])
        if not np.isclose(geometry.area / 1e6, csv_area, atol=1e-6):
            raise ValueError(f"CSV/geometry area mismatch: {layer}")
        geometries[layer] = geometry
    if set(geometries) != set(layers):
        raise ValueError("CSV and GeoJSON periods do not match")
    return layers, grouped, geometries, project(VILLAGE_LON, VILLAGE_LAT)


def save(fig, output: Path, stem: str, description: str):
    fig.savefig(output / f"{stem}.png", dpi=220, facecolor=PAPER,
                metadata={"Description": description})
    fig.savefig(output / f"{stem}.svg", facecolor=PAPER,
                metadata={"Title": description, "Date": None})
    plt.close(fig)
    print(f"Created {stem}.png and {stem}.svg")


def extent_chart(layers, rows, output):
    inner = np.array([float(rows[layer][2.0]["mapped_flood_km2"]) for layer in layers])
    totals = np.array([float(rows[layer][5.0]["mapped_flood_km2"]) for layer in layers])
    outer = totals - inner
    if np.any(outer < -1e-9):
        raise ValueError("An inner radius has more flood area than the outer radius")

    fig, ax = plt.subplots(figsize=(11.8, 6.8), facecolor=PAPER)
    fig.subplots_adjust(left=0.185, right=0.91, top=0.745, bottom=0.20)
    fig.text(0.055, 0.93, "Mapped flood extent near Kalari Abdu", fontsize=21,
             weight="bold", color=INK)
    fig.text(0.055, 0.885, "Six observation windows in 2024 · land within 5 km of the approximate village point",
             fontsize=11.5, color=MUTED)
    legend = [Patch(facecolor=TEAL, label="Within 2 km"),
              Patch(facecolor=LIGHT_BLUE, label="Between 2 and 5 km")]
    fig.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.046, 0.85),
               ncol=2, frameon=False, handlelength=1.2, handleheight=1.05,
               columnspacing=2.4, labelcolor=INK, fontsize=11.2)

    y = np.arange(len(layers))
    ax.set_facecolor(PAPER)
    ax.barh(y, inner, color=TEAL, height=0.54, zorder=3)
    ax.barh(y, outer, left=inner, color=LIGHT_BLUE, height=0.54, zorder=3)
    for index, value in enumerate(totals):
        if value == 0:
            ax.plot([0], [index], "o", ms=5, color=MUTED, clip_on=False, zorder=4)
            ax.text(0.11, index, "0.00  ·  No mapped detection", va="center",
                    fontsize=10.8, color=MUTED)
        else:
            ax.text(value + 0.075, index, f"{value:.2f}", va="center",
                    fontsize=12, color=INK, weight="bold")
    ax.set_yticks(y, [label_for_layer(layer) for layer in layers], fontsize=11.5)
    ax.tick_params(axis="y", length=0, pad=12)
    ax.set_ylim(len(layers) - 0.48, -0.52)
    ax.set_xlim(0, 5.15)
    ax.set_xticks(np.arange(0, 6, 1))
    ax.set_xlabel("Mapped flood area (km²)", labelpad=11, fontsize=11.5, color=INK)
    ax.tick_params(axis="x", colors=MUTED, labelsize=10.5, length=0, pad=7)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#AFBFC4")
    ax.spines["left"].set_linewidth(0.8)
    fig.text(0.055, 0.087,
             "Source: UNOSAT VIIRS maximum-flood-extent layers; local clipping in EPSG:32633.",
             fontsize=9.3, color=MUTED)
    fig.text(0.055, 0.057,
             "Bands are disjoint and sum to the 5 km total. Periods are separate composites; not yet field validated.",
             fontsize=9.3, color=MUTED)
    fig.text(0.055, 0.027, "No mapped detection does not establish dry conditions or complete detection.",
             fontsize=9.3, color=MUTED)
    save(fig, output, "flood_extent",
         "Mapped flood area by observation window in 2024, within 2 km and between 2–5 km of Kalari Abdu")


def geometry_patches(geometry, origin):
    """Return compound paths with correctly oriented holes, in local UTM kilometres."""
    if geometry.is_empty:
        return
    parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    for part in parts:
        part = orient(part, sign=1.0)
        vertices, codes = [], []
        for ring in [part.exterior, *part.interiors]:
            coordinates = (np.asarray(ring.coords) - np.asarray(origin)) / 1000
            vertices.extend(coordinates)
            codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(coordinates) - 2)
                         + [MplPath.CLOSEPOLY])
        yield PathPatch(MplPath(vertices, codes), facecolor=TEAL, edgecolor=TEAL,
                        linewidth=0.30, zorder=3)


def footprint_maps(layers, rows, geometries, origin, output):
    fig, axes = plt.subplots(2, 3, figsize=(12.0, 9.7), facecolor=PAPER)
    fig.subplots_adjust(left=0.035, right=0.965, top=0.835, bottom=0.16,
                        wspace=0.10, hspace=0.23)
    fig.text(0.045, 0.954, "Where flooding was mapped", fontsize=22,
             weight="bold", color=INK)
    fig.text(0.045, 0.916,
             "Kalari Abdu surroundings · six 2024 composites · identical scale in every panel",
             fontsize=11.8, color=MUTED)
    handles = [Patch(facecolor=TEAL, label="Mapped flood footprint"),
               Line2D([0], [0], color=MUTED, lw=1, label="5 km study circle"),
               Line2D([0], [0], color=MUTED, lw=0.9, ls=(0, (4, 3)), label="2 km reference"),
               Line2D([0], [0], color=INK, marker="+", ls="None", markersize=8,
                      markeredgewidth=1.8, label="Approximate village point")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.036, 0.894),
               ncol=4, frameon=False, columnspacing=1.45, handlelength=1.35,
               handletextpad=0.55, fontsize=9.5, labelcolor=INK)

    for index, (ax, layer) in enumerate(zip(axes.flat, layers)):
        area = float(rows[layer][5.0]["mapped_flood_km2"])
        ax.set_facecolor(PAPER)
        ax.add_patch(Circle((0, 0), 5, facecolor="white", edgecolor="none", zorder=0))
        # Centre coordinates originate from a longitude/latitude point transformed
        # into UTM 33N; no artificial river line or basemap is drawn.
        for patch in geometry_patches(geometries[layer], origin):
            ax.add_patch(patch)
        ax.add_patch(Circle((0, 0), 5, fill=False, edgecolor="#8B9FA7",
                            linewidth=0.9, zorder=4))
        ax.add_patch(Circle((0, 0), 2, fill=False, edgecolor="#7D939C",
                            linewidth=0.8, linestyle=(0, (4, 3)), zorder=4))
        ax.plot(0, 0, marker="+", markersize=8, markeredgewidth=1.8, color=INK, zorder=5)
        ax.set_xlim(-5.5, 5.5)
        ax.set_ylim(-5.5, 5.5)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
        ax.text(0, 1.035, label_for_layer(layer), transform=ax.transAxes,
                ha="left", va="bottom", fontsize=11.2, color=INK, weight="bold")
        ax.text(1, 1.035, f"{area:.2f} km²", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=11.2, color=INK)
        if geometries[layer].is_empty:
            ax.text(0, -2.65, "No mapped detection", ha="center", va="center",
                    fontsize=10.5, color=MUTED)

    # One common scale bar and grid-north arrow serve every equal-scale panel.
    first = axes[0, 0]
    first.annotate("", xy=(-4.9, 4.85), xytext=(-4.9, 3.5),
                   arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2))
    first.text(-4.9, 5.04, "N", ha="center", va="bottom", fontsize=9, color=INK)
    last = axes[1, 2]
    last.plot([2.7, 4.7], [-5.23, -5.23], color=INK, lw=2.0, clip_on=False)
    last.plot([2.7, 2.7], [-5.07, -5.39], color=INK, lw=1.0, clip_on=False)
    last.plot([4.7, 4.7], [-5.07, -5.39], color=INK, lw=1.0, clip_on=False)
    last.text(3.7, -5.60, "2 km", color=INK, fontsize=9.5, ha="center", va="top")
    fig.text(0.045, 0.094,
             "Flood footprints only; no basemap. WGS84 / UTM zone 33N (EPSG:32633); arrow shows grid north.",
             fontsize=9.4, color=MUTED)
    fig.text(0.045, 0.067,
             "Centre: 11.73678° N, 13.28467° E (approximate locality point). Circles are study areas, not village boundaries.",
             fontsize=9.4, color=MUTED)
    fig.text(0.045, 0.040,
             "Source: UNOSAT VIIRS layers, clipped to 5 km. Not yet field validated; no detection does not establish dry conditions.",
             fontsize=9.4, color=MUTED)
    save(fig, output, "flood_footprints",
         "Six equal-scale maps of UNOSAT flood footprints around the approximate Kalari Abdu village point")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data" / "source")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": MUTED,
                         "ytick.color": INK, "svg.fonttype": "none",
                         "svg.hashsalt": "kalari-flood-study-2024"})
    layers, rows, geometries, origin = load_sources(args.source_dir)
    extent_chart(layers, rows, args.output_dir)
    footprint_maps(layers, rows, geometries, origin, args.output_dir)


if __name__ == "__main__":
    main()
