// Shapes of the files in public/data/. Keep in sync with DATA_CONTRACT.md.

export type Bounds = [number, number, number, number]; // [west, south, east, north]

export interface Pass {
  date: string; // ISO yyyy-mm-dd
  scene_id: string;
  days_since_event: number;
}

export interface PassKpis {
  date: string;
  flood_water_ha: number;
  cropland_flooded_ha: number;
  buildings_in_water: number;
  places_still_flooded: number;
}

export interface Manifest {
  schema_version: string;
  mock?: boolean;
  generated_at: string;
  event: { name: string; date: string };
  aoi: { name: string; bounds: Bounds };
  passes: Pass[];
  layers: {
    flood_duration: {
      type: 'image';
      url: string;
      bounds: Bounds;
      legend: { min_days: number; max_days: number; colors: string[] };
    };
    water: { type: 'image'; url_template: string; bounds: Bounds };
    /** Grey radar backscatter image per pass (optional). */
    radar?: { type: 'image'; url_template: string; bounds: Bounds; dates: string[]; legend: { min_db: number; max_db: number } };
  };
  /** Context datasets such as rainfall (optional). */
  aux_layers?: AuxLayer[];
  grid?: { width: number; height: number; pixel_m: number; observed_share: number };
  units_source?: string;
  kpis_by_pass: PassKpis[];
  credit: string;
}

export interface AuxLayer {
  id: string;
  name: string;
  unit: string;
  bounds: Bounds;
  legend: { min: number; max: number; colors: string[] };
  items: { date: string | null; url: string }[];
  note?: string;
}

export type UnitKind = 'settlement' | 'cropland' | 'area';

export interface UnitProps {
  id: string;
  name: string;
  type: UnitKind;
  lga: string;
  area_ha: number;
  centroid: [number, number];
  water_ha_by_pass: number[];
  flooded_days: number;
  buildings_total: number;
  buildings_in_water_by_pass: number[];
  cropland_ha: number;
  cropland_flooded_ha_by_pass: number[];
  /** Mean of each context dataset over this place, one value per pass (id -> series). */
  aux?: Record<string, (number | null)[]>;
}

export interface UnitFeature {
  type: 'Feature';
  geometry: { type: 'Polygon'; coordinates: number[][][] };
  properties: UnitProps;
}

export interface UnitCollection {
  type: 'FeatureCollection';
  features: UnitFeature[];
}

export interface Weights {
  water: number;
  buildings: number;
  cropland: number;
  duration: number;
}

export type DryEstimate =
  | { kind: 'never'; label: string }
  | { kind: 'cleared'; date: string; label: string }
  | { kind: 'estimate'; date: string; label: string }
  | { kind: 'stalled'; label: string };

export interface RankedUnit {
  props: UnitProps;
  feature: UnitFeature;
  rank: number;
  score: number; // 0..1
  waterNow: number;
  buildingsNow: number;
  croplandNow: number;
  floodedNow: boolean;
  dry: DryEstimate;
}
