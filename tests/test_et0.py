"""FAO-56 equation tests, rounded published examples and independent calculations.

Source: https://www.fao.org/4/x0490e/x0490e07.htm and chapter 4 (x0490e08).
Example numbering/rounding in the HTML is inconsistent, so independently
evaluated equations take precedence over uncertain example labels. In
particular, 20°S/J246 has Ra≈32.2, N≈11.7 and Rs≈17.8 for n=7.1 hours;
Rs≈14.5 belongs to Rio's May example, with Ra≈25.1 and N≈10.9.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import pytest

from fieldwater import et0 as e


def weather(**changes):
    """A complete Brussels daily observation; wind converted from 10 km/h."""
    result = dict(date=date(2025, 7, 6), tmax=21.5, tmin=12.3,
                  rh_max=84.0, rh_min=63.0, wind=10 / 3.6,
                  sunshine_hours=9.25)
    result.update(changes)
    return result


def independent_daily(w, latitude, altitude=0, wind_height=2, ko=0, coastal=False):
    """Independent complete scalar calculation; no production helpers used."""
    tmax, tmin = w["tmax"], w["tmin"]
    t = w.get("tmean", (tmax + tmin) / 2)
    esmax = 0.6108 * math.exp(17.27 * tmax / (tmax + 237.3))
    esmin = 0.6108 * math.exp(17.27 * tmin / (tmin + 237.3))
    es = (esmax + esmin) / 2
    if w.get("tdew") is not None:
        td = w["tdew"]
        ea = 0.6108 * math.exp(17.27 * td / (td + 237.3))
    elif w.get("rh_max") is not None and w.get("rh_min") is not None:
        ea = (esmin * w["rh_max"] + esmax * w["rh_min"]) / 200
    else:
        td = tmin - ko
        ea = 0.6108 * math.exp(17.27 * td / (td + 237.3))
    p = 101.3 * (1 - 0.0065 * altitude / 293) ** 5.26
    gamma = 0.000665 * p
    delta = 4098 * 0.6108 * math.exp(17.27 * t / (t + 237.3)) / (t + 237.3) ** 2
    j = w["date"].timetuple().tm_yday
    phi = latitude * math.pi / 180
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    ws = math.acos(max(-1, min(1, -math.tan(phi) * math.tan(dec))))
    ra = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    nmax = 24 / math.pi * ws
    rso = (0.75 + 2e-5 * altitude) * ra
    if w.get("rs") is not None:
        rs = w["rs"]
    elif w.get("sunshine_hours") is not None:
        rs = (0.25 + 0.50 * w["sunshine_hours"] / nmax) * ra
    else:
        rs = min((0.19 if coastal else 0.16) * math.sqrt(tmax - tmin) * ra, rso)
    rnl = 4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * min(rs / rso, 1) - 0.35)
    rn = 0.77 * rs - rnl
    u2 = w.get("wind", 2.0)
    if "wind" in w and wind_height != 2:
        u2 = u2 * 4.87 / math.log(67.8 * wind_height - 5.42)
    et = (0.408 * delta * rn + gamma * 900 / (t + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return dict(et0=max(0, et), ra=ra, ea=ea, es=es, rn=rn, u2=u2, rs=rs)


def test_fao_pressure_1800():
    p = e.atmospheric_pressure(1800)
    assert p == pytest.approx(81.8, abs=0.05)
    assert e.psychrometric_constant(p) == pytest.approx(0.054, abs=0.0005)


def test_fao_mean_saturation_pressure():
    assert e.mean_saturation_vapour_pressure(24.5, 15) == pytest.approx(2.39, abs=0.005)
    assert e.mean_saturation_vapour_pressure(24.5, 15) > e.saturation_vapour_pressure(19.75)


@pytest.mark.parametrize("t,expected", [(0, 0.6108), (10, 1.2280), (20, 2.3383), (30, 4.2431), (-10, 0.2857)])
def test_saturation_reference_values(t, expected):
    assert e.saturation_vapour_pressure(t) == pytest.approx(expected, abs=5e-5)


@pytest.mark.parametrize("t", [-40, -10, 0, 15, 30, 45])
def test_slope_matches_independent_derivative(t):
    h = 1e-4
    derivative = (e.saturation_vapour_pressure(t + h) - e.saturation_vapour_pressure(t - h)) / (2 * h)
    # FAO rounds 17.27*237.3=4098.171 to 4098.
    assert e.slope_vapour_pressure_curve(t) == pytest.approx(derivative, rel=5e-5)


def test_fao_actual_pressure_rh_and_vpd():
    ea = e.actual_vapour_pressure_from_rh(25, 18, 82, 54)
    assert ea == pytest.approx(1.70, abs=0.005)
    assert e.vapour_pressure_deficit(e.mean_saturation_vapour_pressure(25, 18), ea) == pytest.approx(0.91, abs=0.01)


@pytest.mark.parametrize("rh", [0, 20, 50, 100])
def test_humidity_equations_and_roundtrip(rh):
    es20 = 2.338281270927446
    assert e.actual_vapour_pressure_from_rh_max(20, rh) == pytest.approx(es20 * rh / 100)
    assert e.actual_vapour_pressure_hourly(20, rh) == pytest.approx(es20 * rh / 100)
    assert e.relative_humidity(es20 * rh / 100, 20) == pytest.approx(rh)
    es = (0.6108 * math.exp(17.27 * 30 / 267.3) + 0.6108 * math.exp(17.27 * 20 / 257.3)) / 2
    assert e.actual_vapour_pressure_from_rh_mean(30, 20, rh) == pytest.approx(es * rh / 100)


def test_dewpoint_tmin_correction_wet_bulb():
    assert e.actual_vapour_pressure_from_dewpoint(10) == pytest.approx(1.2279626193393785)
    assert e.actual_vapour_pressure_from_tmin(13, 3) == pytest.approx(1.2279626193393785)
    expected = 0.6108 * math.exp(17.27 * 20 / 257.3) - 0.000662 * 100 * 5
    assert e.actual_vapour_pressure_from_wet_bulb(25, 20, 100) == pytest.approx(expected)


def test_mean_temperature_and_energy_conversion():
    assert e.mean_temperature(24, 12) == 18.0
    assert e.radiation_to_evaporation(10) == pytest.approx(4.08)
    assert e.radiation_to_evaporation(-10) == pytest.approx(-4.08)


def test_fao_20s_solar_geometry_and_angstrom():
    phi = math.radians(-20)
    dec = e.solar_declination(246)
    assert dec == pytest.approx(0.120, abs=0.001)
    assert e.inverse_relative_distance_earth_sun(246) == pytest.approx(0.985, abs=0.001)
    ws = e.sunset_hour_angle(phi, dec)
    assert ws == pytest.approx(1.527, abs=0.001)
    ra, n = e.extraterrestrial_radiation(phi, 246), e.daylight_hours(ws)
    assert ra == pytest.approx(32.2, abs=0.05)
    assert n == pytest.approx(11.7, abs=0.05)
    # n=7.1 with THESE geometry values gives 17.8, not Rio's 14.5.
    assert e.solar_radiation(ra, 7.1, n) == pytest.approx(17.8, abs=0.1)


def test_fao_rio_radiation_examples():
    """Rounded Example 10–12 inputs; values are not the 20°S/J246 example."""
    rs = e.solar_radiation(25.1, 7.1, 10.9)
    assert rs == pytest.approx(14.5, abs=0.1)
    rnl = e.net_longwave_radiation(25.1, 19.1, 2.1, 14.5, 18.8)
    assert rnl == pytest.approx(3.5, abs=0.1)
    assert e.net_radiation(e.net_shortwave_radiation(14.5), rnl) == pytest.approx(7.6, abs=0.1)


@pytest.mark.parametrize("latitude,j,night", [(90, 355, True), (90, 172, False), (-90, 172, True), (-90, 355, False), (80, 355, True), (-80, 355, False)])
def test_polar_geometry(latitude, j, night):
    phi = e.latitude_radians(latitude)
    ws = e.sunset_hour_angle(phi, e.solar_declination(j))
    assert ws == (0 if night else math.pi)
    assert e.daylight_hours(ws) == (0 if night else 24)
    ra = e.extraterrestrial_radiation(phi, j)
    assert math.isfinite(ra) and ra >= 0
    assert ra == 0 if night else ra > 0


def test_polar_exact_equinox_and_zero_daylight():
    assert e.sunset_hour_angle(math.pi / 2, 0) == math.pi / 2
    assert e.solar_radiation(0, 0, 0) == 0
    with pytest.raises(ValueError):
        e.solar_radiation(1, 0, 0)


def test_calendar_leap_year_and_degrees():
    assert e.day_of_year(date(2024, 12, 31)) == 366
    assert e.day_of_year(date(2025, 9, 3)) == 246
    assert e.latitude_radians(-20) == pytest.approx(-math.pi / 9)


def test_hourly_senegal_solar_example():
    phi, j = math.radians(16.22), 274
    assert e.seasonal_correction_angle(j) == pytest.approx(3.3315, abs=0.0001)
    assert e.seasonal_time_correction(j) == pytest.approx(0.1889, abs=0.0001)
    angle = e.solar_time_angle(14.5, 15, 16.25, j)
    assert angle == pytest.approx(0.682, abs=0.001)
    bounds = e.solar_time_angle_bounds(angle)
    assert e.extraterrestrial_radiation_hourly(phi, j, *bounds) == pytest.approx(3.543, abs=0.01)
    night_bounds = e.solar_time_angle_bounds(e.solar_time_angle(2.5, 15, 16.25, j))
    assert e.extraterrestrial_radiation_hourly(phi, j, *night_bounds) == 0


@pytest.mark.parametrize("latitude,j", [(0, 81), (45, 172), (-20, 246), (80, 172), (80, 355)])
def test_sum_hourly_extraterrestrial_equals_daily(latitude, j):
    phi = math.radians(latitude)
    hourly_sum = sum(e.extraterrestrial_radiation_hourly(phi, j, -math.pi + i * math.pi / 12, -math.pi + (i + 1) * math.pi / 12) for i in range(24))
    assert hourly_sum == pytest.approx(e.extraterrestrial_radiation(phi, j), abs=1e-12)


def test_hourly_sunrise_clips_partial_interval():
    phi, j = 0, 81
    ra = e.extraterrestrial_radiation_hourly(phi, j, -math.pi / 2 - 0.1, -math.pi / 2 + 0.1)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    expected = 720 / math.pi * 0.082 * dr * math.cos(dec) * (math.sin(-math.pi / 2 + 0.1) + 1)
    assert ra == pytest.approx(expected)


def test_solar_time_greenwich_wrap():
    assert e.solar_time_angle(12, 0, 359, 100) == pytest.approx(e.solar_time_angle(12, 1, 0, 100))


@pytest.mark.parametrize("coastal,k", [(False, 0.16), (True, 0.19)])
def test_temperature_radiation_and_clear_sky_cap(coastal, k):
    assert e.solar_radiation_from_temperature(26.6, 14.8, 40.6, coastal) == pytest.approx(k * math.sqrt(11.8) * 40.6)
    assert e.solar_radiation_from_temperature(40, 0, 40, coastal, rso=25) == 25
    assert e.solar_radiation_from_temperature(20, 20, 40, coastal) == 0


def test_clear_sky_albedo_and_custom_coefficients():
    assert e.clear_sky_radiation(40, 100) == pytest.approx(30.08)
    assert e.clear_sky_radiation(40, 100, 0.2, 0.4) == pytest.approx(24)
    assert e.net_shortwave_radiation(20) == pytest.approx(15.4)
    assert e.net_shortwave_radiation(20, 1) == 0
    assert e.net_radiation(0, 1) == -1


def test_longwave_ratio_capped_and_night_explicit():
    r1 = e.net_longwave_radiation(30, 20, 2, 20, 20)
    assert e.net_longwave_radiation(30, 20, 2, 40, 20) == r1
    with pytest.raises(ValueError, match="cloudiness_ratio"):
        e.net_longwave_radiation(30, 20, 2, 0, 0)
    expected = 4.903e-9 * ((303.16 ** 4 + 293.16 ** 4) / 2) * (0.34 - 0.14 * math.sqrt(2)) * (1.35 * 0.5 - 0.35)
    assert e.net_longwave_radiation(30, 20, 2, 0, 0, 0.5) == pytest.approx(expected)


def test_hourly_longwave_scaling():
    daily = e.net_longwave_radiation(28, 28, 3.402, 0, 0, 0.8)
    assert e.net_longwave_radiation(28, 28, 3.402, 0, 0, 0.8, hourly=True) == pytest.approx(daily / 24)
    with pytest.raises(ValueError):
        e.net_longwave_radiation(30, 20, 2, 10, 20, hourly=True)


def test_monthly_and_general_soil_heat_flux():
    assert e.soil_heat_flux_daily() == 0
    assert e.soil_heat_flux_monthly(14.1, 18.8) == pytest.approx(0.329)
    assert e.soil_heat_flux_monthly_previous(16.1, 14.1) == pytest.approx(0.28)
    assert e.soil_heat_flux(20, 15, 30, 2) == pytest.approx(0.7)
    assert e.soil_heat_flux_monthly(18.8, 14.1) == pytest.approx(-0.329)


@pytest.mark.parametrize("rn,day,expected", [(2, None, 0.2), (-2, None, -1), (2, False, 1), (-2, True, -0.2), (0, None, 0)])
def test_hourly_soil_flux(rn, day, expected):
    assert e.soil_heat_flux_hourly(rn, day) == pytest.approx(expected)


def test_wind_example_and_identity():
    assert e.wind_speed_2m(3.2, 10) == pytest.approx(2.4, abs=0.01)
    assert e.wind_speed_2m(2, 2) == 2
    assert e.wind_speed_2m(0, 10) == 0


@pytest.mark.parametrize("u2,ea,rn,g", [(2, 1, 12, 0), (0, 2, 10, 2), (4, 0, 8, -1), (2, 3, -2, 0)])
def test_daily_equation_independently(u2, ea, rn, g):
    expected = (0.408 * 0.145 * (rn - g) + 0.067 * 900 / 293 * u2 * (2.338 - ea)) / (0.145 + 0.067 * (1 + 0.34 * u2))
    assert e.penman_monteith_daily(20, u2, 2.338, ea, 0.145, 0.067, rn, g) == pytest.approx(expected)


@pytest.mark.parametrize("rn,day,g", [(1.749, True, None), (-0.1, False, None), (1.5, True, 0.4), (-0.1, False, -0.02)])
def test_hourly_equation_independently(rn, day, g):
    used_g = (0.1 if day else 0.5) * rn if g is None else g
    expected = (0.408 * 0.358 * (rn - used_g) + 0.0673 * 37 / 311 * 3.3 * (6.625 - 3.445)) / (0.358 + 0.0673 * (1 + 0.34 * 3.3))
    assert e.penman_monteith_hourly(38, 3.3, 6.625, 3.445, 0.358, 0.0673, rn, g, day) == pytest.approx(expected)


def test_hourly_fao_senegal_day_example():
    result = e.penman_monteith_hourly(38, 3.3, 6.625, 3.445, 0.358, 0.0673, 1.749, daytime=True)
    assert result == pytest.approx(0.63, abs=0.01)


@pytest.mark.parametrize("tmax,tmin,ra", [(30, 20, 40), (21.5, 12.3, 41.09), (20, 20, 30), (30, 15, 0)])
def test_hargreaves_essential_energy_conversion(tmax, tmin, ra):
    expected = 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(tmax - tmin) * 0.408 * ra
    assert e.hargreaves(tmax, tmin, ra) == pytest.approx(expected)


def test_daily_brussels_published_and_independent():
    w = weather()
    result = e.calculate_daily_et0(w, 50.8, 100, 10)
    assert result["et0"] == pytest.approx(3.9, abs=0.05)
    expected = independent_daily(w, 50.8, 100, 10)
    for key, value in expected.items():
        assert result[key] == pytest.approx(value, rel=1e-12)
    assert result["method"] == "pm"
    assert result["rh_min"] == 63
    assert result["flags"] == ["radiation_from_sunshine"]


@pytest.mark.parametrize("latitude,altitude,coastal", [(0, 0, False), (-20, 1800, True), (45, 200, False)])
def test_explicit_pm_temperature_only_against_independent(latitude, altitude, coastal):
    w = dict(date=date(2025, 7, 15), tmax=26.6, tmin=14.8)
    result = e.calculate_daily_et0(w, latitude, altitude, wind_height=10, coastal=coastal, ko=2)
    expected = independent_daily(w, latitude, altitude, wind_height=10, ko=2, coastal=coastal)
    for key, value in expected.items():
        assert result[key] == pytest.approx(value, rel=1e-12)
    assert result["method"] == "pm"
    assert result["u2"] == 2.0  # Missing wind is already the 2 m estimate.
    assert set(result["flags"]) == {"wind_estimated_2m_s", "humidity_estimated_tmin_ko", "rh_min_estimated", "radiation_estimated_temperature"}


@pytest.mark.parametrize("changes,expected_ea,flag", [
    (dict(tdew=10), 1.2279626193393785, None),
    (dict(rh_min=None), 0.6108 * math.exp(17.27 * 12.3 / 249.6) * 0.84, "humidity_from_rh_max"),
    (dict(rh_min=None, rh_max=None, rh_mean=60), None, "humidity_from_rh_mean"),
    (dict(rh_min=None, rh_max=None), None, "humidity_estimated_tmin_ko"),
])
def test_humidity_priority_and_estimates(changes, expected_ea, flag):
    result = e.calculate_daily_et0(weather(**changes), 50.8)
    if expected_ea is not None:
        assert result["ea"] == pytest.approx(expected_ea)
    if flag:
        assert flag in result["flags"]
    if changes.get("rh_min", 63) is None:
        assert result["rh_min"] == pytest.approx(100 * result["ea"] / e.saturation_vapour_pressure(21.5))


def test_isolated_rh_min_cannot_supply_fao_ea():
    result = e.calculate_daily_et0(weather(rh_max=None, rh_min=50), 50.8)
    assert "humidity_estimated_tmin_ko" in result["flags"]
    assert result["rh_min"] == 50


def test_measured_radiation_priority_rain_invariance_and_no_mutation():
    w = weather(rs=15, rain=0)
    copy = dict(w)
    result = e.calculate_daily_et0(w, 50.8)
    assert w == copy
    assert result["rs"] == 15
    assert "radiation_from_sunshine" not in result["flags"]
    assert result["et0"] == e.calculate_daily_et0(dict(w, rain=100), 50.8)["et0"]


def test_none_equivalent_to_missing():
    w = dict(date=date(2025, 7, 15), tmax=30, tmin=20)
    result = e.calculate_daily_et0(w, 20)
    with_none = dict(w, **{key: None for key in ["tmean", "rh_max", "rh_min", "rh_mean", "tdew", "wind", "sunshine_hours", "rs", "rain"]})
    assert result == e.calculate_daily_et0(with_none, 20)


@pytest.mark.parametrize("extra,method", [({}, "hargreaves"), ({"rain": 5}, "hargreaves"), ({"wind": 0}, "pm"), ({"rh_min": 0}, "pm"), ({"rh_mean": 50}, "pm"), ({"tdew": 10}, "pm"), ({"rs": 0}, "pm"), ({"sunshine_hours": 0}, "pm")])
def test_auto_only_switches_temperature_only(extra, method):
    w = dict(date=date(2025, 7, 15), tmax=30, tmin=20, **extra)
    assert e.calculate_daily_et0(w, 20, method="auto")["method"] == method


def test_explicit_hargreaves_diagnostics_and_provided_mean():
    w = dict(date=date(2025, 7, 15), tmax=30, tmin=20, tmean=24)
    result = e.calculate_daily_et0(w, 20, method="hargreaves")
    expected = 0.0023 * 41.8 * math.sqrt(10) * 0.408 * result["ra"]
    assert result["et0"] == pytest.approx(expected)
    assert result["ea"] is result["rh_min"] is result["rn"] is None
    assert result["rs"] is result["rso"] is None
    assert result["u2"] == 2.0
    assert "hargreaves_temperature_method" in result["flags"]


def test_custom_daily_g_and_coefficients():
    w = weather()
    base = e.calculate_daily_et0(w, 50.8)
    altered = e.calculate_daily_et0(w, 50.8, g=1)
    assert altered["et0"] < base["et0"]
    custom = e.calculate_daily_et0(w, 50.8, a_s=0.2, b_s=0.4)
    assert custom["rso"] == pytest.approx(0.6 * custom["ra"])


@pytest.mark.parametrize("latitude", [-90, -80, 80, 90])
def test_high_level_polar_night_finite_and_flagged(latitude):
    day = date(2025, 12, 21) if latitude > 0 else date(2025, 6, 21)
    result = e.calculate_daily_et0(dict(date=day, tmax=-5, tmin=-10), latitude)
    assert result["ra"] == result["rso"] == result["rs"] == 0
    assert "polar_night_cloudiness_assumed" in result["flags"]
    assert math.isfinite(result["rn"]) and math.isfinite(result["et0"])
    assert result["et0"] >= 0


def test_negative_daily_clipping_signed_equations():
    assert e.penman_monteith_daily(20, 0, 2, 2, 0.145, 0.067, -5) < 0
    result = e.calculate_daily_et0(weather(), 50.8, g=100)
    assert result["et0"] == 0
    assert "negative_et0_clipped" in result["flags"]
    cold = e.calculate_daily_et0(dict(date=date(2025, 1, 10), tmax=-20, tmin=-30), 0, method="hargreaves")
    assert cold["et0"] == 0
    assert "negative_et0_clipped" in cold["flags"]


@pytest.mark.parametrize("wind", [0.5, 2, 5])
def test_drier_air_increases_pm_et_at_fixed_energy(wind):
    ets = [e.penman_monteith_daily(25, wind, 3.2, ea, 0.19, 0.067, 12) for ea in [2.8, 2, 1, 0]]
    assert all(a < b for a, b in zip(ets, ets[1:]))


@pytest.mark.parametrize("wind", [1, 2, 4])
def test_warmer_air_increases_pm_et_in_dry_conditions(wind):
    """Fixed ea/Rn/gamma; update BOTH es and delta as temperature changes.

    This is a property of the specified dry regime, not a universal assertion
    across simultaneous changes to humidity, radiation, and air pressure.
    """
    ets = [e.penman_monteith_daily(
        temperature, wind, e.saturation_vapour_pressure(temperature), 0.5,
        e.slope_vapour_pressure_curve(temperature), 0.067, 12,
    ) for temperature in [10, 15, 20, 25, 30, 35, 40]]
    assert all(a < b for a, b in zip(ets, ets[1:]))


@pytest.mark.parametrize("ea", [0, 0.5, 1])
def test_wind_increases_pm_et_in_dry_air(ea):
    """Hold 25 °C, es/delta, Rn, gamma and low ea fixed; vary only wind."""
    ets = [e.penman_monteith_daily(
        25, wind, e.saturation_vapour_pressure(25), ea,
        e.slope_vapour_pressure_curve(25), 0.067, 12,
    ) for wind in [0, 0.5, 1, 2, 4, 8]]
    assert all(a < b for a, b in zip(ets, ets[1:]))


@pytest.mark.parametrize("temperature", [10, 25, 40])
def test_net_radiation_increases_pm_et(temperature):
    """Hold temperature, vapour pressures, wind, gamma and G fixed; vary Rn."""
    ets = [e.penman_monteith_daily(
        temperature, 2, e.saturation_vapour_pressure(temperature), 0.5,
        e.slope_vapour_pressure_curve(temperature), 0.067, rn, g=0,
    ) for rn in [0, 3, 6, 12, 18, 24]]
    assert all(a < b for a, b in zip(ets, ets[1:]))


def test_wind_sensitivity_is_larger_in_dry_air():
    def increment(ea):
        return e.penman_monteith_daily(25, 4, 3.2, ea, 0.19, 0.067, 12) - e.penman_monteith_daily(25, 1, 3.2, ea, 0.19, 0.067, 12)
    assert increment(0.5) > increment(2.8)


def test_ko_reduces_humidity_and_increases_daily_et():
    w = dict(date=date(2025, 7, 15), tmax=35, tmin=20)
    wet, dry = e.calculate_daily_et0(w, 20), e.calculate_daily_et0(w, 20, ko=3)
    assert dry["ea"] < wet["ea"]
    assert dry["rh_min"] < wet["rh_min"]
    assert dry["et0"] > wet["et0"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), None, True, "20"])
def test_nonfinite_or_non_numeric_rejected(value):
    with pytest.raises(ValueError):
        e.saturation_vapour_pressure(value)
    with pytest.raises(ValueError):
        e.calculate_daily_et0(weather(wind=value), 50.8) if value is not None else e.calculate_daily_et0(weather(tmax=value), 50.8)


@pytest.mark.parametrize("j", [0, 367, 1.0, True, None])
def test_invalid_julian_day(j):
    with pytest.raises(ValueError):
        e.solar_declination(j)


@pytest.mark.parametrize("changes", [
    {"tmax": None}, {"tmin": None}, {"tmax": 10}, {"tmean": 40},
    {"rh_max": 101}, {"rh_min": -1}, {"rh_max": 50, "rh_min": 60},
    {"rh_mean": 90}, {"tdew": 30}, {"wind": -1}, {"rain": -1},
    {"rs": -1}, {"sunshine_hours": 24}, {"date": "2025-07-06"},
    {"date": datetime(2025, 7, 6)}, {"rs": float("nan")},
    {"rh_mean": float("inf")}, {"tmax": 101},
])
def test_invalid_weather(changes):
    with pytest.raises(ValueError):
        e.calculate_daily_et0(weather(**changes), 50.8)


@pytest.mark.parametrize("kwargs", [
    {"latitude": 91}, {"latitude": float("nan")}, {"altitude": 12000},
    {"wind_height": 0}, {"wind_height": 0.09}, {"ko": -1},
    {"method": "invalid"}, {"coastal": "yes"}, {"g": float("inf")},
    {"a_s": 0.8, "b_s": 0.5}, {"polar_cloudiness_ratio": -0.1},
])
def test_invalid_high_level_options(kwargs):
    options = dict(latitude=50.8)
    options.update(kwargs)
    with pytest.raises(ValueError):
        e.calculate_daily_et0(weather(), **options)


@pytest.mark.parametrize("call", [
    lambda: e.atmospheric_pressure(-1001),
    lambda: e.psychrometric_constant(0),
    lambda: e.actual_vapour_pressure_from_rh(30, 20, 40, 50),
    lambda: e.actual_vapour_pressure_from_tmin(-99, 2),
    lambda: e.actual_vapour_pressure_from_wet_bulb(40, 0, 100),
    lambda: e.solar_radiation(30, 13, 12),
    lambda: e.clear_sky_radiation(30, a_s=0.2),
    lambda: e.clear_sky_radiation(30, a_s=0, b_s=0),
    lambda: e.net_shortwave_radiation(20, -0.1),
    lambda: e.soil_heat_flux(20, 10, 0, 2),
    lambda: e.soil_heat_flux_hourly(2, "day"),
    lambda: e.wind_speed_2m(2, 0.09),
    lambda: e.penman_monteith_daily(20, 2, 2, 1, 0, 0.067, 10),
    lambda: e.hargreaves(30, 20, -1),
    lambda: e.hargreaves(30, 20, 40, 31),
    lambda: e.solar_time_angle_bounds(0, 2),
    lambda: e.extraterrestrial_radiation_hourly(0, 1, 0.2, 0.1),
    lambda: e.extraterrestrial_radiation_hourly(0, 1, -1, 1),
])
def test_low_level_invalid_domains(call):
    with pytest.raises(ValueError):
        call()


def test_public_functions_have_equation_documentation():
    for name in e.__all__:
        assert callable(getattr(e, name))
        assert getattr(e, name).__doc__, name


@pytest.mark.skip(reason="Bangkok monthly fixture not used: supplied task lacks an unambiguous complete monthly ET0 input set; online latitude signs and example numbering are inconsistent. Monthly G is checked independently and against the Algiers example.")
def test_monthly_bangkok_uncertain_fixture():
    pass
