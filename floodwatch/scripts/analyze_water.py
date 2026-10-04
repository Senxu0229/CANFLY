#!/usr/bin/env python3
"""Reproducible exploratory open-water change analysis; not validated flood extent."""
import argparse
import json
from pathlib import Path
import math
import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks
from osgeo import gdal, ogr, osr
from export_observations import DATES, CENTER, sha256, require
from water_classes import CODES

NODATA = -9999.0
PIXEL = 10
FILTER = 3
MIN_PATCH = 9  # 900 m2 = 0.09 ha; exploratory minimum mapping unit


def crs(code):
    s = osr.SpatialReference()
    s.ImportFromEPSG(code)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def write_raster(path, array, gt, projection, names, nodata=NODATA):
    arrays = array if array.ndim == 3 else array[np.newaxis]
    kind = gdal.GDT_Byte if array.dtype == np.uint8 else gdal.GDT_Float32
    ds = gdal.GetDriverByName('GTiff').Create(str(path), arrays.shape[2], arrays.shape[1], len(arrays), kind,
        options=['COMPRESS=DEFLATE', 'TILED=YES', 'PREDICTOR=' + ('2' if kind == gdal.GDT_Byte else '3')])
    ds.SetGeoTransform(gt)
    ds.SetProjection(projection)
    for i, (data, name) in enumerate(zip(arrays, names), 1):
        band = ds.GetRasterBand(i)
        band.SetDescription(name)
        band.SetNoDataValue(nodata)
        band.WriteArray(data)
    ds.FlushCache()
    ds = None


def remove_small(mask, minimum=MIN_PATCH):
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())
    keep = sizes >= minimum
    keep[0] = False
    return keep[labels]


def otsu(values):
    hist, edges = np.histogram(values, bins=512, range=(-40, 5))
    centers = (edges[:-1] + edges[1:]) / 2
    p = hist / hist.sum()
    w = np.cumsum(p)
    m = np.cumsum(p * centers)
    between = (m[-1] * w - m) ** 2 / np.maximum(w * (1 - w), 1e-15)
    i = int(np.argmax(between[:-1]))
    total = float(np.sum(p * (centers - m[-1]) ** 2))
    return float(edges[i + 1]), float(between[i] / total)


def histogram_valley(values, bin_width=.1):
    """Select a shared cutoff from a pronounced valley, without using change area.

    Fail rather than invent a cutoff for a distribution without two distinct modes.
    A histogram valley separates radar populations; it does not validate water.
    """
    hist, edges = np.histogram(values, bins=np.arange(-35, 5 + bin_width / 2, bin_width))
    centers = (edges[:-1] + edges[1:]) / 2
    smoothed = ndimage.gaussian_filter1d(hist.astype(float), .3 / bin_width)
    peaks, _ = find_peaks(smoothed, distance=round(3 / bin_width), prominence=smoothed.max() * .05)
    require(len(peaks) >= 2, 'No distinct histogram modes; inspect the data before selecting a threshold')
    left, right = sorted(peaks[np.argsort(smoothed[peaks])[-2:]])
    valley = left + int(np.argmin(smoothed[left:right + 1]))
    ratio = float(smoothed[valley] / min(smoothed[left], smoothed[right]))
    require(left < valley < right and ratio < .5, 'Histogram valley is not sufficiently distinct')
    # Half-dB rounding avoids implying precision finer than histogram selection supports.
    threshold = float(round(float(centers[valley]) * 2) / 2)
    require(centers[left] < threshold < centers[right], 'Rounded cutoff lies outside the histogram modes')
    return threshold, {'bin_width_db': bin_width, 'range_db': [-35, 5],
        'gaussian_sigma_db': .3, 'minimum_peak_separation_db': 3,
        'minimum_peak_prominence_fraction': .05, 'maximum_valley_to_smaller_peak_ratio': .5,
        'peak_centers_db': [float(centers[left]), float(centers[right])],
        'valley_db': float(centers[valley]), 'valley_to_smaller_peak_ratio': ratio,
        'rounding_step_db': .5, 'threshold_db': threshold}


def classify(before, after, valid, threshold):
    b = remove_small(valid & (before < threshold))
    a = remove_small(valid & (after < threshold))
    # 0 invalid, 1 neither, 2 water on both, 3 new candidate, 4 lost candidate.
    result = np.zeros(before.shape, np.uint8)
    result[valid] = CODES['neither']
    result[b & a] = CODES['persistent']
    result[~b & a & valid] = CODES['new']
    result[b & ~a & valid] = CODES['brighter']
    return result


