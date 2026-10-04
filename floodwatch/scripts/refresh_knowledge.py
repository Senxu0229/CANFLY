#!/usr/bin/env python3
"""Refresh the small, verified RAG seed corpus from this project's active data.

Uses only the Python standard library; never scans arbitrary dataset directories.
Generated docs live in knowledge/generated. Hand-written knowledge/*.md or *.txt
are untouched. Run --check in validation to detect stale source-backed documents.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_record(path, project):
    try:
        display = str(path.relative_to(project))
    except ValueError:
        display = str(path)
    return f"- `{display}`; SHA256 `{digest(path)}`."


def public_path(project, url):
    public = (project / 'public').resolve()
    require(isinstance(url, str) and not url.startswith(('/', 'http:', 'https:')), 'Expected a local public URL')
    candidate = (public / url).resolve()
    require(candidate.is_relative_to(public), 'Public source escapes the public directory')
    return candidate


def check_algorithm(path, report, contract):
    """Fail for changed class semantics; do not import GDAL or execute data code."""
    codes = {item['key']: item['code'] for item in contract['classes']}
    require(codes == {'nodata': 0, 'neither': 1, 'persistent': 2, 'new': 3, 'brighter': 4},
            'Class codes changed; review the seed facts')

    class ResolveCodes(ast.NodeTransformer):
        def visit_Subscript(self, node):
            node = self.generic_visit(node)
            if isinstance(node.value, ast.Name) and node.value.id == 'CODES' and isinstance(node.slice, ast.Constant):
                return ast.copy_location(ast.Constant(value=codes[node.slice.value]), node)
            return node

    tree = ResolveCodes().visit(ast.parse(path.read_text(encoding='utf-8')))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {'PIXEL', 'FILTER', 'MIN_PATCH'}:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    require(constants == {'PIXEL': 10, 'FILTER': 3, 'MIN_PATCH': 9}, 'Analysis grid/filter/patch constants changed; review the seed facts')
    expected = '''def classify(before, after, valid, threshold):
    b = remove_small(valid & (before < threshold))
    a = remove_small(valid & (after < threshold))
    result = np.zeros(before.shape, np.uint8)
    result[valid] = 1
    result[b & a] = 2
    result[~b & a & valid] = 3
    result[b & ~a & valid] = 4
    return result
'''
    require(ast.dump(functions.get('classify', ast.Pass())) == ast.dump(ast.parse(expected).body[0]),
            'Classification semantics changed; update the knowledge generator after reviewing the code')
    cleanup = ast.unparse(functions['remove_small'])
    require('ndimage.label(mask, structure=np.ones((3, 3)))' in cleanup and 'sizes >= minimum' in cleanup
            and 'keep[0] = False' in cleanup, 'Connected-component filtering changed')
    expected_area = '''def area_stats(classes):
    counts = np.bincount(classes.ravel(), minlength=5)
    area = counts * PIXEL ** 2 / 1e6
    return {'common_valid_km2': float(area[1:].sum()),
        'before_water_km2': float(area[2] + area[4]),
        'after_water_km2': float(area[2] + area[3]),
        'persistent_water_km2': float(area[2]), 'new_water_km2': float(area[3]),
        'lost_water_km2': float(area[4]), 'net_water_change_km2': float(area[3] - area[4])}
'''
    require(ast.dump(functions['area_stats']) == ast.dump(ast.parse(expected_area).body[0]), 'Area formula changed')
    method = report['method']
    require(report['pixel_size_m'] == 10 and method['minimum_water_patch_pixels'] == 9 and method['connectivity'] == 8,
            'Active report differs from verified grid/patch parameters')
    require(report['status'] == 'exploratory-unvalidated', 'Report validation status changed; review limitations')


def build_documents(project, dataset_root):
    manifest_path = project / 'public/observations/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    report_path = public_path(project, manifest['analysis_url'])
    report = json.loads(report_path.read_text(encoding='utf-8'))
    algorithm_path = project / 'scripts/analyze_water.py'
    contract_path = project / 'shared/water_classes.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    classes = {item['key']: item for item in contract['classes']}
    calibration_path = dataset_root / 'kalari_abdu_analysis/calibration_info.json'
    calibration = json.loads(calibration_path.read_text(encoding='utf-8'))
    check_algorithm(algorithm_path, report, contract)
    require(manifest['aoi']['center'] == report['center'] and manifest['aoi']['radius_m'] == report['radius_m'],
            'Map and analysis AOIs differ')
    require(report['dates'] == ['20240828', '20240921'], 'The analysed pair changed; review date-specific explanations')
    require(calibration['radiometrically_calibrated'] is True, 'Calibration provenance is missing')
    for item in calibration['observations']:
        require(report['input_sha256'].get(item['file']) == item['sha256'], 'Report/calibration source hashes differ')
    observations = manifest['observations']
    require(len({item['id'] for item in observations}) == len(observations), 'Duplicate observation IDs')
    require({item['id'] for item in observations} == {'20240828', '20240921', '20241015', '20241108'},
            'Available dates changed; review the four-observation seed description')
    metadata = []
    for observation in observations:
        product = observation['source_product']
        require(Path(product).name == product and product not in {'.', '..'}, 'Invalid source product path')
        xml_path = dataset_root / product / 'product.xml'
        values = {}
        for node in ET.parse(xml_path).iter():
            key = node.tag.rsplit('}', 1)[-1]
            if key in {'satellite', 'sensor', 'beamModeMnemonic', 'polarizations', 'passDirection', 'productType', 'rawDataStartTime'}:
                values[key] = node.text
        for source_key, manifest_key in [('beamModeMnemonic', 'beam_mode'), ('polarizations', 'polarization'),
                                         ('passDirection', 'orbit_direction'), ('rawDataStartTime', 'acquisition_utc')]:
            require(values.get(source_key) == observation[manifest_key], f'{product}: manifest/XML mismatch for {source_key}')
        require(values.get('satellite') == 'RADARSAT-2' and values.get('sensor') == 'SAR' and values.get('productType') == 'SLC',
                'Sensor/product type changed; review acquisition text')
        if observation['id'] in report['dates']:
            expected_xml_hashes = [value for name, value in calibration['input_sha256'].items()
                                   if name.endswith('/' + product + '/product.xml')]
            require(expected_xml_hashes == [digest(xml_path)], 'Calibration XML source hash mismatch')
        metadata.append((observation, xml_path))

    def document(title, body, paths):
        provenance = '\n'.join(source_record(path, project) for path in paths)
        return f'# {title}\n\n{body.strip()}\n\n## Verified local sources\n\n{provenance}\n'

    lon, lat = manifest['aoi']['center']
    radius = manifest['aoi']['radius_m']
    dates = ', '.join(item['date'] for item in observations)
    a = report['areas']
    method = report['method']
    threshold = method['threshold_db']
    sensitivity = report['sensitivity']
    area = lambda key: f"{a[key]:.4f}"
    docs = {}
    docs['01_location_and_dates.md'] = document('Kalari Abdu location and map dates', f'''
FAQ: What are the exact coordinates of the village? Where is Kalari Abdu?

Kalari Abdu is the active project study area in Nigeria. The map centre is
longitude {lon}° E, latitude {lat}° N (WGS84). GeoJSON uses [longitude, latitude]:
[{lon}, {lat}].

The area of interest is a circle of radius {radius} metres ({radius / 1000:g} km),
approximately 12 km across. This is a radius, not a 6 km-wide square.
The two-date common valid analysis area is {area('common_valid_km2')} km².

Available radar acquisition dates: {dates}.
The configured event reference date is {manifest['event']['date']}; the application
labels the event “{manifest['event']['name']}”. This is project metadata, not evidence
that every pixel flooded on that day. The baseline image may already contain water.

Quantified change analysis exists only for 2024-08-28 → 2024-09-21 in that order.
Other date selections, including October/November and the reversed pair, are image
comparisons only. There are no calculated change areas for those selected pairs.
''', [manifest_path, report_path])

    rows = '\n'.join(f"- {item['date']}: {item['acquisition_utc']} (UTC raw-data start); {item['beam_mode']}, {item['polarization']}, {item['orbit_direction']}.\n  Product: `{item['source_product']}`."
                     for item, _ in metadata)
    docs['02_satellite_observations.md'] = document('Satellite and source observations', f'''
FAQ: Which satellite or spacecraft acquired these images? What radar sensor, beam mode and polarization do we use?

The four local source products are RADARSAT-2 SAR (synthetic aperture radar),
SLC (single look complex). These are radar measurements, not visible-light colour
photographs. All four source XML files identify beam mode XF0W2, HH polarization,
and Descending orbit direction. Using the same mode does not by itself validate the
water classification.

{rows}

Times above are `rawDataStartTime`, matching the website's `acquisition_utc`.
The XML first-image-line zero-Doppler time is a different metadata field.
No additional satellite or observation dates are available in this active manifest.
''', [xml_path for _, xml_path in metadata])

    docs['03_water_detection_method.md'] = document('How possible water is detected', f'''
FAQ: How is possible new water detected? How is water area calculated? What threshold identifies water?

For the analysed 2024-08-28 → 2024-09-21 pair, {calibration['software']} read the
complete HH SLC products, calibrated linear sigma0 using the product sigma LUT,
and performed Range-Doppler terrain correction with SRTM elevation and EGM96
conversion. Calibration output spacing is {calibration['spacing_m']} m in {calibration['crs']}.
Terrain radiometric normalization was not applied. Calibration alone does not
identify water.

The analysis uses {report['crs']}, a {report['pixel_size_m']} m grid. It area-averages
linear power, then applies a 3 × 3 mean (30 m footprint), then converts to dB using
10 × log10(sigma0). It does not measure PNG brightness. Each date's candidate mask
is smoothed sigma0 HH strictly below the common threshold {threshold} dB
(approximately {threshold:.1f} dB), selected by {method['threshold_method']}.
Connected components with fewer than {method['minimum_water_patch_pixels']} pixels
are removed separately from each date using {method['connectivity']}-neighbour connectivity.
Nine 10 m pixels are 900 m², or 0.09 hectares. Missing/outside-AOI pixels are excluded.

In short: calibrate, terrain-correct, resample to one grid, smooth linear power,
convert to dB and classify with the shared threshold. Below {threshold} dB only means
possible water. Statistics come from the analysis TIFFs, not the web PNG previews.
Possible new water means the earlier date did not meet the candidate rule and the
later date did, with small patches removed from both masks; not every new dark
pixel is confirmed flooding. Each analysis pixel is 10 × 10 = 100 m²; the 10 m grid
does not mean an independent 10 m spatial resolution.
Area = retained class pixel count × 100 m² / 1,000,000, expressed in km².
This is approximate ground area from UTM grid pixels, not a validated flood extent.
''', [report_path, algorithm_path, calibration_path])

    docs['04_legend_and_class_rules.md'] = document('Map legend and class meanings', f'''
FAQ: What does orange mean? Is orange damaged farmland? What do light blue and dark blue represent?

These classes describe the ordered 2024-08-28 → 2024-09-21 pair, using a shared
threshold of {threshold} dB and the small-patch cleanup described in the method.

- Light blue / cyan: “{classes['new']['label']}”, class 3. The pixel is outside
  the cleaned baseline low-return mask and inside the later low-return mask.
  It is possible new water, not confirmed inundation or attributable flood damage.
- Dark blue: “{classes['persistent']['label']}”, class 2. The pixel is inside
  both cleaned low-return masks. It does not establish permanent water or when flooding began.
- Orange: “{classes['brighter']['label']}”, class 4. The pixel is inside the
  baseline low-return mask and outside the later low-return mask: a change toward
  stronger returns requiring verification. Brighter returns; the cause needs checking.
  Small-patch filtering also affects the masks, so this is not a per-pixel proof
  of a raw signal increase. It does not establish confirmed water recession,
  damaged farmland, crop loss, or recovery.
- Class 1 is in neither cleaned candidate mask and is uncoloured. Uncoloured
  areas can still contain water missed by this method. Class 0 is outside the
  valid shared area or no-data; it is excluded from area statistics.

The grayscale image displays calibrated radar brightness; it is not a semantic
map of water, fields, shrubs, or soil. Orange change may have several explanations;
none is confirmed by the current classification. Do not read orange as recession or
farmland damage, or light blue as confirmed inundation. The code variable
`lost_water_km2` is a class area, not a verified recession area.
''', [algorithm_path, report_path, contract_path])

    docs['05_current_two_date_statistics.md'] = document('Current two-date candidate areas', f'''
Scope: 2024-08-28 → 2024-09-21 only. These values come from the active website
analysis report, using threshold {threshold} dB ({method['threshold_method']}).
They describe radar threshold classes and are not ground-truth water measurements.

| Observation/class | Area (km²) |
| --- | ---: |
| 2024-08-28 possible water | {area('before_water_km2')} |
| 2024-09-21 possible water | {area('after_water_km2')} |
| Dark blue, possible water on both dates | {area('persistent_water_km2')} |
| Light blue, possible new water | {area('new_water_km2')} |
| Orange, stronger-return transition to check | {area('lost_water_km2')} |
| Later minus baseline class area | {area('net_water_change_km2')} |
| Common valid comparison area | {area('common_valid_km2')} |

Why is the August candidate area larger? The measured statement is that more
pixels met this radar classification in August. That does not demonstrate that
true water extent decreased. The baseline may already contain water; smooth soil,
registration, mixed pixels, vegetation, and threshold choice can affect classes.
The dataset has no independent same-date water labels establishing the cause.

Independent ±1 dB thresholds on each date give possible-new-water areas between
{sensitivity['new_water_min_km2']:.4f} and {sensitivity['new_water_max_km2']:.4f} km².
This is a settings sensitivity check, not accuracy or a statistical confidence
interval; actual flooding can lie outside the interval. Other date pairs have no
computed candidate areas. The current page's selected dates determine applicability.
''', [report_path])

    limits = '\n'.join(f'- {limitation}' for limitation in report['limitations'])
    docs['06_uncertainty_and_missing_evidence.md'] = document('Uncertainty and missing evidence', f'''
The project status is `{report['status']}`. Observation facts include acquisition
metadata, calibrated backscatter, pixel-class transitions, and computed class areas.
Interpreting those as inundation, recession, land cover, or damage remains a hypothesis.

No independent same-date ground-truth water map is supplied. The current knowledge
and analysis do not establish flood depth, flood duration, peak water level,
casualties, affected population, building damage, crop type, crop loss, or a
validated farmland boundary. No model accuracy/IoU/F1 is available. The four image
dates do not determine when each pixel flooded or dried. The background basemap
is visual context; its image date is not supplied as validation of these SAR dates.

Analysis report limitations:
{limits}

Smooth bare soil, roads and radar shadow can resemble water; flooding under vegetation
or in built-up areas can be missed. Changing the threshold alone cannot prove the
classification is accurate or justify a flood extent chosen to reach an expected area.
Deciding whether orange is farmland damage still needs independent water, farmland or
field evidence from matching dates. This knowledge base does not invent external
literature or external validation results.
''', [report_path, manifest_path])
    return docs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=PROJECT)
    parser.add_argument('--dataset-root', type=Path, default=Path('/home/grad/zqin/datasets/hackathon'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--check', action='store_true', help='Exit 1 if generated documents need refreshing; do not write')
    args = parser.parse_args()
    project = args.project_root.resolve()
    output = args.output_dir or project / 'knowledge/generated'
    try:
        documents = build_documents(project, args.dataset_root)
        stale = [name for name, content in documents.items()
                 if not (output / name).is_file() or (output / name).read_text(encoding='utf-8') != content]
        if args.check:
            if stale:
                print('Stale generated knowledge: ' + ', '.join(stale), file=sys.stderr)
                return 1
            print(f'Verified {len(documents)} generated knowledge documents against their current sources.')
            return 0
        output.mkdir(parents=True, exist_ok=True)
        for name in stale:
            target = output / name
            temporary = target.with_suffix('.md.tmp')
            temporary.write_text(documents[name], encoding='utf-8')
            temporary.replace(target)
        print(f'Refreshed {len(stale)} of {len(documents)} generated knowledge documents in {output}.')
        print('Rebuild the RAG index after refreshing or editing knowledge documents.')
        return 0
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        print(f'Knowledge refresh failed: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
