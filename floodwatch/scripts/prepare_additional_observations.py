#!/usr/bin/env python3
"""Prepare dated 6 km sigma0 crops on the existing analysis grid.

Reuses the verified full-product SNAP calibration/geocoding graph. Does not
classify water or change the active two-date web comparison. Original SLCs are
retained; generated GeoTIFFs hold calibrated power, not complex I/Q samples.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage
from osgeo import gdal, osr
from PIL import Image

from analyze_water import crs, write_raster, NODATA, FILTER
from calibrate_observations import make_graph
from terrain_correct_observations import validate
from export_observations import CENTER, RADIUS, require, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--display-manifest', type=Path, required=True)
    parser.add_argument('--dem', type=Path, required=True)
    parser.add_argument('--gpt', type=Path, required=True)
    parser.add_argument('--dates', nargs='+', required=True)
    args = parser.parse_args()
    gdal.UseExceptions(); osr.UseExceptions()
    root = args.dataset_root.expanduser().resolve()
    reference = args.reference_dir.expanduser().resolve()
    dem = args.dem.expanduser().resolve()
    gpt = args.gpt.expanduser().resolve()
    mask_path = reference / 'common_valid_mask.tif'
    reference_info = json.loads((reference / 'analysis_report.json').read_text())
    require(reference_info['center'] == list(CENTER) and reference_info['radius_m'] == RADIUS,
            'Reference center or radius differs')
    require(reference_info['no_data_area_km2'] == 0, 'Reference mask must cover entire AOI')
    require(sha256(mask_path) == reference_info['output_sha256'][mask_path.name], 'Reference mask hash mismatch')
    mask_dataset = gdal.Open(str(mask_path))
    circle = mask_dataset.ReadAsArray().astype(bool)
    gt = mask_dataset.GetGeoTransform()
    projection = mask_dataset.GetProjection()
    height, width = circle.shape
    require(gt[1] == 10 and gt[5] == -10 and gt[2] == gt[4] == 0, 'Reference must use north-up 10 m grid')
    require(mask_dataset.GetSpatialRef().GetAuthorityCode(None) == '32633', 'Reference must use UTM 33N')
    bounds = [gt[0], gt[3] - height*10, gt[0] + width*10, gt[3]]
    display_manifest = json.loads(args.display_manifest.read_text())
    require(display_manifest['aoi']['center'] == list(CENTER) and display_manifest['aoi']['radius_m'] == RADIUS,
            'Display AOI differs')
    display = display_manifest['display']
    require(display['stretch'] == {'min': -25, 'max': -5, 'unit': 'sigma0 HH dB'}, 'Expected calibrated display scale')
    west, south, east, north = display_manifest['aoi']['bounds']
    transform = osr.CoordinateTransformation(crs(4326), crs(3857))
    xmin, ymin, _ = transform.TransformPoint(west, south)
    xmax, ymax, _ = transform.TransformPoint(east, north)
    dwidth, dheight = display['width'], display['height']
    dem_ds = gdal.Open(str(dem))
    require(dem_ds.GetSpatialRef().GetAuthorityCode(None) == '4326' and dem_ds.GetRasterBand(1).GetNoDataValue() == -32768,
            'Expected EPSG:4326 EGM96 DEM with -32768 nodata')
    aoi_path = root / 'kalari_abdu_6km_20240828/kalari_abdu_6km_aoi.geojson'
    for date in args.dates:
        require(len(date) == 8 and date.isdigit(), 'Use YYYYMMDD dates')
        products = list(root.glob(f'RS2_*_{date}_*_SLC'))
        require(len(products) == 1, f'Expected exactly one complete source product for {date}')
        source = products[0] / 'product.xml'
        output = root / f'kalari_abdu_6km_{date}'
        require(not output.exists(), f'Refusing to overwrite existing directory: {output}')
        xml = ET.parse(source).getroot()
        metadata = {}
        for key in ['rawDataStartTime','beamModeMnemonic','polarizations','passDirection','productType']:
            node = xml.find('.//{*}' + key)
            require(node is not None and node.text, f'Missing {key}')
            metadata[key] = node.text.strip()
        expected_date = f'{date[:4]}-{date[4:6]}-{date[6:]}'
        require(metadata['rawDataStartTime'].startswith(expected_date), 'Acquisition date mismatch')
        require([metadata[k] for k in ['beamModeMnemonic','polarizations','passDirection','productType']] ==
                ['XF0W2','HH','Descending','SLC'], 'Source acquisition settings differ from baseline')
        inputs = [source, source.parent/'imagery_HH.tif', source.parent/'lutSigma.xml', dem, mask_path, aoi_path]
        print(f'{date}: hashing original inputs...', flush=True)
        hashes = {str(p): sha256(p) for p in inputs}
        with tempfile.TemporaryDirectory(prefix=f'.prepare-{date}-', dir=root) as temporary:
            stage = Path(temporary)
            intermediate = stage / 'sigma0_tc_buffered.tif'
            graph = stage / 'calibration_graph.xml'
            make_graph(source, dem, intermediate).write(graph, encoding='utf-8', xml_declaration=True)
            print(f'{date}: SNAP sigma0 calibration and terrain correction...', flush=True)
            log = stage / 'calibration.log'
            with log.open('w') as handle:
                process = subprocess.run([str(gpt),str(graph),'-c','2G','-q','4','-J-Xmx8G','-J-Djava.awt.headless=true'],stdout=handle,stderr=subprocess.STDOUT)
            require(process.returncode == 0, log.read_text()[-6000:])
            terrain_checks = validate(intermediate)
            source_band = gdal.Translate('', str(intermediate), format='MEM', bandList=[1])
            warped = gdal.Warp('', source_band, format='MEM', dstSRS='EPSG:32633', outputBounds=bounds,
                width=width, height=height, resampleAlg='average', srcNodata=0, dstNodata=NODATA)
            linear = warped.ReadAsArray()
            valid = np.isfinite(linear) & (linear > 0)
            support = ndimage.binary_erosion(valid, structure=np.ones((FILTER,FILTER)))
            require(bool(support[circle].all()), 'New observation does not fully cover the reference AOI')
            weights = ndimage.uniform_filter(valid.astype(np.float64),FILTER,mode='constant')
            smooth = ndimage.uniform_filter(np.where(valid,linear,0).astype(np.float64),FILTER,mode='constant')
            smooth = np.divide(smooth,weights,out=np.zeros_like(smooth),where=weights>0)
            db = 10*np.log10(np.maximum(smooth,1e-20))
            bands = np.stack([linear,smooth,db]).astype(np.float32)
            bands[:,~circle] = NODATA
            raster = stage / 'kalari_abdu_6km_sigma0_10m.tif'
            write_raster(raster,bands,gt,projection,
                ['sigma0_HH_linear_10m_average','sigma0_HH_linear_30m_box_mean','sigma0_HH_dB_30m_box_mean'])
            calibrated = gdal.Open(str(raster),gdal.GA_Update)
            calibrated.SetMetadata({'ACQUISITION_UTC':metadata['rawDataStartTime'],'SOURCE_PRODUCT':source.parent.name,
                'CENTER_LONGITUDE':str(CENTER[0]),'CENTER_LATITUDE':str(CENTER[1]),'AOI_RADIUS_M':str(RADIUS),
                'PROCESSING':'SNAP sigma0 calibration + SRTM Range-Doppler; shared 10 m UTM grid; circular mask',
                'SMOOTHING':'Band 1 unsmoothed; bands 2 and 3 use 3 x 3 linear-power mean'})
            for i in [1,2]: calibrated.GetRasterBand(i).SetUnitType('1')
            calibrated.GetRasterBand(3).SetUnitType('dB')
            calibrated.FlushCache(); calibrated = None
            # Reuse exactly the current calibrated web display grid and stretch.
            subset = gdal.Translate('',str(raster),format='MEM',bandList=[2])
            preview = gdal.Warp('',subset,format='MEM',dstSRS='EPSG:3857',
                outputBounds=[xmin,ymin,xmax,ymax],width=dwidth,height=dheight,
                resampleAlg='average',srcNodata=NODATA,dstNodata=NODATA)
            power = preview.ReadAsArray()
            visible = np.isfinite(power) & (power>0)
            gray = np.clip((10*np.log10(np.maximum(power,1e-20))+25)/20*255,0,255).astype(np.uint8)
            gray[~visible] = 0
            rgba = np.stack([gray,gray,gray,visible.astype(np.uint8)*255],axis=-1)
            Image.fromarray(rgba).save(stage/'kalari_abdu_6km_preview.png')
            preview_map = gdal.GetDriverByName('GTiff').Create(str(stage/'kalari_abdu_6km_preview_map.tif'),dwidth,dheight,4,gdal.GDT_Byte,
                options=['COMPRESS=DEFLATE','TILED=YES'])
            preview_map.SetGeoTransform(preview.GetGeoTransform()); preview_map.SetProjection(preview.GetProjection())
            for i,color in enumerate([gdal.GCI_RedBand,gdal.GCI_GreenBand,gdal.GCI_BlueBand,gdal.GCI_AlphaBand]):
                preview_map.GetRasterBand(i+1).WriteArray(rgba[:,:,i]); preview_map.GetRasterBand(i+1).SetColorInterpretation(color)
            preview_map.FlushCache(); preview_map = None
            shutil.copy2(aoi_path,stage/'kalari_abdu_6km_aoi.geojson')
            # Round-trip validation of every pixel and the exact grid/mask.
            check = gdal.Open(str(raster)); actual = check.ReadAsArray()
            require(check.GetGeoTransform() == gt and check.GetProjection() == projection, 'Output grid changed')
            require(np.array_equal(actual,bands), 'GeoTIFF round-trip mismatch')
            require(np.array_equal(actual[0]!=NODATA,circle),'Final AOI mask mismatch')
            require(np.isfinite(actual[:,circle]).all(),'Non-finite AOI values')
            require(np.allclose(actual[2,circle],10*np.log10(actual[1,circle]),atol=1e-5),'Linear/dB inconsistency')
            require(np.array_equal(np.asarray(Image.open(stage/'kalari_abdu_6km_preview.png')),rgba),'PNG round-trip mismatch')
            x,y,_ = osr.CoordinateTransformation(crs(4326),crs(32633)).TransformPoint(*CENTER)
            column,row = gdal.ApplyGeoTransform(gdal.InvGeoTransform(gt),x,y)
            require(bool(circle[int(row),int(column)]),'Village center is missing')
            for path,digest in hashes.items():
                require(sha256(Path(path)) == digest, f'Input changed during processing: {path}')
            # Keep the graph rerunnable; its buffered intermediate is not retained in this crop.
            make_graph(source,dem,output/'sigma0_tc_buffered.tif').write(graph,encoding='utf-8',xml_declaration=True)
            source_band = warped = subset = preview = check = None
            intermediate.unlink()
            for extra in stage.glob('sigma0_tc_buffered.tif.*'): extra.unlink()
            report = {'date':expected_date,'acquisition_utc':metadata['rawDataStartTime'],'source_product_xml':str(source),
                'center':{'longitude':CENTER[0],'latitude':CENTER[1]},'radius_m':RADIUS,'acquisition_geometry':metadata,
                'radiometrically_calibrated':True,'terrain_corrected':True,'dem_file':str(dem),'external_dem_apply_egm':True,
                'analysis_grid':{'crs':'EPSG:32633','geotransform':gt,'width':width,'height':height,'pixel_size_m':10,
                    'reference_mask':str(mask_path),'aoi_pixels':int(circle.sum()),'aoi_grid_area_km2':float(circle.sum()*.0001),'nodata':NODATA},
                'bands':['linear sigma0, averaged to 10 m','linear sigma0, 3 x 3 mean (30 m footprint)','band 2 converted to dB'],
                'display':{'crs':'EPSG:3857','bounds':display_manifest['aoi']['bounds'],'width':dwidth,'height':dheight,
                    'stretch':display['stretch'],'geotransform':gdal.Open(str(stage/'kalari_abdu_6km_preview_map.tif')).GetGeoTransform()},
                'software':{'SNAP':'14.0.0','GDAL':gdal.VersionInfo('--version')},'input_sha256':hashes,
                'validation':{'terrain_intermediate':terrain_checks,'all_aoi_pixels_valid':True,'exact_reference_grid_and_mask':True,
                    'raster_and_png_roundtrip':True,'village_center_valid':True,'original_inputs_unchanged':True},
                'limitations':['Calibrated intensity product, not an original complex SLC subset. Preserve the original complete product for future processing.',
                    '10 m grid spacing is not independent 10 m resolution; 30 m averaging smooths shorelines.',
                    'No additional thermal-noise subtraction, terrain radiometric normalization, manual shift or water classification.',
                    'Residual geolocation errors remain possible. Images alone do not establish water extent or crop damage.',
                    'The saved SNAP graph regenerates a buffered intermediate; run this script for the masked final outputs.'],
                'files':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p)} for p in stage.iterdir() if p.is_file()}}
            (stage/'processing_info.json').write_text(json.dumps(report,indent=2)+'\n')
            os.rename(stage,output)
            print(f'{date}: saved and validated {output}; {int(circle.sum())} AOI pixels',flush=True)


if __name__ == '__main__':
    main()
