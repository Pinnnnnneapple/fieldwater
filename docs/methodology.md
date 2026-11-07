# Methodology and equation reference

The reference is Allen, R. G., Pereira, L. S., Raes, D. & Smith, M. (1998),
*Crop evapotranspiration: Guidelines for computing crop water requirements*,
FAO Irrigation and Drainage Paper 56, Rome, ISBN 92-5-104219-5.
[FAO full text](https://www.fao.org/4/x0490e/x0490e00.htm).

The implementation uses the short-grass FAO reference surface, a single crop
coefficient, and one uniform root-zone layer. Depths are mm, temperatures °C,
vapour pressures kPa, wind m/s, altitude/root depth m, and radiation MJ/m² per
calculation interval. Relative humidity is percent. Weather/site latitude is
degrees north; the low-level solar functions take radians. Internal arithmetic
retains full precision; terminal output rounds to two decimals.

## Reference evapotranspiration

The following equations are implemented separately in `fieldwater.et0`.
Δ is the saturation-pressure slope; δ is solar declination. They are different
variables. G is positive for heat flowing into the soil.

| FAO-56 equation | Implemented formula / function |
| --- | --- |
| 6 | `penman_monteith_daily`: ET0 = [0.408Δ(Rn−G) + γ·900·u2(es−ea)/(T+273)] / [Δ+γ(1+0.34u2)] |
| 7 | `atmospheric_pressure`: P = 101.3[(293−0.0065z)/293]^5.26 |
| 8 | `psychrometric_constant`: γ = 0.000665P |
| 9 | `mean_temperature`: T = (Tmax+Tmin)/2 |
| 10 | `relative_humidity`: RH = 100ea/e°(T) |
| 11 | `saturation_vapour_pressure`: e°(T) = 0.6108 exp[17.27T/(T+237.3)] |
| 12 | `mean_saturation_vapour_pressure`: es = [e°(Tmax)+e°(Tmin)]/2 |
| 13 | `slope_vapour_pressure_curve`: Δ = 4098e°(T)/(T+237.3)² |
| 14 | `actual_vapour_pressure_from_dewpoint`: ea = e°(Tdew) |
| 15–16 | `actual_vapour_pressure_from_wet_bulb`: ea = e°(Twet)−aP(Tdry−Twet), default aspirated a=0.000662 °C⁻¹ |
| 17 | `actual_vapour_pressure_from_rh`: ea = [e°(Tmin)RHmax+e°(Tmax)RHmin]/200 |
| 18 | `actual_vapour_pressure_from_rh_max`: ea = e°(Tmin)RHmax/100 |
| 19 | `actual_vapour_pressure_from_rh_mean`: ea = es·RHmean/100 |
| 20 | `radiation_to_evaporation`: equivalent evaporation = 0.408R |
| 21 | `extraterrestrial_radiation`: Ra = (1440/π)Gsc·dr[ωs sinφ sinδ+cosφ cosδ sinωs], Gsc=0.0820 |
| 22 | `latitude_radians`: φ = latitude·π/180 |
| 23 | `inverse_relative_distance_earth_sun`: dr = 1+0.033 cos(2πJ/365) |
| 24 | `solar_declination`: δ = 0.409 sin(2πJ/365−1.39) |
| 25 | `sunset_hour_angle`: ωs = acos(−tanφ tanδ), bounded for polar night/day |
| 28 | `extraterrestrial_radiation_hourly`: Ra = (720/π)Gsc·dr[(ω2−ω1)sinφ sinδ+cosφ cosδ(sinω2−sinω1)] |
| 29–30 | `solar_time_angle_bounds`: ω1,ω2 = ω ± π·duration/24 |
| 31 | `solar_time_angle`: ω = π[t+0.06667(Lz−Lm)+Sc−12]/12; low-level longitudes are degrees **west** |
| 32 | `seasonal_time_correction`: Sc = 0.1645sin(2b)−0.1255cos(b)−0.025sin(b), hours |
| 33 | `seasonal_correction_angle`: b = 2π(J−81)/364 |
| 34 | `daylight_hours`: N = 24ωs/π |
| 35 | `solar_radiation`: Rs = (as+bs·n/N)Ra; defaults as=0.25, bs=0.50 |
| 36 | `clear_sky_radiation`: Rso = (as+bs)Ra when calibrated coefficients supplied |
| 37 | `clear_sky_radiation`: Rso = (0.75+0.00002z)Ra otherwise |
| 38 | `net_shortwave_radiation`: Rns = (1−α)Rs; default α=0.23 |
| 39 | `net_longwave_radiation`: Rnl = σ[(Tmax,K⁴+Tmin,K⁴)/2](0.34−0.14√ea)(1.35Rs/Rso−0.35); σ=4.903×10⁻⁹, TK=T+273.16 |
| 40 | `net_radiation`: Rn = Rns−Rnl |
| 41 | `soil_heat_flux`: G = cs(T−Tprevious)·depth/interval; cs=2.1 MJ/m³/°C |
| 42 | `soil_heat_flux_daily`: G = 0 |
| 43 | `soil_heat_flux_monthly`: G = 0.07(Tnext−Tprevious) |
| 44 | `soil_heat_flux_monthly_previous`: G = 0.14(Tcurrent−Tprevious) |
| 45–46 | `soil_heat_flux_hourly`: G = 0.1Rn for Rn>0, otherwise 0.5Rn (or explicit day/night) |
| 47 | `wind_speed_2m`: u2 = uz·4.87/ln(67.8z−5.42); measured 2 m wind retained unchanged |
| 48 | `actual_vapour_pressure_from_tmin`: ea = e°(Tmin−Ko), Ko≥0; default 0 °C |
| 50 | `solar_radiation_from_temperature`: Rs = kRs√(Tmax−Tmin)Ra; 0.16 inland, 0.19 coastal, capped at Rso in daily API |
| 52 | `hargreaves`: ET0 = 0.0023(T+17.8)√(Tmax−Tmin)·**0.408Ra** when Ra is MJ/m²/day |
| 53 | `penman_monteith_hourly`: equation 6 with **37** replacing 900; radiation/G in MJ/m²/hour |
| 54 | `actual_vapour_pressure_hourly`: ea = e°(Thr)RHhr/100 |

Hourly solar intervals are clipped to sunrise/sunset and limited to one hour.
Hourly longwave uses σ/24 and the hourly temperature in both temperature slots.
The CLI and scheduler ingest **daily** weather; hourly calculations are a library
API. Monthly G functions are also library APIs; the scheduler uses daily G=0.

The longwave Rs/Rso ratio is capped above at 1. Low ratios (<0.3) and unusually
high humidity are flagged; the literal empirical equation is retained, including
possible negative longwave values outside its usual domain. At Rso=0 the low-level
function requires a cloudiness ratio. The daily API uses 0.5 for polar night and
flags that assumption. Polar-safe geometry does not establish crop-model validity
in polar climates. Low-level ET equations retain signed fluxes; daily scheduling
clips negative ET0 to zero and records the clipping.

## Missing observations (chapter 3)

Tmax and Tmin are mandatory for this daily workflow. A supplied Tmean is used
after checking that it lies within the extrema; otherwise their mean is used.
The humidity priority is Tdew, RHmax+RHmin, RHmax, RHmean, then Tmin−Ko. Missing
wind uses u2=2 m/s. Radiation priority is measured Rs, sunshine via Angstrom,
then temperature range via eq. 50. Each estimate has a daily flag. RHmin needed
for climate adjustment is inferred as 100ea/e°(Tmax) when absent and possible.
An isolated RHmin does not determine ea using these FAO equations.

`--method pm` retains PM even with temperature-only input. Explicit
`--method hargreaves` uses eq. 52. The library also supports `method='auto'`,
which chooses Hargreaves only when all humidity, wind, sunshine, and Rs are absent.
Default Ko=0 assumes Tmin approximates dew point; some arid settings require a
locally justified positive correction. Missing rain is assumed zero and flagged,
so users should supply measured rain for scheduling.

## Crops, soils, and stress

| FAO-56 reference | Implementation |
| --- | --- |
| Tables 11, 12 | Four stage lengths, Kc ini/mid/end, maximum height; regional choices in `crop.stage_source` |
| 58 | ETc = Kc·ET0 |
| 62, 65 | Kc adjusted = Kc table + [0.04(u2−2)−0.004(RHmin−45)](h/3)^0.3 |
| Fig. 25 / 66 | Constant initial/mid Kc; linear interpolation over development and late season |
| Table 19 | Selected representative θFC, θWP by texture, m³/m³ |
| Table 22 | Root depth ranges and baseline p; p = clamp[p_table+0.04(5−ETc), 0.1, 0.8] |
| 82 | TAW = 1000(θFC−θWP)Zr |
| 83 | RAW = p·TAW |
| 84 | Ks=1 at Dr≤RAW; otherwise max[0,(TAW−Dr)/(TAW−RAW)] |
| 81 (single-Kc approximation) | ETc,adj = Ks·Kc·ET0 |
| 85 | Dr,end = Dr,previous + Dgrowth − Pe − Inet − CR + ETc,adj + DP |
| 88 | DP = max[0, Pe+Inet+CR−Dr,start−ETc,adj] |
| 90 / Table 24 | Ya/Ym = clamp[1−Ky(1−ΣETc,adj/ΣETc), 0, 1]; seasonal Ky from FAO-33 as reproduced in FAO-56 |

Kc endpoints use the supplied **midseason and late-season mean** wind/RHmin,
respectively; dry endpoints below 0.45 remain unchanged. Inputs to the empirical
adjustment are clipped to u2=1–6 m/s, RHmin=20–80%, h=0.1–10 m. No initial-Kc
wetting model is implied: use `--kc-ini`. The day index is zero-based at the start
of the day; the final endpoint is reached at elapsed day equal to total stage
length. Scheduling ends before that day. Partial stages use the available mean,
with a flag; absent stage weather leaves its endpoint unadjusted. Future data can
therefore revise prior Kc on a rerun, as in a seasonal planning calculation.

Root depth holds Zr,min through the initial stage and grows linearly to Zr,max
during development. Table 22 gives a range of **maximum effective depths**, not
seedling depths: this interpretation is an explicit planning assumption. Replace
it with local rooting measurements using a custom crop file. Newly rooted soil
is at field capacity by default. `--subsoil-depletion` specifies its depleted
fraction and Dgrowth is included in every conservation check.

Ks is evaluated after that day's rainfall, CR, and morning irrigation, so supply
can relieve stress on the same day. ETc,adj is additionally limited by available
root-zone water. This daily timing approximation cannot resolve storm timing,
infiltration rates, or midday stress. MAD changes the management trigger, while
physiological p still sets Ks. Stress days count Ks<1. Single-Kc stress applies to
the combined evaporation/transpiration flux; a dual-Kc model would separate them.

## Effective rainfall and management

Default `fixed` uses Pe=f(P−RO), f=0.8. An optional runoff column is subtracted
first. The remainder `(P−Pe)` is reported as rain_loss, which includes runoff;
do not subtract runoff a second time. Soil storage overflow is always a separate
DP term. The USDA-SCS option is the empirical monthly CROPWAT-style formula:

```
Pe_month = P_month(125 − 0.2P_month)/125     if P_month <= 250 mm
           125 + 0.1P_month               otherwise
```

The scheduler computes monthly totals of P−RO and apportions effective rain
in proportion to individual rainfall depths. It does **not** insert daily rain
into a monthly equation. Partial months are flagged; their totals are not
extrapolated. SCS uses all supplied rows in that calendar month, including forecast
or out-of-season rows, so daily apportionment is retrospective and can change on
a rerun. Use fixed rainfall for advice that must avoid this monthly look-ahead.
Neither option replaces measured infiltration or a runoff model.

| Strategy | Morning rule |
| --- | --- |
| `refill` | When post-rain Dr≥MAD·TAW (or adjusted p·TAW), refill to FC |
| `fixed` / `fixed-depth` | Same trigger, apply fixed **net** depth |
| `interval` / `fixed-interval` | Apply fixed net depth on planting day and every N days, including wet days |
| `deficit` | Same trigger; replenish to θtarget=`deficit_fraction`·θFC, strictly above θWP |
| `none` | No automatic irrigation; useful as a rainfed comparison |

Gross depth = net/efficiency. Capacity is **gross** mm/day and limits automatic
applications. Drip 0.9, sprinkler 0.75, and furrow 0.6 are illustrative efficiencies,
not performance guarantees. Irrigation above storage capacity drains via DP.
Optional observed `irrigation_net` overrides automation on that day, including a
recorded zero; capacity does not alter measurements. No salinity leaching,
ponding, groundwater-depth model, or conveyance network is represented.

The balance residual is
`ΔDr − (Dgrowth + ETc,adj + DP − Pe − Inet − CR)`.
Equivalently, water supply minus losses equals the change in storage, which is
**−ΔDr** for a fixed root zone. Daily and seasonal tests require |residual|<1e−9 mm.

## Forecasts and yield

`next --as-of DATE` simulates the whole supplied season history then reports the
first event strictly after DATE. With `is_forecast=true`, the default as-of date
is the day before the first forecast row; otherwise it is the machine's current
date. Historical irrigation is simulated unless observations are supplied. The
model does not fetch forecasts or infer their uncertainty. "No irrigation" means
none within the supplied crop/weather horizon. Do not present a synthetic file
or a retrospective simulation as an operational weather forecast.

The seasonal Ky relationship is a planning estimate, not a yield forecast. Ky
is null where no supported single seasonal value is selected; yield is withheld
for incomplete seasons and individual alfalfa cuttings. Rice's saturation-based
p and standing-water Kc require a separate paddy balance for operational advice;
this release exposes the table and a flagged root-zone-only approximation.

## Validation and source discrepancies

Tests reproduce pressure at 1800 m (81.8 kPa, γ≈0.054), es at 24.5/15 °C
(2.39 kPa), 20°S on 3 September (Ra≈32.2, N≈11.7), and Uccle/Brussels on
6 July (ET0=3.88026 mm/day, within 0.05 of 3.9). An independent scalar
calculation also checks every Brussels intermediate.

The request combined two radiation examples: 20°S/J246 with n=7.1 gives
Rs≈17.8, while Rio's May values Ra=25.1, N=10.9, n=7.1 give Rs≈14.5.
Tests explicitly distinguish them. Exact-equation independent checks supplement
rounded printed values. The Bangkok monthly ET0 fixture is explicitly skipped
because its complete unambiguous inputs were not established; monthly soil heat
flux and hourly ET0 are tested separately. No Bangkok value is fabricated.

Source chapters: [2](https://www.fao.org/4/x0490e/x0490e06.htm),
[3](https://www.fao.org/4/x0490e/x0490e07.htm),
[4](https://www.fao.org/4/x0490e/x0490e08.htm),
[6](https://www.fao.org/4/x0490e/x0490e0b.htm),
[7](https://www.fao.org/4/x0490e/x0490e0c.htm),
[8](https://www.fao.org/4/x0490e/x0490e0e.htm).
