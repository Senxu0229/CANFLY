# Uncertainty and missing evidence / 不确定性与证据缺口

The project status is `exploratory-unvalidated`. Observation facts include acquisition
metadata, calibrated backscatter, pixel-class transitions, and computed class areas.
Interpreting those as inundation, recession, land cover, or damage remains a hypothesis.
中文：观测事实是雷达回波与候选类别变化；洪水成因、退水和农田损毁属于未核实推测。

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

中文：平滑裸地、道路、雷达阴影可能像水；植被覆盖或城市中的淹水可能漏检。
只改阈值不能证明分类准确，也不能为了得到预期面积而宣称洪灾范围。要判断橙色是否农田损毁，
仍缺少相应日期的独立水体、农田或现场证据。本知识库没有虚构外部文献或外部验证结果。

## Verified local sources / 本地来源

- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
- `public/observations/manifest.json`; SHA256 `e59702c175c0f1ec75cb04253078f1727eeda88932dc26973ded4f40193532e9`.
