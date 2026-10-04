"""Class identifiers and legend shared by analysis, export, map and assistant."""
import json
from pathlib import Path
CONTRACT = json.loads((Path(__file__).resolve().parents[1] / 'shared/water_classes.json').read_text())
CODES = {item['key']: item['code'] for item in CONTRACT['classes']}
assert sorted(CODES.values()) == list(range(5)), 'The raster format requires codes 0 through 4'