def area_stats(classes):
    # UTM grid area, approximate ground area (<0.1% projection distortion here).
    counts = np.bincount(classes.ravel(), minlength=5)
    area = counts * PIXEL ** 2 / 1e6
    return {'common_valid_km2': float(area[1:].sum()),
        'before_water_km2': float(area[CODES['persistent']] + area[CODES['brighter']]),
        'after_water_km2': float(area[CODES['persistent']] + area[CODES['new']]),
        'persistent_water_km2': float(area[CODES['persistent']]), 'new_water_km2': float(area[CODES['new']]),
        'lost_water_km2': float(area[CODES['brighter']]), 'net_water_change_km2': float(area[CODES['new']] - area[CODES['brighter']])}


def prepare(root, directory):
    provenance = json.loads((directory / 'calibration_info.json').read_text())
    require(provenance['radiometrically_calibrated'], 'Calibration is required')
    boundary_path = root / 'kalari_abdu_6km_20240828/kalari_abdu_6km_aoi.geojson'
    vector = ogr.Open(str(boundary_path))
    feature = vector.GetLayer().GetNextFeature()  # Keep parent alive for OGR geometry.
    geometry = feature.GetGeometryRef().Clone()
    geometry.Transform(osr.CoordinateTransformation(crs(4326), crs(32633)))
    xmin, xmax, ymin, ymax = geometry.GetEnvelope()
    bounds = [math.floor(xmin / 10) * 10 - 50, math.floor(ymin / 10) * 10 - 50,
              math.ceil(xmax / 10) * 10 + 50, math.ceil(ymax / 10) * 10 + 50]
    width, height = round((bounds[2] - bounds[0]) / 10), round((bounds[3] - bounds[1]) / 10)
    gt = (bounds[0], 10, 0, bounds[3], 0, -10)
    projection = crs(32633).ExportToWkt()
    mem_vector = ogr.GetDriverByName('MEM').CreateDataSource('')
    layer = mem_vector.CreateLayer('aoi', crs(32633), ogr.wkbPolygon)
    f = ogr.Feature(layer.GetLayerDefn()); f.SetGeometry(geometry); layer.CreateFeature(f)
    mask_ds = gdal.GetDriverByName('MEM').Create('', width, height, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt); mask_ds.SetProjection(projection)
    gdal.RasterizeLayer(mask_ds, [1], layer, burn_values=[1])
    aoi = mask_ds.ReadAsArray().astype(bool)
    unfiltered, filtered, valid_masks = [], [], []
    for observation in provenance['observations']:
        date = observation['id']
        source = directory / observation['file']
        require(sha256(source) == observation['sha256'], 'Calibration output hash mismatch')
        # SNAP's second band is DEM, not alpha. Explicitly select sigma0 only.
        sigma = gdal.Translate('', str(source), format='MEM', bandList=[1])
        warped = gdal.Warp('', sigma, format='MEM', dstSRS='EPSG:32633', outputBounds=bounds,
            width=width, height=height, resampleAlg='average', srcNodata=0, dstNodata=NODATA)
        linear = warped.ReadAsArray()
        valid = np.isfinite(linear) & (linear > 0)
        # Average in linear power, NEVER smooth logarithmic dB or display pixels.
        weights = ndimage.uniform_filter(valid.astype(np.float64), FILTER, mode='constant')
        smooth = ndimage.uniform_filter(np.where(valid, linear, 0).astype(np.float64), FILTER, mode='constant')
        smooth = np.divide(smooth, weights, out=np.zeros_like(smooth), where=weights > 0)
        full_support = ndimage.binary_erosion(valid, structure=np.ones((FILTER, FILTER)))
        unfiltered.append(linear); filtered.append(smooth); valid_masks.append(full_support)
    common = aoi & valid_masks[0] & valid_masks[1]
    require(common.sum() / aoi.sum() > .99, 'Insufficient common AOI coverage')
    dbs = []
    for date, linear, smooth in zip(DATES, unfiltered, filtered):
        db = 10 * np.log10(np.maximum(smooth, 1e-20))
        arrays = np.stack([linear, smooth, db]).astype(np.float32)
        arrays[:, ~common] = NODATA
        write_raster(directory / f'analysis_{date}_10m.tif', arrays, gt, projection,
            ['sigma0_HH_linear_10m_average', 'sigma0_HH_linear_30m_box_mean', 'sigma0_HH_dB_30m_box_mean'])
        dbs.append(db)
    write_raster(directory / 'common_valid_mask.tif', common.astype(np.uint8), gt, projection, ['common_valid'], nodata=0)
    return dbs, common, aoi, gt, projection, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--analysis-dir', type=Path, required=True)
    parser.add_argument('--threshold-db', type=float)
    parser.add_argument('--threshold-method', choices=['valley', 'otsu'], default='otsu')
    args = parser.parse_args()
    gdal.UseExceptions(); ogr.UseExceptions(); osr.UseExceptions()
    output = args.analysis_dir.resolve()
    (before, after), valid, aoi, gt, projection, provenance = prepare(args.dataset_root.resolve(), output)
    pooled = np.concatenate([before[valid], after[valid]])
    require(np.isfinite(pooled).all(), 'Non-finite calibrated backscatter')
    require(float(((pooled > -40) & (pooled < 5)).mean()) > .99, 'Unexpected calibrated backscatter distribution')
    otsu_threshold, separability = otsu(pooled)
    threshold = otsu_threshold
    threshold_method = 'pooled two-date Otsu'
    selection = None
    if args.threshold_db is not None:
        require(np.isfinite(args.threshold_db) and -40 < args.threshold_db < 5, 'Invalid threshold in dB')
        threshold = args.threshold_db
        threshold_method = 'explicit exploratory threshold'
    elif args.threshold_method == 'valley':
        threshold, selection = histogram_valley(pooled)
        threshold_method = 'pooled two-date histogram valley'
        alternate_threshold, alternate = histogram_valley(pooled, bin_width=.2)
        require(abs(threshold - alternate_threshold) <= .5, 'Histogram cutoff is unstable across bin widths')
        selection['bin_width_check'] = alternate
    classes = classify(before, after, valid, threshold)
    scenarios = []
    # Independent thresholds for each date, not just coupled shifts.
    for db in [-1., 0., 1.]:
        for da in [-1., 0., 1.]:
            b = remove_small(valid & (before < threshold + db))
            a = remove_small(valid & (after < threshold + da))
            scenarios.append({'before_threshold_db': threshold + db, 'after_threshold_db': threshold + da,
                              'new_water_km2': float((valid & ~b & a).sum() * .0001)})
    conservative = remove_small(valid & (after < threshold - 1) & (before >= threshold + 1))
    # A spatial one-pixel guard highlights sensitivity near pre-existing water edges.
    bwater = (classes == 2) | (classes == 4)
    edge_safe = (classes == 3) & ~ndimage.binary_dilation(bwater, iterations=1)
    labels, n = ndimage.label(classes == 3, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel()); sizes[0] = 0
    transform = osr.CoordinateTransformation(crs(32633), crs(4326))
    cx, cy, _ = osr.CoordinateTransformation(crs(4326), crs(32633)).TransformPoint(*CENTER)
    patches = []
    for label in np.argsort(sizes)[-5:][::-1]:
        if sizes[label] == 0: continue
        r, c = ndimage.center_of_mass(labels == label)
        x, y = gdal.ApplyGeoTransform(gt, c + .5, r + .5)
        lon, lat, _ = transform.TransformPoint(x, y)
        bearing = (math.degrees(math.atan2(x - cx, y - cy)) + 360) % 360
        patches.append({'area_km2': float(sizes[label] * .0001), 'centroid_lon_lat': [lon, lat],
                        'distance_from_village_km': math.hypot(x - cx, y - cy) / 1000,
                        'direction': ['N','NE','E','SE','S','SW','W','NW'][round(bearing / 45) % 8]})
    report = {'schema_version': '1.0', 'status': 'exploratory-unvalidated', 'dates': list(DATES),
        'name': 'Exploratory low-backscatter threshold transitions', 'interpretation': 'Water extent and water recession are unvalidated; field names containing water refer to radar threshold classes only', 'crs': 'EPSG:32633', 'pixel_size_m': 10,
        'geotransform': list(gt), 'shape': list(valid.shape), 'center': list(CENTER), 'radius_m': 6000,
        'aoi_grid_area_km2': float(aoi.sum() * .0001),
        'no_data_area_km2': float((aoi & ~valid).sum() * .0001),
        'distribution_percentiles_db': {date: np.percentile(values[valid], [1,10,25,50,75,90,99]).tolist() for date,values in zip(DATES,[before,after])},
        'method': {'quantity': 'sigma0 HH', 'calibration': 'SNAP product sigma LUT',
            'terrain_correction': 'Range-Doppler / SRTM with EGM96 conversion',
            'smoothing': '3 x 3 box mean of linear power on 10 m grid (30 m footprint)',
            'threshold_method': threshold_method,
            'threshold_db': threshold, 'otsu_separability': separability,
            'threshold_selection': selection,
            'minimum_water_patch_pixels': MIN_PATCH, 'connectivity': 8},
        'otsu_reference': {'threshold_db': otsu_threshold,
            'areas': area_stats(classify(before, after, valid, otsu_threshold))},
        'areas': area_stats(classes), 'sensitivity': {'description': 'Independent +/- 1 dB thresholds for each date; NOT a confidence interval',
            'scenarios': scenarios, 'new_water_min_km2': min(s['new_water_km2'] for s in scenarios),
            'new_water_max_km2': max(s['new_water_km2'] for s in scenarios),
            'conservative_core_km2': float(conservative.sum() * .0001),
            'excluding_10m_existing_water_edge_km2': float(edge_safe.sum() * .0001)},
        'largest_new_patches': patches,
        'limitations': [
            'Orange class means leaving the low-return class, not confirmed water recession. Net class-area change is not a measured change in water extent.',
            'Candidate open water only; no independent same-date ground-truth validation.',
            'Smooth bare soil, roads and radar shadows can resemble water; vegetation-covered or urban flooding may be missed.',
            'The shared threshold separates dark and bright radar returns, not semantic land cover. A histogram valley is not independent validation. Threshold sensitivity is not accuracy or a statistical confidence interval.',
            '10 m grid spacing is not independent 10 m resolution: interpolation and 30 m smoothing affect shorelines and small features.',
            'Residual registration error and mixed shoreline pixels can create apparent changes. No image shift was fitted to changing water.',
            'The 28 August baseline may contain water; 21 September is not necessarily the flood peak. New water is not net water increase or attributable flood damage.',
            'Areas use UTM grid pixel area (approximately ground area); outside-AOI and missing pixels are excluded.'],
        'input_sha256': {str(output / x['file']): x['sha256'] for x in provenance['observations']}}
    write_raster(output / 'water_change_classes.tif', classes, gt, projection,
        ['0=nodata;1=neither;2=both_dates;3=new_candidate;4=lost_candidate'], nodata=0)
    change = np.where(valid, after - before, NODATA).astype(np.float32)
    write_raster(output / 'sigma0_change_db.tif', change, gt, projection, ['after_minus_before_sigma0_dB'])
    write_raster(output / 'new_water_conservative_core.tif', np.where(valid, conservative, 255).astype(np.uint8), gt, projection, ['core_1_other_0'], nodata=255)
    report['output_sha256'] = {p.name: sha256(p) for p in output.glob('*.tif') if not p.name.startswith('sigma0_202')}
    (output / 'analysis_report.json').write_text(json.dumps(report, indent=2) + '\n')
    # Standalone QC figure, including actual distributions used for thresholding.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    fig, axes = plt.subplots(2, 2, figsize=(13, 12), constrained_layout=True)
    extent = [(gt[0]-cx)/1000, (gt[0]+10*valid.shape[1]-cx)/1000,
              (gt[3]-10*valid.shape[0]-cy)/1000, (gt[3]-cy)/1000]
    for ax, values, title in zip(axes[0], [before, after], ['28 Aug 2024: baseline', '21 Sep 2024: post-event']):
        ax.imshow(np.ma.masked_where(~valid, values), cmap='gray', vmin=-25, vmax=-5, extent=extent)
        ax.plot(0,0,'r+',ms=9); ax.set_title(title + '\nCalibrated HH sigma0, -25 to -5 dB'); ax.set_xlabel('East of village (km)'); ax.set_ylabel('North (km)')
    colors = ['#ffffff','#e0e3df','#176aaf','#00c8dc','#eea64b']
    axes[1,0].imshow(classes, cmap=ListedColormap(colors), norm=BoundaryNorm(np.arange(-.5,5.5),5), extent=extent, interpolation='nearest')
    axes[1,0].plot(0,0,'r+',ms=9)
    axes[1,0].set_title(f'Possible new water: {report["areas"]["new_water_km2"]:.2f} km²\nWater extent unvalidated; orange does not prove recession')
    axes[1,0].legend(handles=[Patch(color=colors[i], label=l) for i,l in [(2,'Possible water on both dates'),(3,'Possible new water'),(4,'Other changes to check')]],loc='lower left',fontsize=8)
    axes[1,0].set_xlabel('East of village (km)'); axes[1,0].set_ylabel('North (km)')
    for array, name in [(before,'28 Aug'),(after,'21 Sep')]:
        axes[1,1].hist(array[valid],bins=np.linspace(-35,0,141),density=True,histtype='step',label=name)
    axes[1,1].axvline(threshold,color='black',ls='--',label=f'Threshold {threshold:.2f} dB')
    if threshold != otsu_threshold:
        axes[1,1].axvline(otsu_threshold,color='#b66218',ls=':',label=f'Previous Otsu rule {otsu_threshold:.2f} dB')
    axes[1,1].set_xlabel('Smoothed sigma0 HH (dB)'); axes[1,1].set_ylabel('Density'); axes[1,1].legend()
    axes[1,1].set_title('Brightness classes are not confirmed land-cover classes')
    fig.suptitle('Kalari Abdu · 6 km radius · north up', fontsize=17)
    fig.savefig(output / 'water_change_preview.png', dpi=170); plt.close(fig)
    print(json.dumps({k:report[k] for k in ['method','areas','sensitivity','largest_new_patches']},indent=2))


if __name__ == '__main__':
    main()
