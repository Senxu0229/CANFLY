#!/usr/bin/env python3
"""Append validated additional-date previews without reusing pair-specific analysis."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from osgeo import gdal
from PIL import Image
from export_observations import require, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root',type=Path,required=True)
    parser.add_argument('--web-dir',type=Path,required=True)
    parser.add_argument('--dates',nargs='+',required=True)
    args=parser.parse_args()
    gdal.UseExceptions()
    root,web=args.dataset_root.expanduser().resolve(),args.web_dir.resolve()
    manifest=json.loads((web/'manifest.json').read_text())
    require(manifest['display']['status']=='calibrated-analysis-preview','Expected calibrated base export')
    reference=json.loads((root/'kalari_abdu_analysis/analysis_report.json').read_text())
    reference_mask=root/'kalari_abdu_analysis/common_valid_mask.tif'
    require(sha256(reference_mask)==reference['output_sha256'][reference_mask.name],'Reference mask changed')
    mask_ds=gdal.Open(str(reference_mask)); mask=mask_ds.ReadAsArray()>0
    with tempfile.TemporaryDirectory(prefix='.append-observations-',dir=web.parent) as temporary:
        stage=Path(temporary)
        for date in args.dates:
            require(len(date)==8 and date.isdigit(),'Expected YYYYMMDD')
            directory=root/f'kalari_abdu_6km_{date}'
            info=json.loads((directory/'processing_info.json').read_text())
            require(info['date'].replace('-','')==date,'Date mismatch')
            require(info['radiometrically_calibrated'] and info['terrain_corrected'],'Preprocessing missing')
            require([info['center']['longitude'],info['center']['latitude']]==manifest['aoi']['center'] and info['radius_m']==manifest['aoi']['radius_m'],'AOI mismatch')
            for key in ['crs','width','height','stretch']:
                require(info['display'][key]==manifest['display'][key],f'Display {key} mismatch')
            require(info['display']['bounds']==manifest['aoi']['bounds'],'Display bounds mismatch')
            for name in ['kalari_abdu_6km_preview.png','kalari_abdu_6km_preview_map.tif','kalari_abdu_6km_sigma0_10m.tif']:
                require(sha256(directory/name)==info['files'][name]['sha256'],f'Changed output: {name}')
            raster=gdal.Open(str(directory/'kalari_abdu_6km_sigma0_10m.tif'))
            require(raster.GetGeoTransform()==mask_ds.GetGeoTransform() and raster.GetProjection()==mask_ds.GetProjection(),'Analysis grid mismatch')
            require(np.array_equal(raster.GetRasterBand(1).ReadAsArray()!=-9999,mask),'AOI coverage mismatch')
            image_path=directory/'kalari_abdu_6km_preview.png'
            with Image.open(image_path) as image:
                require(image.size==(manifest['display']['width'],manifest['display']['height']) and image.mode=='RGBA','Unexpected PNG dimensions or bands')
                image.verify()
            token=sha256(image_path)[:12]
            filename=f'radar_{date}_sigma0_{token}.png'
            shutil.copy2(image_path,stage/filename)
            geometry=info['acquisition_geometry']
            require([geometry[k] for k in ['beamModeMnemonic','polarizations','passDirection']]==['XF0W2','HH','Descending'],'Acquisition settings differ')
            observation={'id':date,'date':info['date'],'role':'post-event','label':'Follow-up observation',
                'image_url':'observations/'+filename,'source_product':Path(info['source_product_xml']).parent.name,
                'beam_mode':geometry['beamModeMnemonic'],'polarization':geometry['polarizations'],
                'orbit_direction':geometry['passDirection'],'acquisition_utc':info['acquisition_utc']}
            manifest['observations']=[o for o in manifest['observations'] if o['id']!=date]+[observation]
            (stage/f'observation_{date}_provenance.json').write_text(json.dumps({
                'observation':observation,'display':info['display'],'analysis_grid':{k:v for k,v in info['analysis_grid'].items() if k!='reference_mask'},
                'source_processing_record_sha256':sha256(directory/'processing_info.json'),
                'png_sha256':sha256(image_path),'validation':info['validation']},indent=2)+'\n')
        manifest['observations'].sort(key=lambda o:o['date'])
        require(len({o['id'] for o in manifest['observations']})==len(manifest['observations']),'Duplicate observations')
        # analysis_url is intentionally unchanged: its report names its own two dates.
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        for path in sorted(stage.iterdir(),key=lambda p:p.name=='manifest.json'):
            os.replace(path,web/path.name)
    print('Available observations: '+', '.join(o['date'] for o in manifest['observations']))


if __name__=='__main__':
    main()
