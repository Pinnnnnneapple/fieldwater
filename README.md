# fieldwater

Turn daily weather into a FAO-56 irrigation calendar: when to irrigate, how much water to apply, and why.

[![CI](https://github.com/Pinnnnnneapple/fieldwater/actions/workflows/ci.yml/badge.svg)](https://github.com/Pinnnnnneapple/fieldwater/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg)](pyproject.toml)

## Why

An ET0 number alone does not tell a cooperative or extension officer when a
field needs water. Crop development, soil storage, rainfall, and the irrigation
system determine the next application. `fieldwater` connects those steps in an
inspectable Python workflow that runs offline and has **no runtime dependencies**.

It serves extension officers, smallholder cooperatives, agronomy students, and
growers working with a weather station. Each day's output includes the water
balance and estimation flags, so an agronomist can check the recommendation.

## Features

- Daily and hourly FAO-56 Penman-Monteith, with documented supporting equations;
  Hargreaves-Samani and chapter 3 estimates for missing observations.
- 21 crop defaults plus regional variants, four-stage Kc curves, climate
  adjustment, JSON crop overrides, and nine representative soil textures.
- Root growth, available water, water stress, effective rain, drainage,
  configurable initial depletion, and a mass-conservation audit.
- Refill, fixed-depth, fixed-interval, deficit, and rainfed policies; application
  efficiency and daily system capacity; observed irrigation overrides.
- Historical + forecast simulation, the next irrigation event, CSV/JSON exports,
  and a single-file HTML report with SVG charts and light/dark styling.
- Published-example regressions and independent calculations, including
  Uccle/Brussels ET0 = 3.88026 mm/day. See [validation notes](docs/methodology.md#validation-and-source-discrepancies).

## Install

Python 3.10 or newer:

```bash
python -m pip install git+https://github.com/Pinnnnnneapple/fieldwater
fieldwater --version
```

From source:

```bash
git clone https://github.com/Pinnnnnneapple/fieldwater.git
cd fieldwater
python -m pip install -e .
```

For an offline checkout, run without installing:

```bash
PYTHONPATH=src python3 -m fieldwater --help
```

The package is not claimed to be
published on PyPI.

## Quickstart

The example has deterministic synthetic daily weather from May through September
2025 at 40°N and 300 m. It is an educational example, not a field recommendation.

```bash
fieldwater schedule examples/weather_demo.csv \
  --site examples/site_demo.json --crop maize --planting 2025-05-01 --soil loam \
  --html report.html --csv daily.csv --json summary.json
```

Actual output from this checkout:

```text
Irrigation calendar (simulated; verify locally)
Date          Net (mm)  Gross (mm)
2025-07-05     117.28      156.37
2025-07-31     126.64      168.86
2025-09-13     152.87      203.82

Season summary: Maize (grain) / Loam (150 days)
ETc: 668.74 mm; ETc adjusted: 668.74 mm
Rain: 361.50 mm; effective rain: 289.20 mm
Irrigation net/gross: 396.79 / 529.05 mm
Deep percolation: 55.12 mm; stress days: 0
Relative yield (Ky approximation): 1.000
Water balance residual: -5.684e-14 mm
```

Net is water entering the modeled soil; gross accounts for the default 0.75
efficiency. This unconstrained example uses a deep mature root zone and allows
large applications. Set `--max-mm-day 30` to limit the system to 30 **gross**
mm/day, and supply locally appropriate roots through `--crop-file`.
The [committed report](examples/output/maize_schedule.html),
[daily ledger](examples/output/maize_schedule.csv), and
[summary](examples/output/maize_schedule.json) contain the same results.

### ET0, including temperature-only files

```bash
fieldwater et0 examples/weather_demo.csv --lat 40 --alt 300 -o et0.csv
fieldwater et0 examples/weather_temperature_only.csv \
  --site examples/site_demo.json --method hargreaves -o temperature-et0.csv
fieldwater et0 examples/weather_temperature_only.csv \
  --site examples/site_demo.json --method pm -o estimated-pm-et0.csv
```

The last command prints:

```text
Wrote 153 daily ET0 estimates to estimated-pm-et0.csv (method: pm).
Flags: humidity_estimated_tmin_ko, radiation_estimated_temperature, rh_min_estimated, wind_estimated_2m_s
```

PM remains PM when explicitly requested: it estimates humidity, radiation, and
wind and records those choices. Hargreaves has its own method flag. Check the
[weather contract and unit options](docs/data-sources.md#csv-contract).

### Management and next-event advice

```bash
fieldwater schedule examples/weather_demo.csv --site examples/site_demo.json \
  --crop maize --planting 2025-05-01 --soil loam \
  --strategy refill --mad 0.5 --efficiency 0.9 --max-mm-day 30

fieldwater next examples/weather_demo.csv --site examples/site_demo.json \
  --crop maize --planting 2025-05-01 --soil loam --as-of 2025-07-01
```

Actual next-event output:

```text
Forecast advice after 2025-07-01 (weather through 2025-09-30)
Next irrigation: 2025-07-05; net 117.28 mm; gross 156.37 mm
```

This command replays synthetic data to demonstrate the interface. For actual
advice, concatenate observed history with a forecast, and set `--as-of` to the
last observed day. Alternatively, supply an `is_forecast` column; without either,
the command uses today's date. Historical applications are simulated unless an
`irrigation_net` column supplies observations (including zeros). Advice is limited
to the supplied weather/crop horizon.

| Strategy | Additional options |
| --- | --- |
| `refill` | Refill to field capacity at adjusted RAW, or at `--mad` |
| `fixed` | `--fixed-depth 25`: net mm each time the trigger is reached |
| `interval` | `--interval 7 --fixed-depth 25`: starts on planting day, even if wet |
| `deficit` | `--deficit-fraction 0.9`: target 90% of volumetric field capacity |
| `none` | Rainfed comparison or observed-irrigation replay |

`--rain-method fixed --rain-fraction 0.8` is the default.
`--rain-method scs` apportions a monthly USDA-SCS estimate to daily rain and flags
partial months. It uses the whole supplied month, so fixed rain is preferable
when retrospective monthly apportionment would be inappropriate. Climate-adjusted
Kc endpoints similarly use available stage means; `--no-climate-adjustment` uses
the tabulated endpoints. See [timing and assumptions](docs/methodology.md).

## Use as a library

```python
from datetime import date
from fieldwater.balance import ScheduleConfig, run_schedule, next_irrigation
from fieldwater.crops import get_crop
from fieldwater.io import load_site, load_weather
from fieldwater.soils import get_soil

result = run_schedule(
    load_weather("examples/weather_demo.csv"),
    load_site("examples/site_demo.json"),
    get_crop("maize"), get_soil("loam"), date(2025, 5, 1),
    ScheduleConfig(efficiency=0.9, mad=0.5, max_mm_day=30),
)
assert abs(result.summary["balance_error"]) < 1e-9
event = next_irrigation(result, date(2025, 7, 1))
if event:
    print(event["date"], event["irrigation_net"], event["irrigation_gross"])
```

Low-level equations are independent public functions:

```python
from datetime import date
from fieldwater.et0 import calculate_daily_et0, atmospheric_pressure

print(round(atmospheric_pressure(1800), 1))  # 81.8 kPa
estimate = calculate_daily_et0(
    {"date": date(2025, 7, 6), "tmax": 21.5, "tmin": 12.3,
     "rh_max": 84, "rh_min": 63, "wind": 10 / 3.6, "sunshine_hours": 9.25},
    latitude=50.8, altitude=100, wind_height=10,
)
print(round(estimate["et0"], 2))  # 3.88 mm/day
```

All public functions document units. `calculate_daily_et0` accepts latitude in
degrees; `extraterrestrial_radiation` takes radians. Hourly ET0 and monthly soil
heat flux are library APIs; the scheduler and CLI operate on daily data.

## Reference tables and custom crops

```bash
fieldwater crops
fieldwater soils
fieldwater schedule examples/weather_demo.csv --site examples/site_demo.json \
  --crop-file examples/crop_custom.json --planting 2025-05-01 --soil loam
```

Crop defaults include maize, spring/winter wheat, rice, soybean, potato, tomato,
cotton, sugarcane, alfalfa, sorghum, barley, sunflower, groundnut, onion, cabbage,
lettuce, pepper, citrus, grapes, and olive. Variants include arid/humid maize,
frozen-soil winter wheat, tropical soybean, ratoon sugarcane, and wine grapes.
See the [full tables and provenance](docs/reference-tables.md) for the chosen
climates, ranges, and Ky availability. Verify against the paper and local practice.

Custom JSON uses `key`, `name`, `kc_ini`, `kc_mid`, `kc_end`, `height`, `zr_min`,
`zr_max`, `p`, and `stages: [initial, development, mid, late]`. Optional `ky`,
`stage_source`, and `notes` document local parameters. Heights/roots are metres;
Kc and p are dimensionless. `ky: null` withholds yield estimation. The
[example custom crop](examples/crop_custom.json) illustrates root overrides.

## Methodology

FAO-56 daily Penman-Monteith (eq. 6):

```text
ET0 = [0.408 Δ (Rn−G) + γ 900 u2 (es−ea)/(T+273)] / [Δ + γ(1+0.34u2)]
ETc = Kc ET0                       ETc,adj = Ks Kc ET0
TAW = 1000 (θFC−θWP) Zr             RAW = p TAW
Dr,end = Dr,previous + Dgrowth − Pe − Inet − CR + ETc,adj + DP
```

The model evaluates stress after morning water supply and checks every daily
and season balance. `Dgrowth` accounts for deficit in newly rooted soil. The
[equation reference](docs/methodology.md) lists all equation numbers, numerical
policies, management semantics, and validation sources.

Reference: Allen, Pereira, Raes & Smith (1998), *FAO Irrigation and Drainage
Paper 56*, [official full text](https://www.fao.org/4/x0490e/x0490e00.htm).
Seasonal Ky values follow FAO-33 as reproduced in FAO-56 Table 24.

## Exit codes

| Code | Meaning | Examples |
| --- | --- | --- |
| 0 | Success | Calculation, table listing, help, no event within forecast horizon |
| 2 | Usage or IO error | Unknown argument, missing file, missing site latitude, unwritable output |
| 3 | Data error | Missing temperatures, date gaps, invalid humidity, unknown crop, invalid efficiency |

## Limitations and disclaimer

This is decision support for planning and education. Calibrate locally and use
field observations and qualified agronomic judgment for operational decisions.
The software carries no guarantee of crop performance or water delivery.

- Crop and soil tables are starting values. Table 22's root-depth bounds describe
  maximum effective rooting ranges; treating the lower bound as the initial root
  depth is a provisional assumption. Perennials need established-root settings.
- Rice table values are included, but the root-zone approximation has no ponded
  water storage or seepage model. It does not provide operational paddy scheduling.
- Alfalfa uses one cutting curve; repeated cutting cycles need separate runs.
  Its seasonal Ky is listed, but cutting-specific yield estimates are withheld.
- Single-Kc stress combines soil evaporation and transpiration. There is no
  dual-Kc, frozen-soil, snow, salinity, nutrient, multilayer, infiltration-rate,
  or groundwater-depth model. Capillary rise must be supplied if relevant.
- Effective-rain formulas, stage means, and daily timing can influence advice.
  Forecast uncertainty is not propagated. Missing rain is flagged as assumed zero.
- Relative yield is a bounded seasonal Ky approximation, withheld for partial
  seasons and crops without a selected supported Ky. It ignores stress timing.
- The requested 14.5 MJ/m²/day radiation value uses Rio's May geometry, not
  20°S on 3 September. Both are tested correctly. The Bangkok monthly ET0 example
  is skipped because its exact inputs were not established.

## Development and roadmap

```bash
python -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m pytest -q
```

The suite covers published examples, independent scalar equations, monotonic
responses, polar geometry, unit conversions, mass conservation, strategies,
forecast advice, escaped HTML, and direct `main(argv)` calls. CI spans Python
3.10–3.14 on Linux, Windows, and macOS. Only the local Python interpreter was
executed during initial development; CI verifies the other combinations.

Planned extensions: dual-Kc soil evaporation, measured soil-moisture assimilation,
cutting cycles and established perennial roots, ponded rice, uncertainty-aware
forecast advice, and additional independently verified worked examples.

Read [CONTRIBUTING.md](CONTRIBUTING.md) to contribute. Code is available under
the [MIT license](LICENSE), copyright © 2026 fieldwater contributors.
