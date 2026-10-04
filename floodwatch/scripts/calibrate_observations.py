#!/usr/bin/env python3
"""Calibrate complete RS2 SLC products to linear sigma0, then terrain correct.

Keeps original range metadata until geocoding. Source imagery is never changed.
Run analyze_water.py next to create a common masked analysis grid.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from osgeo import gdal
from export_observations import DATES, sha256, require
from terrain_correct_observations import make_graph as geometry_graph, validate


def make_graph(source, dem, target):
    tree = geometry_graph(source, dem, target)
    graph = tree.getroot()
    graph.set('id', 'KalariAbduCalibratedSigma0')
    calibration = ET.Element('node', id='calibration')
    ET.SubElement(calibration, 'operator').text = 'Calibration'
    ET.SubElement(ET.SubElement(calibration, 'sources'), 'sourceProduct', refid='read')
    params = ET.SubElement(calibration, 'parameters')
    for key, value in {'selectedPolarisations': 'HH', 'outputSigmaBand': 'true',
                       'outputImageInComplex': 'false', 'outputImageScaleInDb': 'false'}.items():
        ET.SubElement(params, key).text = value
    graph.insert(2, calibration)
    terrain = graph.find("node[@id='terrain']")
    terrain.find('sources/sourceProduct').set('refid', 'calibration')
    terrain.find('parameters/sourceBands').text = 'Sigma0_HH'
    ET.indent(graph)
    return tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['dataset-root', 'dem', 'gpt', 'output-dir']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root, dem, gpt, output = [p.expanduser().resolve() for p in
        (args.dataset_root, args.dem, args.gpt, args.output_dir)]
    gdal.UseExceptions()
    output.mkdir(parents=True, exist_ok=True)
    record = {'software': 'ESA SNAP 14.0.0', 'quantity': 'linear sigma0 HH',
              'radiometrically_calibrated': True,
              'method': 'Read complete SLC -> Calibration (product sigma LUT) -> Range-Doppler Terrain-Correction -> map subset',
              'terrain_radiometric_normalization': False, 'speckle_filtered': False,
              'dem_vertical_datum': 'EGM96', 'external_dem_apply_egm': True,
              'crs': 'EPSG:32633', 'spacing_m': 5, 'observations': [],
              'input_sha256': {str(dem): sha256(dem)}}
    for date in DATES:
        info = json.loads((root / f'kalari_abdu_6km_{date}' / 'extraction_info.json').read_text())
        source = root / Path(info['source_product_xml']).parent.name / 'product.xml'
        # Hash all calibration/geometry inputs and full original complex image.
        for name in ['product.xml', 'lutSigma.xml', 'imagery_HH.tif']:
            path = source.parent / name
            require(path.exists(), f'Missing source: {path}')
            record['input_sha256'][str(path)] = sha256(path)
        with tempfile.TemporaryDirectory(prefix='.calibration-', dir=output) as temporary:
            stage = Path(temporary)
            target = stage / f'sigma0_{date}_tc.tif'
            graph = output / f'calibration_{date}.xml'
            make_graph(source, dem, target).write(graph, encoding='utf-8', xml_declaration=True)
            log = output / f'calibration_{date}.log'
            print(f'Calibrating and terrain correcting {date}...', flush=True)
            with log.open('w') as handle:
                result = subprocess.run([str(gpt), str(graph), '-c', '2G', '-q', '4',
                    '-J-Xmx8G', '-J-Djava.awt.headless=true'], stdout=handle, stderr=subprocess.STDOUT)
            require(result.returncode == 0, log.read_text()[-6000:])
            checks = validate(target)
            require(checks['intensity_max'] < 1e6, 'Implausible calibrated sigma0 scale')
            record['observations'].append({'id': date, 'file': target.name,
                'source_product': source.parent.name, 'sha256': sha256(target), 'validation': checks})
            os.replace(target, output / target.name)
            make_graph(source, dem, output / target.name).write(graph, encoding='utf-8', xml_declaration=True)
            print(f'{date}: validated linear sigma0 and terrain geometry', flush=True)
    for path, digest in record['input_sha256'].items():
        require(sha256(Path(path)) == digest, f'Source changed during processing: {path}')
    (output / 'calibration_info.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'Calibrated products saved: {output}', flush=True)


if __name__ == '__main__':
    main()
