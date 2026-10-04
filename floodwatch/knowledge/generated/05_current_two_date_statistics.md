# Current two-date candidate areas / 当前两期疑似水体面积

Scope: 2024-08-28 → 2024-09-21 only. These values come from the active website
analysis report, using threshold -12.40234375 dB (pooled two-date Otsu).
They describe radar threshold classes and are not ground-truth water measurements.

| Observation/class / 观测或类别 | Area (km²) |
| --- | ---: |
| 2024-08-28 possible water / 灾前疑似水体 | 24.5950 |
| 2024-09-21 possible water / 灾后疑似水体 | 20.0398 |
| Dark blue, possible water on both dates / 深蓝 | 18.3177 |
| Light blue, possible new water / 浅蓝疑似新增 | 1.7221 |
| Orange, stronger-return transition to check / 橙色待核查 | 6.2773 |
| Later minus baseline class area / 两期候选类别面积差 | -4.5552 |
| Common valid comparison area / 共同有效范围 | 113.1036 |

Why is the August candidate area larger? The measured statement is that more
pixels met this radar classification in August. That does not demonstrate that
true water extent decreased. The baseline may already contain water; smooth soil,
registration, mixed pixels, vegetation, and threshold choice can affect classes.
The dataset has no independent same-date water labels establishing the cause.
中文：八月候选类别更大不等于真实洪水变少，原因证据不足，不能倒推为已确认退水。

Independent ±1 dB thresholds on each date give possible-new-water areas between
1.1640 and 2.6530 km².
This is a settings sensitivity check, not accuracy or a statistical confidence
interval; actual flooding can lie outside the interval. Other date pairs have no
computed candidate areas. The current page's selected dates determine applicability.

## Verified local sources / 本地来源

- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
