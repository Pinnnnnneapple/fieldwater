# Crop and soil reference tables

These defaults support transparent planning. Verify the original FAO-56 tables,
their footnotes, cultivar, planting date, climate, ground cover, harvest state,
and local measurements before use. A value selected from a published range is
not a universal constant. Kc and p are dimensionless; height and roots are metres.

Sources: [Tables 11 and 12](https://www.fao.org/4/x0490e/x0490e0b.htm),
[Table 19](https://www.fao.org/4/x0490e/x0490e0c.htm),
[Tables 22 and 24](https://www.fao.org/4/x0490e/x0490e0e.htm).
Seasonal Ky comes from FAO-33 as reproduced in Table 24. A dash means no
supported single seasonal value was selected. In particular, citrus has a
published Ky range of 1.1–1.3; choose a locally justified value in a custom file.

## Crop defaults and regional variants

Stages are initial/development/mid/late days, in that order. Zr min/max are
Table 22 maximum-effective-depth bounds provisionally used for root growth;
these are not measured seedling depths. Adjust via a custom crop file.

| Key | Kc ini/mid/end | Height | Zr min/max | p at ETc=5 | Stages | Seasonal Ky |
| --- | --- | --- | --- | --- | --- | --- |
| `maize` | 0.3/1.2/0.35 | 2 | 1/1.7 | 0.55 | 30/40/50/30 | 1.25 |
| `wheat_spring` | 0.3/1.15/0.25 | 1 | 1/1.5 | 0.55 | 20/25/60/30 | 1.15 |
| `wheat_winter` | 0.7/1.15/0.25 | 1 | 1.5/1.8 | 0.55 | 30/140/40/30 | 1.05 |
| `rice` | 1.05/1.2/0.6 | 1 | 0.5/1 | 0.2 | 30/30/60/30 | — |
| `soybean` | 0.4/1.15/0.5 | 1 | 0.6/1.3 | 0.5 | 20/35/60/25 | 0.85 |
| `potato` | 0.5/1.15/0.75 | 0.6 | 0.4/0.6 | 0.35 | 25/30/45/30 | 1.1 |
| `tomato` | 0.6/1.15/0.8 | 0.6 | 0.7/1.5 | 0.4 | 30/40/45/30 | 1.05 |
| `cotton` | 0.35/1.2/0.5 | 1.5 | 1/1.7 | 0.65 | 30/50/60/55 | 0.85 |
| `sugarcane` | 0.4/1.25/0.75 | 3 | 1.2/2 | 0.65 | 35/60/190/120 | 1.2 |
| `alfalfa` | 0.4/1.2/1.15 | 0.7 | 1/2 | 0.55 | 10/20/20/10 | 1.1 |
| `sorghum` | 0.3/1.05/0.55 | 1.5 | 1/2 | 0.55 | 20/35/40/30 | 0.9 |
| `barley` | 0.3/1.15/0.25 | 1 | 1/1.5 | 0.55 | 20/25/60/30 | — |
| `sunflower` | 0.35/1.15/0.35 | 2 | 0.8/1.5 | 0.45 | 25/35/45/25 | 0.95 |
| `groundnut` | 0.4/1.15/0.6 | 0.4 | 0.5/1 | 0.5 | 25/35/45/25 | 0.7 |
| `onion` | 0.7/1.05/0.75 | 0.4 | 0.3/0.6 | 0.3 | 15/25/70/40 | 1.1 |
| `cabbage` | 0.7/1.05/0.95 | 0.4 | 0.5/0.8 | 0.45 | 40/60/50/15 | 0.95 |
| `lettuce` | 0.7/1/0.95 | 0.3 | 0.3/0.5 | 0.3 | 20/30/15/10 | — |
| `pepper` | 0.6/1.05/0.9 | 0.7 | 0.5/1 | 0.3 | 30/35/40/20 | 1.1 |
| `citrus` | 0.7/0.65/0.7 | 4 | 1.2/1.5 | 0.5 | 60/90/120/95 | — |
| `grapes` | 0.3/0.85/0.45 | 2 | 1/2 | 0.35 | 20/50/75/60 | 0.85 |
| `olive` | 0.65/0.7/0.7 | 4 | 1.2/1.7 | 0.65 | 30/90/60/90 | — |
| `maize_arid` | 0.3/1.2/0.35 | 2 | 1/1.7 | 0.55 | 25/40/45/30 | 1.25 |
| `maize_humid` | 0.3/1.2/0.35 | 2 | 1/1.7 | 0.55 | 20/35/40/30 | 1.25 |
| `wheat_winter_frozen` | 0.4/1.15/0.25 | 1 | 1.5/1.8 | 0.55 | 160/75/75/25 | 1.05 |
| `soybean_tropical` | 0.4/1.15/0.5 | 1 | 0.6/1.3 | 0.5 | 15/15/40/15 | 0.85 |
| `sugarcane_ratoon` | 0.4/1.25/0.75 | 3 | 1.2/2 | 0.65 | 25/70/135/50 | 1.2 |
| `grapes_wine` | 0.3/0.7/0.45 | 2 | 1/2 | 0.45 | 30/60/40/80 | 0.85 |

## Selected regions and qualifications

- `maize`: FAO-56 Table 11: Spain/California, April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Dry grain harvest: Kc_end=0.35 (Table 12 range 0.60-0.35).
- `wheat_spring`: FAO-56 Table 11: Barley/Oats/Wheat, 35-45 degrees latitude, March/April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Kc_end=0.25 selected from 0.25-0.40 for dry harvest.
- `wheat_winter`: FAO-56 Table 11: Mediterranean, November. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Non-frozen-soil Kc_ini; dry-harvest Kc_end=0.25 from 0.25-0.40.
- `rice`: FAO-56 Table 11: Tropics/Mediterranean, December/May. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. No sourced universal single seasonal Ky value; ky=None. Kc_end=0.60 selected from 0.90-0.60. Table 22 rice p=0.20 refers to saturation, not ordinary FC-WP depletion: a ponded-water balance is required. Initial Kc assumes standing water and subhumid moderate conditions (Table 14).
- `soybean`: FAO-56 Table 11: Central USA, May; development=35 from 30/35. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Height=1.0 m selected from Table 12 range 0.5-1.0 m.
- `potato`: FAO-56 Table 11: Continental climate, May. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `tomato`: FAO-56 Table 11: Mediterranean, April/May. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Kc_end=0.80 is a representative choice within Table 12 range 0.70-0.90.
- `cotton`: FAO-56 Table 11: Egypt/Pakistan/California, March-May. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Selected Kc_mid=1.20 (1.15-1.20), Kc_end=0.50 (0.70-0.50), height=1.5 m (1.2-1.5).
- `sugarcane`: FAO-56 Table 11: virgin crop, low latitudes. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `alfalfa`: FAO-56 Table 11: first cutting, California, January/April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Individual cutting-period Kc, not averaged-season Kc. Reset the curve at cutting; seasonal Ky=1.1 must not be interpreted as a cutting-specific Ky.
- `sorghum`: FAO-56 Table 11: USA/Pakistan/Mediterranean, May/June. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Kc_mid=1.05 and height=1.5 m represent Table 12 ranges 1.00-1.10 and 1-2 m. Stage components sum to 125 days; FAO HTML's total column says 130. The four listed components are retained without inventing a correction.
- `barley`: FAO-56 Table 11: Barley/Oats/Wheat, 35-45 degrees latitude, March/April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. No sourced universal single seasonal Ky value; ky=None. 
- `sunflower`: FAO-56 Table 11: Mediterranean/California, April/May. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Kc_mid=1.15 selected from Table 12 range 1.00-1.15.
- `groundnut`: FAO-56 Table 11: West Africa, dry season. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `onion`: FAO-56 Table 11: dry onion, Mediterranean, April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `cabbage`: FAO-56 Table 11: California desert, September. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `lettuce`: FAO-56 Table 11: Mediterranean, April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. No sourced universal single seasonal Ky value; ky=None. 
- `pepper`: FAO-56 Table 11: Europe/Mediterranean, April/June; initial=30 from 25/30. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `citrus`: FAO-56 Table 11: Mediterranean, January. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. No sourced universal single seasonal Ky value; ky=None. Table 24 Ky=1.1-1.3 is a range; no universal single value selected. Table 12 assumes 70% canopy and no active ground cover. Established roots do not reset annually; supply appropriate constant depths.
- `grapes`: FAO-56 Table 11: California, March. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Table/raisin coefficients and depletion fraction; wine grapes differ. Established roots do not reset annually.
- `olive`: FAO-56 Table 11: Mediterranean, March. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. No sourced universal single seasonal Ky value; ky=None. Height=4 m represents Table 12 range 3-5 m. Active-season coefficients; winter/off-season is not modeled. Table 12 footnote 24 also gives a different seasonal Spanish example. Established roots do not reset annually.
- `maize_arid`: FAO-56 Table 11: arid climate, December/January. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Dry grain harvest: Kc_end=0.35 (Table 12 range 0.60-0.35).
- `maize_humid`: FAO-56 Table 11: Nigeria (humid), June. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Dry grain harvest: Kc_end=0.35 (Table 12 range 0.60-0.35).
- `wheat_winter_frozen`: FAO-56 Table 11: Idaho, October. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Frozen-soil Kc_ini=0.40; dry-harvest Kc_end=0.25. Ky: FAO-56 Table 24 (FAO-33). Dormancy requires local stage adjustment.
- `soybean_tropical`: FAO-56 Table 11: tropics, December. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). Height=1.0 m selected from Table 12 range 0.5-1.0 m.
- `sugarcane_ratoon`: FAO-56 Table 11: ratoon, low latitudes. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Ky: FAO-56 Table 24 (FAO-33). 
- `grapes_wine`: FAO-56 Table 11: wine, mid latitudes, April. Root-growth assumption: Table 22 maximum-depth range used as initial/final depths; calibrate locally. Wine-grape Kc and p; height=2 m selected from 1.5-2 m. Ky=0.85 is Table 24's grape value, not a wine-specific calibration. Established roots do not reset annually.

## Representative soil values

Contents are volumetric fractions (m³/m³). These selected pairs fall within
Table 19 FC, WP, and FC−WP ranges; they are not measured site properties.
All calculations assume a uniform profile. Use `Soil` directly in the library
for measured values; the CLI selects the built-in textures.

| Key | theta FC | theta WP | Available water (mm/m) |
| --- | --- | --- | --- |
| `sand` | 0.12 | 0.04 | 80 |
| `loamy_sand` | 0.15 | 0.06 | 90 |
| `sandy_loam` | 0.24 | 0.11 | 130 |
| `loam` | 0.27 | 0.12 | 150 |
| `silt_loam` | 0.3 | 0.14 | 160 |
| `silt` | 0.32 | 0.14 | 180 |
| `silty_clay_loam` | 0.34 | 0.19 | 150 |
| `silty_clay` | 0.36 | 0.21 | 150 |
| `clay` | 0.36 | 0.22 | 140 |

## Important crop-specific conditions

Rice's p=0.20 is saturation-based and its Kc assumes ponding. The table is
included for reference; this release's root-zone-only model lacks paddy water
storage and seepage. Alfalfa is an individual cutting curve, while its Ky is
seasonal; cutting-specific yield output is withheld. Established orchard/vine
roots need local constant depths rather than an annual seedling-root reset.

For sorghum, the selected Table 11 stage components sum to 125 days while the
FAO HTML total column says 130. The four components are retained. Height and
Kc values selected from ranges are identified in each crop's notes.
