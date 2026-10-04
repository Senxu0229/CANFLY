# Uncertainty and missing evidence

The project status is `exploratory-unvalidated`. Observation facts include acquisition
metadata, calibrated backscatter, pixel-class transitions, and computed class areas.
Interpreting those as inundation, recession, land cover, or damage remains a hypothesis.

No independent same-date ground-truth water map is supplied. The current knowledge
and analysis do not establish flood depth, flood duration, peak water level,
casualties, affected population, building damage, crop type, crop loss, or a
validated farmland boundary. No model accuracy/IoU/F1 is available. The four image
dates do not determine when each pixel flooded or dried. The background basemap
is visual context; its image date is not supplied as validation of these SAR dates.

Analysis report limitations:
- Orange class means leaving the low-return class, not confirmed water recession. Net class-area change is not a measured change in water extent.
- Candidate open water only; no independent same-date ground-truth validation.
- Smooth bare soil, roads and radar shadows can resemble water; vegetation-covered or urban flooding may be missed.
- The shared threshold separates dark and bright radar returns, not semantic land cover. A histogram valley is not independent validation. Threshold sensitivity is not accuracy or a statistical confidence interval.
- 10 m grid spacing is not independent 10 m resolution: interpolation and 30 m smoothing affect shorelines and small features.
- Residual registration error and mixed shoreline pixels can create apparent changes. No image shift was fitted to changing water.
- The 28 August baseline may contain water; 21 September is not necessarily the flood peak. New water is not net water increase or attributable flood damage.
- Areas use UTM grid pixel area (approximately ground area); outside-AOI and missing pixels are excluded.

Smooth bare soil, roads and radar shadow can resemble water; flooding under vegetation
or in built-up areas can be missed. Changing the threshold alone cannot prove the
classification is accurate or justify a flood extent chosen to reach an expected area.
Deciding whether orange is farmland damage still needs independent water, farmland or
field evidence from matching dates. This knowledge base does not invent external
literature or external validation results.

## Verified local sources

- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
- `public/observations/manifest.json`; SHA256 `e59702c175c0f1ec75cb04253078f1727eeda88932dc26973ded4f40193532e9`.
