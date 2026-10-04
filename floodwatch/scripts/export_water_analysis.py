#!/usr/bin/env python3
"""Publish validated local analysis artifacts; manifest replaced last."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from osgeo import gdal, osr
from PIL import Image
from export_observations import sha256, require
from analyze_water import crs
from water_classes import CONTRACT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir', type=Path, required=True)
    parser.add_argument('--web-dir', type=Path, required=True)
    args = parser.parse_args()
    gdal.UseExceptions()
    source, web = args.analysis_dir.resolve(), args.web_dir.resolve()
    report = json.loads((source / 'analysis_report.json').read_text())
    manifest = json.loads((web / 'manifest.json').read_text())
    require(all(date in [o['id'] for o in manifest['observations']] for date in report['dates']), 'Analysis observations missing')
    require(manifest['aoi']['center'] == report['center'] and manifest['aoi']['radius_m'] == report['radius_m'], 'Study area mismatch')
    for name, digest in report['output_sha256'].items():
        require(sha256(source / name) == digest, f'Analysis output changed: {name}')
    transform = osr.CoordinateTransformation(crs(4326), crs(3857))
    west, south, east, north = manifest['aoi']['bounds']
    xmin, ymin, _ = transform.TransformPoint(west, south)
    xmax, ymax, _ = transform.TransformPoint(east, north)
    width, height = manifest['display']['width'], manifest['display']['height']
    options = dict(format='MEM', dstSRS='EPSG:3857', outputBounds=[xmin,ymin,xmax,ymax], width=width, height=height)
    token = sha256(source / 'analysis_report.json')[:12]
    with tempfile.TemporaryDirectory(prefix='.water-export-', dir=web.parent) as temporary:
        stage = Path(temporary)
        for observation in manifest['observations']:
            if observation['id'] not in report['dates']:
                continue
            date = observation['id']
            raster = source / f'analysis_{date}_10m.tif'
            ds = gdal.Open(str(raster))
            require(tuple(ds.GetGeoTransform()) == tuple(report['geotransform']), 'Analysis grid mismatch')
            band = gdal.Translate('', ds, format='MEM', bandList=[2])
            warped = gdal.Warp('', band, resampleAlg='average', srcNodata=-9999, dstNodata=-9999, **options)
            linear = warped.ReadAsArray()
            valid = np.isfinite(linear) & (linear > 0)
            gray = np.clip((10*np.log10(np.maximum(linear, 1e-20)) + 25) / 20 * 255,0,255).astype(np.uint8)
            rgba = np.stack([gray,gray,gray,valid.astype(np.uint8)*255],axis=-1)
            filename = f'radar_{date}_sigma0_{token}.png'
            Image.fromarray(rgba).save(stage / filename)
            observation['image_url'] = 'observations/' + filename
        classes = gdal.Warp('', str(source / 'water_change_classes.tif'), resampleAlg='near', srcNodata=0,dstNodata=0,**options).ReadAsArray()
        colors = np.array([entry['rgba'] for entry in sorted(CONTRACT['classes'], key=lambda item: item['code'])],dtype=np.uint8)
        overlay = f'water_change_{token}.png'
        Image.fromarray(colors[classes]).save(stage / overlay)
        public_report = copy.deepcopy(report)
        # Public report uses relative file references; private source paths remain in local provenance.
        public_report['input_sha256'] = {Path(k).name:v for k,v in report['input_sha256'].items()}
        public_report['overlay_url'] = 'observations/' + overlay
        public_report['display_bounds'] = manifest['aoi']['bounds']
        public_report['downloads'] = {}
        for key, filename in [('preview','water_change_preview.png'), ('before','analysis_20240828_10m.tif'),
                              ('after','analysis_20240921_10m.tif'), ('classes','water_change_classes.tif')]:
            target = Path(filename).stem + '_' + token + Path(filename).suffix
            shutil.copy2(source / filename, stage / target)
            public_report['downloads'][key] = 'observations/' + target
        report_name = 'analysis_report_' + token + '.json'
        public_report['downloads']['report'] = 'observations/' + report_name
        (stage / report_name).write_text(json.dumps(public_report,indent=2) + '\n')
        manifest['analysis_url'] = 'observations/' + report_name
        manifest['display'].update({'status':'calibrated-analysis-preview','radiometrically_calibrated':True,
            'stretch':{'min':-25,'max':-5,'unit':'sigma0 HH dB'},
            'resampling':'Linear sigma0: 10 m area averaging, 3 x 3 mean, then display resampling'})
        manifest['limitations'] = ['Display brightness differences are not measurements of flooding; use the separate candidate-change layer and read its uncertainty notes.'] + report['limitations']
        manifest['credit'] = 'RADARSAT-2: EODMS R2TF. Terrain: NASA SRTM via ESA STEP. Radar-class diagnostics; water extent and recession unvalidated.'
        (stage / 'manifest.json').write_text(json.dumps(manifest,indent=2) + '\n')
        for path in stage.glob('*.png'):
            with Image.open(path) as im:
                im.verify()
        for path in sorted(stage.iterdir(), key=lambda p:p.name == 'manifest.json'):
            os.replace(path,web / path.name)
    print(f'Exported calibrated previews, change overlay and local downloads: {web}')


if __name__ == '__main__':
    main()
