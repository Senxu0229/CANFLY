from pathlib import Path
import csv,json,warnings
import pyogrio,shapely
from pyogrio.raw import read
from shapely.geometry import Point,mapping
from shapely.ops import transform,unary_union
from pyproj import Transformer
warnings.filterwarnings('ignore',category=RuntimeWarning)
root=Path(__file__).resolve().parents[1]; db=str(root/'data/FL20240902NGA.gdb')
fwd=Transformer.from_crs(4326,32633,always_xy=True).transform
back=Transformer.from_crs(32633,4326,always_xy=True).transform
point=transform(fwd,Point(13.28467,11.73678))
layers=[n for n,t in pyogrio.list_layers(db) if t]
(root/'analysis/layers.json').write_text(json.dumps([{'layer':n,'geometry':t,'features':pyogrio.read_info(db,layer=n)['features']} for n,t in pyogrio.list_layers(db)],indent=2))
rows=[]; features=[]
for n in layers:
 if 'MaximumFloodExtent' not in n: continue
 m,f,g,a=read(db,layer=n)
 geo=shapely.make_valid(unary_union([shapely.from_wkb(x) for x in g]))
 cloudname=n.replace('MaximumFloodExtent','CloudObstruction')
 cloud=None
 if cloudname in layers:
  _,_,cg,_=read(db,layer=cloudname)
  cloud=shapely.make_valid(unary_union([shapely.from_wkb(x) for x in cg]))
 attrs={k:str(v[0]) for k,v in zip(m['fields'],a)}
 for radius in [2000,5000]:
  buf=point.buffer(radius,quad_segs=128); ll=transform(back,buf)
  clip=transform(fwd,geo.intersection(ll)); ca=transform(fwd,cloud.intersection(ll)).area if cloud is not None else None
  rows.append({'layer':n,'radius_km':radius/1000,'buffer_km2':buf.area/1e6,'mapped_flood_km2':clip.area/1e6,'percent_buffer_mapped_flood':clip.area/buf.area*100,'cloud_obstructed_km2':None if ca is None else ca/1e6,'field_validation':attrs.get('Field_Validation'),'sensor_date':attrs.get('Sensor_Date')})
  if radius==5000: features.append({'type':'Feature','properties':rows[-1],'geometry':mapping(transform(back,clip))})
with (root/'analysis/kalari_flood_summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(root/'analysis/kalari_flood_5km.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features}))
for r in rows: print(r)
