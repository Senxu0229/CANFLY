# Satellite and source observations / 卫星与原始数据

常见问题 / FAQ: 拍摄卫星是哪一个？用的是什么卫星和波束模式？
English FAQ: Which satellite or spacecraft acquired these images? What radar sensor, beam mode and polarization do we use?

The four local source products are RADARSAT-2 SAR (synthetic aperture radar),
SLC (single look complex). These are radar measurements, not visible-light colour
photographs. All four source XML files identify beam mode XF0W2, HH polarization,
and Descending orbit direction. 中文：卫星是 RADARSAT-2，合成孔径雷达 SAR，
HH 极化，XF0W2 波束，降轨。相同模式不等于已经验证水体分类准确。

- 2024-08-28: 2024-08-28T04:54:34.419140Z (UTC raw-data start); XF0W2, HH, Descending.
  Product: `RS2_OK158812_PK1444889_DK1409105_XF0W2_20240828_045434_HH_SLC`.
- 2024-09-21: 2024-09-21T04:54:35.747349Z (UTC raw-data start); XF0W2, HH, Descending.
  Product: `RS2_OK158812_PK1444898_DK1409114_XF0W2_20240921_045435_HH_SLC`.
- 2024-10-15: 2024-10-15T04:54:36.591113Z (UTC raw-data start); XF0W2, HH, Descending.
  Product: `RS2_OK158813_PK1444906_DK1409122_XF0W2_20241015_045436_HH_SLC`.
- 2024-11-08: 2024-11-08T04:54:36.529351Z (UTC raw-data start); XF0W2, HH, Descending.
  Product: `RS2_OK158813_PK1444914_DK1409130_XF0W2_20241108_045436_HH_SLC`.

Times above are `rawDataStartTime`, matching the website's `acquisition_utc`.
The XML first-image-line zero-Doppler time is a different metadata field.
No additional satellite or observation dates are available in this active manifest.

## Verified local sources / 本地来源

- `/home/grad/zqin/datasets/hackathon/RS2_OK158812_PK1444889_DK1409105_XF0W2_20240828_045434_HH_SLC/product.xml`; SHA256 `afc7c53addfd733e62d687c3c22ff0397d3b9a6c1bf318f204660268a829abaa`.
- `/home/grad/zqin/datasets/hackathon/RS2_OK158812_PK1444898_DK1409114_XF0W2_20240921_045435_HH_SLC/product.xml`; SHA256 `7905e370bd62cb9338bbe0a726ec10acb9d3ae2a566eabdab46675e2c2bb17ce`.
- `/home/grad/zqin/datasets/hackathon/RS2_OK158813_PK1444906_DK1409122_XF0W2_20241015_045436_HH_SLC/product.xml`; SHA256 `fb356e94009208c2a748b4210fc6decb032fc92b17a39a4cb9a4025cac48ac6c`.
- `/home/grad/zqin/datasets/hackathon/RS2_OK158813_PK1444914_DK1409130_XF0W2_20241108_045436_HH_SLC/product.xml`; SHA256 `6645b2568d405b6b9b4098a666880b772539a2f9bfc4920f91ffef1facb522a9`.
