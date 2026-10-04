#!/usr/bin/env python3
"""Geocode the original RADARSAT-2 products with SNAP, then subset the AOI.

Geometry only: no calibration, speckle filter, flood classification, or manual
image shift. The external DEM must contain EGM96 orthometric heights in metres.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from osgeo import gdal, osr

from export_observations import DATES, CENTER, require, sha256

REGION = 'POLYGON ((13.19 11.64, 13.38 11.64, 13.38 11.84, 13.19 11.84, 13.19 11.64))'


def make_graph(source: Path, dem: Path, target: Path) -> ET.ElementTree:
    graph = ET.Element('graph', id='KalariAbduTerrainCorrection')
    ET.SubElement(graph, 'version').text = '1.0'

    def node(name, operator, source_ref, parameters):
        element = ET.SubElement(graph, 'node', id=name)
        ET.SubElement(element, 'operator').text = operator
        if source_ref:
            ET.SubElement(ET.SubElement(element, 'sources'), 'sourceProduct', refid=source_ref)
        params = ET.SubElement(element, 'parameters')
        for key, value in parameters.items():
            ET.SubElement(params, key).text = str(value)

    node('read', 'Read', None, {'file': source})
    # Keep ORIGINAL range/timing metadata for geocoding. In SNAP 14, subsetting
    # this decreasing-range RS2 SLC before TC produced an impossible near range
    # (894795 m versus the original 912404 m), then an empty output. The lazy
    # graph below geocodes only tiles requested by the downstream map subset.
    node('terrain', 'Terrain-Correction', 'read', {
        'sourceBands': 'Intensity_HH', 'demName': 'External DEM',
        'externalDEMFile': dem, 'externalDEMNoDataValue': -32768,
        'externalDEMApplyEGM': 'true',
        'demResamplingMethod': 'BILINEAR_INTERPOLATION',
        'imgResamplingMethod': 'BILINEAR_INTERPOLATION',
        'pixelSpacingInMeter': 5.0, 'mapProjection': 'EPSG:32633',
        'alignToStandardGrid': 'true', 'nodataValueAtSea': 'false',
        'saveDEM': 'true', 'saveSelectedSourceBand': 'true',
        'applyRadiometricNormalization': 'false',
    })
    node('subset', 'Subset', 'terrain', {'geoRegion': REGION, 'copyMetadata': 'true'})
    node('write', 'Write', 'subset', {'file': target, 'formatName': 'GeoTIFF'})
    ET.indent(graph)
    return ET.ElementTree(graph)


def validate(path: Path) -> dict:
    dataset = gdal.Open(str(path))
    require(dataset is not None and dataset.RasterCount == 2, 'Expected intensity + elevation')
    require(dataset.GetSpatialRef().GetAuthorityCode(None) == '32633', 'Unexpected output CRS')
    gt = dataset.GetGeoTransform()
    require(gt[1] == 5 and gt[5] == -5 and gt[2] == gt[4] == 0, 'Expected north-up 5 m grid')
    intensity, elevation = dataset.ReadAsArray()
    valid = np.isfinite(intensity) & np.isfinite(elevation) & (elevation != -32768)
    require(float(valid.mean()) > 0.99 and float(intensity[valid].max()) > 0,
            'Terrain correction produced insufficient valid data; do not export')
    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)
    geographic.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target = dataset.GetSpatialRef()
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    x, y, _ = osr.CoordinateTransformation(geographic, target).TransformPoint(*CENTER)
    column, row = gdal.ApplyGeoTransform(gdal.InvGeoTransform(gt), x, y)
    require(0 <= column < dataset.RasterXSize and 0 <= row < dataset.RasterYSize,
            'Village center lies outside output')
    require(bool(valid[int(row), int(column)]), 'Village center has no valid corrected data')
    return {'size': [dataset.RasterXSize, dataset.RasterYSize],
            'geotransform': gt, 'valid_fraction': float(valid.mean()),
            'center_valid': True, 'intensity_max': float(intensity[valid].max()),
            'elevation_ellipsoid_min_max_m': [float(elevation[valid].min()), float(elevation[valid].max())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--dem', type=Path, required=True, help='EPSG:4326 DEM, EGM96 heights, nodata -32768')
    parser.add_argument('--gpt', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root, dem, gpt, output = [p.expanduser().resolve() for p in
                              (args.dataset_root, args.dem, args.gpt, args.output_dir)]
    gdal.UseExceptions()
    osr.UseExceptions()
    dem_dataset = gdal.Open(str(dem))
    require(dem_dataset.GetSpatialRef().GetAuthorityCode(None) == '4326', 'DEM must use EPSG:4326')
    require(dem_dataset.GetRasterBand(1).GetNoDataValue() == -32768, 'Unexpected DEM nodata')
    output.parent.mkdir(parents=True, exist_ok=True)
    input_hashes = {str(dem): sha256(dem)}
    record = {'software': 'ESA SNAP 14.0.0 / Microwave Toolbox',
              'method': 'Range-Doppler Terrain-Correction on original product, followed by map subset',
              'dem_file': str(dem), 'dem_vertical_datum': 'EGM96',
              'external_dem_apply_egm': True, 'output_crs': 'EPSG:32633',
              'output_spacing_m': 5, 'radiometrically_calibrated': False,
              'manual_shift_applied': False, 'speckle_filtered': False,
              'reference': 'https://step.esa.int/main/wp-content/help/versions/9.0.0/snap-toolboxes/org.esa.s1tbx.s1tbx.op.sar.processing.ui/operators/RangeDopplerGeocodingOp.html',
              'observations': []}
    with tempfile.TemporaryDirectory(prefix='.terrain-', dir=output.parent) as temporary:
        stage = Path(temporary)
        for date in DATES:
            info = json.loads((root / f'kalari_abdu_6km_{date}' / 'extraction_info.json').read_text())
            source = root / Path(info['source_product_xml']).parent.name / 'product.xml'
            input_hashes[str(source)] = sha256(source)
            result = stage / f'radar_{date}_tc.tif'
            graph = stage / f'terrain_{date}.xml'
            make_graph(source, dem, result).write(graph, encoding='utf-8', xml_declaration=True)
            log = stage / f'terrain_{date}.log'
            print(f'Terrain correcting {date} from original product...', flush=True)
            with log.open('w') as handle:
                process = subprocess.run([str(gpt), str(graph), '-c', '2G', '-q', '4',
                                          '-J-Xmx8G', '-J-Djava.awt.headless=true'],
                                         stdout=handle, stderr=subprocess.STDOUT)
            if process.returncode:
                raise RuntimeError(log.read_text()[-8000:])
            checks = validate(result)
            record['observations'].append({'id': date, 'file': result.name,
                                           'source_product': source.parent.name,
                                           'sha256': sha256(result), 'validation': checks})
            # Save a rerunnable graph whose output points at the final location.
            make_graph(source, dem, output / result.name).write(graph, encoding='utf-8', xml_declaration=True)
            print(f'{date}: valid fraction {checks["valid_fraction"]:.4f}, village covered', flush=True)
        for path, digest in input_hashes.items():
            require(sha256(Path(path)) == digest, f'Processing input changed: {path}')
        record['input_sha256'] = input_hashes
        (stage / 'processing_info.json').write_text(json.dumps(record, indent=2) + '\n')
        output.mkdir(parents=True, exist_ok=True)
        for path in sorted(stage.iterdir(), key=lambda p: p.name == 'processing_info.json'):
            os.replace(path, output / path.name)
    print(f'Validated terrain products: {output}', flush=True)


if __name__ == '__main__':
    main()
