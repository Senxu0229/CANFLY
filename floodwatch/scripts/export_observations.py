#!/usr/bin/env python3
"""Export the existing Kalari Abdu display previews for MapLibre.

Requires GDAL's Python bindings and NumPy (available in the forest-gis Conda
environment). Without --terrain-dir, this reprojects the old zero-height
geolocation previews. It does not identify flooding.
With --terrain-dir it displays separately validated SNAP terrain-corrected intensity.
Both modes remain radiometrically uncalibrated.

    python scripts/export_observations.py \
      --dataset-root ~/datasets/hackathon --output-dir public/observations
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from osgeo import gdal, osr


DATES = ("20240828", "20240921")
CENTER = (13.2846742, 11.7367804)
RADIUS = 6000
PREFIX = "kalari_abdu_6km"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def spatial_ref(epsg: int) -> osr.SpatialReference:
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(epsg)
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


def transform_from(dataset: gdal.Dataset, target: osr.SpatialReference):
    source = dataset.GetSpatialRef()
    source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


def projected_extent(dataset: gdal.Dataset, target: osr.SpatialReference):
    """Densify the full preview border so a curved edge is not clipped."""
    transform = transform_from(dataset, target)
    gt = dataset.GetGeoTransform()
    border = []
    for t in np.linspace(0, 1, 257):
        for col, row in ((t * dataset.RasterXSize, 0),
                         (t * dataset.RasterXSize, dataset.RasterYSize),
                         (0, t * dataset.RasterYSize),
                         (dataset.RasterXSize, t * dataset.RasterYSize)):
            x, y = gdal.ApplyGeoTransform(gt, col, row)
            border.append(transform.TransformPoint(x, y)[:2])
    points = np.asarray(border)
    require(bool(np.isfinite(points).all()), "Non-finite projected bounds")
    return (*points.min(axis=0), *points.max(axis=0))


def load_source(root: Path, date: str):
    directory = root / f"{PREFIX}_{date}"
    preview_path = directory / f"{PREFIX}_preview_map.tif"
    info_path = directory / "extraction_info.json"
    aoi_path = directory / f"{PREFIX}_aoi.geojson"
    info = json.loads(info_path.read_text())
    require(info["center"]["longitude"] == CENTER[0]
            and info["center"]["latitude"] == CENTER[1]
            and info["radius_m"] == RADIUS, f"Unexpected AOI for {date}")
    # Resolve by product name under dataset-root, rather than relying on the
    # extraction report's original machine-specific absolute path.
    product_name = Path(info["source_product_xml"]).parent.name
    xml_path = root / product_name / "product.xml"
    xml = ET.parse(xml_path).getroot()

    def xml_value(tag: str):
        node = xml.find(f".//{{*}}{tag}")
        require(node is not None and bool(node.text), f"Missing {tag}: {xml_path}")
        return node.text.strip()

    metadata = {
        "id": date,
        "date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
        "role": "baseline" if date == DATES[0] else "post-event",
        "label": "Before flood" if date == DATES[0] else "After flood",
        "image_url": f"observations/radar_{date}.png",
        "source_product": product_name,
        "beam_mode": xml_value("beamModeMnemonic"),
        "polarization": xml_value("polarizations"),
        "orbit_direction": xml_value("passDirection"),
        "acquisition_utc": xml_value("rawDataStartTime"),
    }
    require(metadata["acquisition_utc"].startswith(metadata["date"]),
            f"Acquisition date mismatch for {date}")
    require(metadata["acquisition_utc"] == info["acquisition_utc"],
            f"Extraction metadata disagrees with product for {date}")
    require((metadata["beam_mode"], metadata["polarization"], metadata["orbit_direction"])
            == ("XF0W2", "HH", "Descending"), f"Unexpected acquisition settings for {date}")
    dataset = gdal.Open(str(preview_path), gdal.GA_ReadOnly)
    require(dataset.RasterCount == 2, f"Expected gray + alpha: {preview_path}")
    for band, interpretation in ((1, gdal.GCI_GrayIndex), (2, gdal.GCI_AlphaBand)):
        raster_band = dataset.GetRasterBand(band)
        require(raster_band.DataType == gdal.GDT_Byte
                and raster_band.GetColorInterpretation() == interpretation,
                f"Unexpected preview bands for {date}")
    require(dataset.GetSpatialRef() is not None, f"Missing preview CRS for {date}")
    aoi = json.loads(aoi_path.read_text())
    properties = aoi["features"][0]["properties"]
    require(properties["center_lon"] == CENTER[0]
            and properties["center_lat"] == CENTER[1]
            and properties["radius_m"] == RADIUS, f"AOI geometry metadata mismatch: {date}")
    paths = [preview_path, info_path, aoi_path, xml_path]
    fingerprints = {str(path.relative_to(root)): sha256(path) for path in paths}
    return dataset, info, metadata, aoi, fingerprints


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def load_terrain(terrain_dir: Path, sources, input_hashes: dict):
    record_path = terrain_dir / "processing_info.json"
    record = json.loads(record_path.read_text())
    require(record["radiometrically_calibrated"] is False
            and record["external_dem_apply_egm"] is True
            and record["manual_shift_applied"] is False,
            "Expected uncalibrated, DEM-based geometry correction")
    input_hashes[str(record_path)] = sha256(record_path)
    for path, digest in record["input_sha256"].items():
        require(sha256(Path(path)) == digest, f"Terrain processing input changed: {path}")
        input_hashes[path] = digest
    products = []
    for source in sources:
        metadata = source[2]
        observation = next(item for item in record["observations"] if item["id"] == metadata["id"])
        require(observation["source_product"] == metadata["source_product"], "Terrain source product mismatch")
        path = terrain_dir / observation["file"]
        require(sha256(path) == observation["sha256"], f"Terrain product hash mismatch: {path}")
        input_hashes[str(path)] = observation["sha256"]
        dataset = gdal.Open(str(path))
        require(dataset.RasterCount == 2
                and dataset.GetSpatialRef().GetAuthorityCode(None) == "32633",
                "Expected terrain-corrected intensity + elevation in UTM 33N")
        intensity, elevation = dataset.ReadAsArray()
        valid = np.isfinite(intensity) & (intensity >= 0) & np.isfinite(elevation) & (elevation != -32768)
        require(valid.mean() > 0.99 and intensity[valid].max() > 0, "Empty/incomplete terrain product")
        # Elevation validity supplies the mask; zero intensity is NOT nodata.
        product = gdal.GetDriverByName("MEM").Create("", dataset.RasterXSize, dataset.RasterYSize, 2, gdal.GDT_Float32)
        product.SetProjection(dataset.GetProjection())
        product.SetGeoTransform(dataset.GetGeoTransform())
        product.GetRasterBand(1).WriteArray(np.where(valid, intensity, 0))
        product.GetRasterBand(1).SetColorInterpretation(gdal.GCI_GrayIndex)
        product.GetRasterBand(2).WriteArray(valid.astype(np.float32) * 255)
        product.GetRasterBand(2).SetColorInterpretation(gdal.GCI_AlphaBand)
        products.append(product)
        metadata["image_url"] = f"observations/radar_{metadata['id']}_tc.png"
    return record, products


def export(dataset_root: Path, output_dir: Path, size: int, terrain_dir: Path | None = None) -> None:
    gdal.UseExceptions()
    osr.UseExceptions()
    require(256 <= size <= 4096, "--size must be between 256 and 4096")
    sources = [load_source(dataset_root, date) for date in DATES]
    first = sources[0]
    require(first[3] == sources[1][3], "The two AOI boundaries differ")
    lower = first[1]["preview_stretch"]["lower_log_raw_power"]
    upper = first[1]["preview_stretch"]["upper_log_raw_power"]
    for dataset, info, *_ in sources:
        require(info["preview_stretch"]["lower_log_raw_power"] == lower
                and info["preview_stretch"]["upper_log_raw_power"] == upper,
                "Input previews have different brightness stretches")
        require(dataset.GetGeoTransform() == first[0].GetGeoTransform()
                and dataset.GetSpatialRef().IsSame(first[0].GetSpatialRef())
                and (dataset.RasterXSize, dataset.RasterYSize)
                == (first[0].RasterXSize, first[0].RasterYSize),
                "Input previews do not share the expected display grid")

    mercator, geographic = spatial_ref(3857), spatial_ref(4326)
    extents = np.array([projected_extent(item[0], mercator) for item in sources])
    west, south = extents[:, :2].min(axis=0)
    east, north = extents[:, 2:].max(axis=0)
    center_x, center_y = (west + east) / 2, (south + north) / 2
    # Square Web Mercator pixels; include the entire transformed source extent.
    span = math.ceil(max(east - west, north - south))
    bounds = [center_x - span / 2, center_y - span / 2,
              center_x + span / 2, center_y + span / 2]
    to_geo = osr.CoordinateTransformation(mercator, geographic)
    sw, ne = to_geo.TransformPoint(*bounds[:2]), to_geo.TransformPoint(*bounds[2:])
    geographic_bounds = [sw[0], sw[1], ne[0], ne[1]]
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    input_hashes = {key: value for item in sources for key, value in item[4].items()}
    terrain_record, terrain_products = None, []
    if terrain_dir:
        terrain_record, terrain_products = load_terrain(terrain_dir, sources, input_hashes)
    # Rasterize the actual geographic study circle onto the shared display grid.
    # This keeps the AOI fixed on the ground when source geolocation changes.
    mask_dataset = gdal.GetDriverByName("MEM").Create("", size, size, 1, gdal.GDT_Byte)
    mask_dataset.SetProjection(mercator.ExportToWkt())
    mask_dataset.SetGeoTransform((bounds[0], span / size, 0, bounds[3], 0, -span / size))
    vector_path = "/vsimem/kalari_export_aoi.geojson"
    gdal.FileFromMemBuffer(vector_path, json.dumps(first[3]).encode())
    try:
        gdal.Rasterize(mask_dataset, vector_path, burnValues=[255])
    finally:
        gdal.Unlink(vector_path)
    aoi_mask = mask_dataset.ReadAsArray()
    validations, transforms, output_alpha = [], [], []
    with tempfile.TemporaryDirectory(prefix=".observations-", dir=output_dir.parent) as temp:
        stage = Path(temp)
        for source_index, (dataset, _, metadata, _, _) in enumerate(sources):
            if terrain_record:
                dataset = terrain_products[source_index]
            warped = gdal.Warp(
                "", dataset, format="MEM", dstSRS=mercator.ExportToWkt(),
                outputBounds=bounds, width=size, height=size,
                resampleAlg="average" if terrain_record else "bilinear", srcAlpha=True, dstAlpha=True,
                outputType=gdal.GDT_Float32 if terrain_record else gdal.GDT_Byte, errorThreshold=0,
                warpOptions=["INIT_DEST=0"],
            )
            require(warped.RasterCount == 2, "Warp lost the alpha band")
            values = warped.ReadAsArray()
            gray, alpha = values
            if terrain_record:
                inside = aoi_mask > 0
                require(bool((np.isfinite(gray[inside]) & (gray[inside] >= 0)
                              & (alpha[inside] >= 254.99)).all()),
                        "Terrain-corrected imagery does not completely cover the study circle")
                gray = np.clip((10 * np.log10(np.maximum(gray, 1)) - lower)
                               / (upper - lower) * 255, 0, 255).astype(np.uint8)
                alpha = aoi_mask.copy()
            require(bool(np.any(alpha == 0)) and bool(np.any(alpha == 255)),
                    "Expected both transparent exterior and valid interior")
            require(bool((alpha[[0, 0, -1, -1], [0, -1, 0, -1]] == 0).all()),
                    "The circular preview must have transparent corners")
            require(alpha[size // 2, size // 2] == 255, "Village center has no data")
            gray[alpha == 0] = 0
            # Produce RGBA explicitly so browser image decoding is unambiguous.
            rgba = gdal.GetDriverByName("MEM").Create("", size, size, 4, gdal.GDT_Byte)
            rgba.SetProjection(mercator.ExportToWkt())
            rgba.SetGeoTransform(warped.GetGeoTransform())
            for index in range(1, 5):
                band = rgba.GetRasterBand(index)
                band.WriteArray(alpha if index == 4 else gray)
                band.SetColorInterpretation((gdal.GCI_RedBand, gdal.GCI_GreenBand,
                                             gdal.GCI_BlueBand, gdal.GCI_AlphaBand)[index - 1])
            output_path = stage / Path(metadata["image_url"]).name
            # The shared projection/bounds live in the manifest. Avoid PAM sidecars.
            with gdal.config_option("GDAL_PAM_ENABLED", "NO"):
                result = gdal.GetDriverByName("PNG").CreateCopy(str(output_path), rgba)
                result = None
            reopened = gdal.Open(str(output_path))
            require(reopened.RasterCount == 4, "Exported PNG is not RGBA")
            require(bool(np.array_equal(reopened.ReadAsArray(), rgba.ReadAsArray())),
                    "PNG decoding changed exported samples")
            reopened = None
            output_alpha.append(alpha)
            transforms.append(warped.GetGeoTransform())
            validations.append({
                "id": metadata["id"], "output_sha256": sha256(output_path),
                "rgba_roundtrip_exact": True, "center_opaque": True,
                "corners_transparent": True,
                "opaque_pixels": int(np.count_nonzero(alpha == 255)),
                "transparent_pixels": int(np.count_nonzero(alpha == 0)),
            })
        require(transforms[0] == transforms[1], "Output map grids differ")
        # Masks can differ if one source has missing samples; never replace either
        # with a synthetic circle just to make the two masks identical.
        masks_equal = bool(np.array_equal(*output_alpha))
        for relative_path, digest in input_hashes.items():
            require(sha256(dataset_root / relative_path) == digest,
                    f"Source changed during export: {relative_path}")

        manifest = {
            "schema_version": "2.0", "mode": "imagery-comparison",
            "event": {"name": "Alau Dam flood", "date": "2024-09-10"},
            "aoi": {"name": "Kalari Abdu", "center": list(CENTER),
                    "radius_m": RADIUS, "bounds": geographic_bounds},
            "observations": [item[2] for item in sources],
            "aoi_url": "observations/aoi.geojson",
            "display": {
                "crs": "EPSG:3857", "width": size, "height": size,
                "stretch": {"min": lower, "max": upper, "unit": "log raw power"},
                "status": "terrain-corrected-preview" if terrain_record else "uncalibrated-preview",
                "radiometrically_calibrated": False,
                "geometry_method": "SNAP Range-Doppler with SRTM elevation" if terrain_record else "Zero-height product geolocation grid",
                "resampling": "5 m terrain grid averaged to display grid" if terrain_record else "bilinear", "map_pixel_size_m": span / size,
            },
            "limitations": [
                "These are display previews of uncalibrated SAR signal; brightness differences are not measurements of flooding or forest loss.",
                "Ground positions are approximate: source previews use product geolocation tiepoints at zero terrain height, without DEM terrain correction or verified image-to-image registration.",
                "Both previews share a display grid and brightness stretch. This does not establish scientific comparability or ground alignment.",
                "The 6 km circle is a study area, not a flood boundary. Transparent pixels are outside the available preview coverage.",
                "Two dates cannot establish inundation duration, peak extent, affected buildings, or recovery forecasts. The baseline may already contain water.",
            ],
            "credit": "RADARSAT-2 source: EODMS R2TF. Preview for project analysis; basemap credits handled separately.",
        }
        if terrain_record:
            manifest["limitations"][1] = "Ground positions use SNAP Range-Doppler terrain correction with SRTM elevations and EGM96-to-ellipsoid height conversion. Residual geolocation errors remain possible; precise absolute accuracy and image-to-image registration have not been independently surveyed."
            manifest["limitations"][2] = "Both dates share terrain-correction settings, a display grid, and a brightness stretch. The radar values remain uncalibrated; this is not a validated flood classification."
            manifest["credit"] += " Terrain elevation: NASA SRTMGL1 via ESA STEP."
        write_json(stage / "aoi.geojson", first[3])
        write_json(stage / "manifest.json", manifest)
        write_json(stage / "provenance.json", {
            "exporter": "scripts/export_observations.py",
            "gdal_version": gdal.VersionInfo("RELEASE_NAME"),
            "input_sha256": input_hashes,
            "output_grid": {"crs": "EPSG:3857", "width": size, "height": size,
                            "bounds": bounds, "geotransform": transforms[0],
                            "geographic_bounds": geographic_bounds},
            "method": ("Original raw intensity terrain-corrected by SNAP using SRTM, averaged from 5 m UTM to common Web Mercator display grid, then original shared log-power stretch and geographic AOI mask applied. No manual shift or radiometric calibration."
                       if terrain_record else "Bilinear reprojection of already stretched gray/alpha AEQD previews; exact coordinate transform; no new radiometric stretch or SAR processing."),
            "terrain_processing": terrain_record,
            "stretch_reference_product": Path(first[1]["preview_stretch"]["reference_slc"]).parent.name,
            "validation": {"same_output_grid": True, "same_brightness_stretch": True,
                           "input_files_unchanged": True, "output_alpha_masks_equal": masks_equal,
                           "observations": validations},
            "limitations": manifest["limitations"],
        })
        # Stage and validate every file before publishing. Replace only known
        # exporter outputs and write the manifest last, keeping unrelated files.
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(stage.iterdir(), key=lambda path: path.name == "manifest.json"):
            os.replace(path, output_dir / path.name)
    print(json.dumps({"output_dir": str(output_dir), "bounds": geographic_bounds,
                      "size": size, "validated": True}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset-root", type=Path, required=True,
                        help="Directory containing complete products and kalari_abdu_6km_YYYYMMDD previews")
    parser.add_argument("--output-dir", type=Path, default=Path("public/observations"))
    parser.add_argument("--size", type=int, default=1200, help="Square PNG dimensions (default: 1200)")
    parser.add_argument("--terrain-dir", type=Path, help="Validated terrain products from terrain_correct_observations.py")
    args = parser.parse_args()
    export(args.dataset_root.expanduser().resolve(), args.output_dir.expanduser().resolve(), args.size,
           args.terrain_dir.expanduser().resolve() if args.terrain_dir else None)


if __name__ == "__main__":
    main()
