# How possible water is detected / 疑似水体识别方法

常见问题 / FAQ: 新增的水体是怎么判断出来的？如何计算水体面积？水体识别用什么阈值？

For the analysed 2024-08-28 → 2024-09-21 pair, ESA SNAP 14.0.0 read the
complete HH SLC products, calibrated linear sigma0 using the product sigma LUT,
and performed Range-Doppler terrain correction with SRTM elevation and EGM96
conversion. Calibration output spacing is 5 m in EPSG:32633.
Terrain radiometric normalization was not applied. Calibration alone does not
identify water.

The analysis uses EPSG:32633, a 10 m grid. It area-averages
linear power, then applies a 3 × 3 mean (30 m footprint), then converts to dB using
10 × log10(sigma0). It does not measure PNG brightness. Each date's candidate mask
is smoothed sigma0 HH strictly below the common threshold -12.40234375 dB
(approximately -12.4 dB), selected by pooled two-date Otsu.
Connected components with fewer than 9 pixels
are removed separately from each date using 8-neighbour connectivity.
Nine 10 m pixels are 900 m², or 0.09 hectares. Missing/outside-AOI pixels are excluded.

中文：先定标、地形校正、统一网格，再对线性功率平滑，转成 dB 后按阈值分类。
当前共同阈值是 -12.40234375 dB，低于它只表示疑似水体。统计依据是分析 TIFF，
不是网页 PNG 缩略图。疑似新增水体表示前期未满足水体候选条件、后期满足候选条件，
两期掩膜均已去除小斑块；并不是所有新增黑点都能确认为洪水。
每个分析像素为 10 × 10 = 100 平方米，类别面积 = 像素个数 × 100 平方米，
除以 1,000,000 转为平方公里。10 m 网格不代表独立的 10 m 空间分辨率。
Area = retained class pixel count × 100 m² / 1,000,000, expressed in km².
This is approximate ground area from UTM grid pixels, not a validated flood extent.

## Verified local sources / 本地来源

- `public/observations/analysis_report_7b1444e7f771.json`; SHA256 `ebd63f760b8b18e98f5d04bd1292867e1d020a2178976f985b8c29ea5c4dcf58`.
- `scripts/analyze_water.py`; SHA256 `546dc6b0a2691bd003428e8771afe20b43c14dee9324acc837196f76b1b55633`.
- `/home/grad/zqin/datasets/hackathon/kalari_abdu_analysis/calibration_info.json`; SHA256 `a9449cecca94e159051c5ed84e57996c6449dead32c9dbfd74fc65e3a07431d6`.
