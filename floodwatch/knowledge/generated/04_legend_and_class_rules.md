# Map legend and class meanings

FAQ: What does orange mean? Is orange damaged farmland? What do light blue and dark blue represent?

These classes describe the ordered 2024-08-28 → 2024-09-21 pair, using a shared
threshold of -12.40234375 dB and the small-patch cleanup described in the method.

- Light blue / cyan: “Possible new water”, class 3. The pixel is outside
  the cleaned baseline low-return mask and inside the later low-return mask.
  It is possible new water, not confirmed inundation or attributable flood damage.
- Dark blue: “Possible water on both dates”, class 2. The pixel is inside
  both cleaned low-return masks. It does not establish permanent water or when flooding began.
- Orange: “Other changes to check”, class 4. The pixel is inside the
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

## Verified local sources

- `scripts/analyze_water.py`; SHA256 `546dc6b0a2691bd003428e8771afe20b43c14dee9324acc837196f76b1b55633`.
- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
- `shared/water_classes.json`; SHA256 `65535eb26c215b45b3397f8533e0d3b0fcb02d66b54944c0855b89dbdecf2196`.
