"""Trusted current-map context, reconstructed from server-side exports every request."""
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode


def local_asset(root, url):
    path = (root/'public'/url).resolve()
    if not path.is_relative_to((root/'public/observations').resolve()) or not path.is_file():
        raise ValueError('Analysis reference is not an available local observation asset')
    return path


def map_context(settings, left_id, right_id, view_mode='compare'):
    manifest = json.loads((settings.root/'public/observations/manifest.json').read_text())
    observations = {item['id']: item for item in manifest['observations']}
    if left_id not in observations or right_id not in observations or left_id == right_id:
        raise ValueError('Select two distinct, available observation dates')
    if view_mode not in ('before', 'compare', 'after', 'change'):
        raise ValueError('Unknown map view')
    contract = json.loads((settings.root/'shared/water_classes.json').read_text())
    context = {'study_area': manifest['aoi']['name'],
        'source_platform': manifest.get('credit', '').split(':', 1)[0].strip(),
        'source_credit': manifest.get('credit', ''),
        'center': {'longitude_degrees_east': manifest['aoi']['center'][0],
                   'latitude_degrees_north': manifest['aoi']['center'][1]},
        'radius_m': manifest['aoi']['radius_m'], 'view_mode': view_mode,
        'left_observation': observations[left_id], 'right_observation': observations[right_id],
        'available_dates': [o['date'] for o in manifest['observations']],
        'event_reference': manifest['event'], 'legend': contract['classes'],
        'analysis_available_for_selected_pair': False,
        'analysis_note': 'No water-change statistics for this ordered pair. Images only; do not infer areas from previews.',
        'source': 'public/observations/manifest.json'}
    if manifest.get('analysis_url'):
        path = local_asset(settings.root, manifest['analysis_url'])
        report = json.loads(path.read_text())
        if report['dates'] == [left_id, right_id]:
            a = report['areas']
            if not all(isinstance(v,(int,float)) and math.isfinite(v) and (k == 'net_water_change_km2' or v >= 0) for k,v in a.items()):
                raise ValueError('Active analysis contains invalid areas')
            if a['persistent_water_km2'] + a['new_water_km2'] + a['lost_water_km2'] > a['common_valid_km2'] + .00001:
                raise ValueError('Candidate classes exceed valid coverage')
            if (report.get('status') != 'exploratory-unvalidated'
                or abs(a['before_water_km2'] + a['new_water_km2'] - a['lost_water_km2'] - a['after_water_km2']) > .00001
                or abs(a['before_water_km2'] - a['persistent_water_km2'] - a['lost_water_km2']) > .00001
                or abs(a['net_water_change_km2'] - a['new_water_km2'] + a['lost_water_km2']) > .00001):
                raise ValueError('Active analysis is inconsistent; rebuild the observation export')
            context.update({'analysis_available_for_selected_pair': True,
                'analysis_note': 'Radar threshold candidates only, not independently confirmed water or flood damage.',
                'analysis_dates': report['dates'], 'method': report['method'],
                'area_calculation': {'grid_pixel_area_m2': report['pixel_size_m'] ** 2,
                    'new_candidate_pixel_count': round(a['new_water_km2'] * 1e6 / report['pixel_size_m'] ** 2),
                    'new_area_formula': 'class-3 pixel count × pixel area / 1,000,000 = km²; later candidate area minus BOTH-DATES candidate area, not later minus earlier total.'},
                'candidate_areas_km2': {'possible_water_left': a['before_water_km2'],
                    'possible_water_right': a['after_water_km2'], 'possible_water_both_dates': a['persistent_water_km2'],
                    'possible_new_water_light_blue': a['new_water_km2'], 'brighter_return_orange_check_cause': a['lost_water_km2'],
                    'net_candidate_class_change': a['net_water_change_km2'], 'valid_study_area': a['common_valid_km2']},
                'threshold_sensitivity_not_confidence_interval': report['sensitivity'],
                'limitations': report['limitations'],
                'analysis_source': path.name, 'analysis_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            # Keep numeric scenarios out of the model prompt; expose the summary only.
            context['threshold_sensitivity_not_confidence_interval'] = {k:v for k,v in report['sensitivity'].items() if k != 'scenarios'}
            context['method'] = {k:v for k,v in report['method'].items() if k not in ('threshold_selection', 'otsu_separability')}
    return context


def map_citation(context, left_id, right_id, view_mode):
    center = context['center']
    lines = [f"{context['study_area']}: longitude {center['longitude_degrees_east']}° E, latitude {center['latitude_degrees_north']}° N; radius {context['radius_m']} m.",
        f"Source platform: {context['source_platform']}. Selected dates: {context['left_observation']['date']} → {context['right_observation']['date']}.", context['analysis_note']]
    if context['analysis_available_for_selected_pair']:
        areas = context['candidate_areas_km2']
        lines.append(f"Possible new water: {areas['possible_new_water_light_blue']:.4f} km²; possible water on both dates: {areas['possible_water_both_dates']:.4f} km²; orange areas to check: {areas['brighter_return_orange_check_cause']:.4f} km².")
        lines.append(f"Shared threshold: {context['method']['threshold_db']} dB. Source: {context['analysis_source']}.")
    return {'id': 'MAP', 'title': 'Current map · manifest.json / active analysis report',
        'url': '/api/context?' + urlencode({'left_id':left_id,'right_id':right_id,'view_mode':view_mode}),
        'excerpt': '\n'.join(lines)}
