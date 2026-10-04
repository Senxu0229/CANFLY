#!/usr/bin/env python3
"""Build the small public context file used by the timeline chart.

Inputs are public, non-RADARSAT data already in the CANFLY repository:
  * ../maiduguri_precip_aug_nov_2024.csv         30-minute rain rate (mm/hr), summed to daily mm
    (falls back to ../Kalari_Abdu_NASA_Rainfall_Daily_2024.csv, daily mm, if absent)
  * ../kalari-flood-study/data/flood_summary.csv  UNOSAT VIIRS 5-day maximum flood extent

Output: public/context/kalari_context.json (tracked; contains no RADARSAT-2 data).
Standard library only. Re-run after extending the rainfall export.
"""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--rain', default=None, type=Path, help='Rain CSV: 30-minute precip_rate_mm_per_hr or daily rainfall_mm')
    parser.add_argument('--viirs', default=REPO / 'kalari-flood-study/data/flood_summary.csv', type=Path)
    parser.add_argument('--viirs-radius-km', default=5, type=int, help='Which study radius from flood_summary.csv to use')
    parser.add_argument('--out', default=HERE / 'public/context/kalari_context.json', type=Path)
    parser.add_argument('--start', default='2024-08-01')
    parser.add_argument('--end', default='2024-11-15')
    args = parser.parse_args()

    rain_path = args.rain
    if rain_path is None:
        rain_path = REPO / 'maiduguri_precip_aug_nov_2024.csv'
        if not rain_path.exists():
            rain_path = REPO / 'Kalari_Abdu_NASA_Rainfall_Daily_2024.csv'
    totals, counts = {}, {}
    with rain_path.open(newline='') as handle:
        reader = csv.DictReader(handle)
        half_hourly = 'precip_rate_mm_per_hr' in (reader.fieldnames or [])
        for row in reader:
            day = row['date'][:10]
            if half_hourly:
                value = float(row['precip_rate_mm_per_hr'] or 0) * 0.5   # mm/hr over 30 minutes -> mm
                counts[day] = counts.get(day, 0) + 1
            else:
                value = float(row['rainfall_mm'])
            totals[day] = totals.get(day, 0.0) + value
    if half_hourly:
        partial = sorted(day for day, n in counts.items() if n != 48)
        for day in partial:          # never show a partial day as a full daily total
            del totals[day]
        if partial:
            print('Skipped incomplete days:', ', '.join(partial))
    days = sorted([day, round(mm, 2)] for day, mm in totals.items() if args.start <= day <= args.end)
    if not days:
        raise SystemExit('No rainfall rows found')

    periods = []
    with args.viirs.open(newline='') as handle:
        for row in csv.DictReader(handle):
            if int(float(row['radius_km'])) != args.viirs_radius_km:
                continue
            periods.append({'start': row['period_start'], 'end': row['period_end'],
                            'km2': round(float(row['mapped_flood_km2']), 3),
                            'cloud_km2': round(float(row['cloud_obstructed_km2'] or 0), 3)})
    periods.sort(key=lambda item: item['start'])
    if not periods:
        raise SystemExit('No VIIRS periods found for that radius')

    out = {
        'schema_version': '1.0',
        'domain': [args.start, args.end],
        'rain': {
            'label': 'Daily rainfall',
            'source': ('NASA satellite rainfall estimate for the Maiduguri area, 30-minute rates summed to daily totals (CANFLY repository)'
                       if half_hourly else 'NASA satellite rainfall estimate, exported from Google Earth Engine (CANFLY repository)'),
            'file': rain_path.name,
            'unit': 'mm/day',
            'coverage': [days[0][0], days[-1][0]],
            'days': days,
        },
        'viirs': {
            'label': 'Mapped flood area, 5-day maximum extent',
            'source': 'UNOSAT VIIRS flood product (375 m), FL20240902NGA',
            'radius_km': args.viirs_radius_km,
            'unit': 'km2',
            'periods': periods,
        },
        'caveat': 'Different sensors, resolutions and footprints from the radar analysis. Timing context only; not a validation of radar classes. No VIIRS detection does not prove dry ground.',
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + '\n')
    print(f'Wrote {args.out} from {rain_path.name} ({len(days)} rainfall days, {len(periods)} VIIRS periods)')


if __name__ == '__main__':
    main()
