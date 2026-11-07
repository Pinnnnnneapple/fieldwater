"""FAO-56 grass reference evapotranspiration, using only the standard library.

Sources: https://www.fao.org/4/x0490e/x0490e07.htm (chapter 3),
https://www.fao.org/4/x0490e/x0490e06.htm (daily equation 6), and
https://www.fao.org/4/x0490e/x0490e08.htm (hourly equation 53).
Equation numbers refer to FAO Irrigation and Drainage Paper 56; some online
examples contain numbering, sign, and rounding inconsistencies. Equations,
rather than those typographical errors, define the implementation.

Temperatures are degrees Celsius, vapour pressures kPa, wind m/s, altitude m,
and daily radiation MJ/m²/day unless stated otherwise. Solar geometry takes
latitude in RADIANS; calculate_daily_et0 takes latitude in DEGREES north.
The empirical temperature formula is accepted over [-100, 100] °C, a numeric
guard rather than a claim of calibration over that entire range. No uncertainty
model is implied. Low-level equations preserve signed fluxes and condensation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime
from numbers import Real
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "atmospheric_pressure", "psychrometric_constant", "mean_temperature",
    "saturation_vapour_pressure", "mean_saturation_vapour_pressure",
    "slope_vapour_pressure_curve", "actual_vapour_pressure_from_dewpoint",
    "actual_vapour_pressure_from_rh", "actual_vapour_pressure_from_rh_max",
    "actual_vapour_pressure_from_rh_mean", "actual_vapour_pressure_from_tmin",
    "actual_vapour_pressure_from_wet_bulb", "actual_vapour_pressure_hourly",
    "relative_humidity", "vapour_pressure_deficit", "radiation_to_evaporation",
    "day_of_year", "latitude_radians", "inverse_relative_distance_earth_sun",
    "solar_declination", "sunset_hour_angle", "extraterrestrial_radiation",
    "daylight_hours", "seasonal_correction_angle", "seasonal_time_correction",
    "solar_time_angle", "solar_time_angle_bounds", "extraterrestrial_radiation_hourly",
    "solar_radiation", "solar_radiation_from_temperature", "clear_sky_radiation",
    "net_shortwave_radiation", "net_longwave_radiation", "net_radiation",
    "soil_heat_flux", "soil_heat_flux_daily", "soil_heat_flux_monthly",
    "soil_heat_flux_monthly_previous", "soil_heat_flux_hourly", "wind_speed_2m",
    "penman_monteith_daily", "penman_monteith_hourly", "hargreaves",
    "calculate_daily_et0",
]


def _number(name: str, value: Any, low: Optional[float] = None,
            high: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return value


def _positive(name: str, value: Any) -> float:
    value = _number(name, value, 0)
    if value == 0:
        raise ValueError(f"{name} must be positive")
    return value


def _temperature(name: str, value: Any) -> float:
    return _number(name, value, -100, 100)


def _temperatures(tmax: float, tmin: float) -> Tuple[float, float]:
    tmax, tmin = _temperature("tmax", tmax), _temperature("tmin", tmin)
    if tmax < tmin:
        raise ValueError("tmax must be >= tmin")
    return tmax, tmin


def _julian_day(j: int) -> int:
    if isinstance(j, bool) or not isinstance(j, int) or not 1 <= j <= 366:
        raise ValueError("day of year must be an integer in [1, 366]")
    return j


def atmospheric_pressure(altitude: float) -> float:
    """Eq. 7: P=101.3[(293-0.0065z)/293]^5.26, kPa; z in [-1000,11000] m."""
    z = _number("altitude", altitude, -1000, 11000)
    return 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26


def psychrometric_constant(pressure: float) -> float:
    """Eq. 8: gamma=0.000665 P, kPa/°C; pressure must be positive kPa."""
    return 0.000665 * _positive("pressure", pressure)


def mean_temperature(tmax: float, tmin: float) -> float:
    """Eq. 9: (Tmax+Tmin)/2, °C; finite ordered extrema in [-100,100] °C."""
    tmax, tmin = _temperatures(tmax, tmin)
    return (tmax + tmin) / 2


def saturation_vapour_pressure(temperature: float) -> float:
    """Eq. 11: e°=0.6108 exp[17.27T/(T+237.3)], kPa; T in [-100,100] °C."""
    t = _temperature("temperature", temperature)
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def mean_saturation_vapour_pressure(tmax: float, tmin: float) -> float:
    """Eq. 12: es=[e°(Tmax)+e°(Tmin)]/2, kPa; finite ordered extrema, °C."""
    tmax, tmin = _temperatures(tmax, tmin)
    return (saturation_vapour_pressure(tmax) + saturation_vapour_pressure(tmin)) / 2


def slope_vapour_pressure_curve(temperature: float) -> float:
    """Eq. 13: delta=4098 e°(T)/(T+237.3)^2, kPa/°C; T in [-100,100] °C."""
    t = _temperature("temperature", temperature)
    return 4098 * saturation_vapour_pressure(t) / (t + 237.3) ** 2


def actual_vapour_pressure_from_dewpoint(tdew: float) -> float:
    """Eq. 14: ea=e°(Tdew), kPa; dewpoint in [-100,100] °C."""
    return saturation_vapour_pressure(tdew)


def actual_vapour_pressure_from_rh(tmax: float, tmin: float,
                                  rh_max: float, rh_min: float) -> float:
    """Eq. 17: ea=[e°(Tmin) RHmax+e°(Tmax) RHmin]/200, kPa.

    Ordered temperatures in °C; 0 <= RHmin <= RHmax <= 100 percent.
    """
    tmax, tmin = _temperatures(tmax, tmin)
    hi, lo = _number("rh_max", rh_max, 0, 100), _number("rh_min", rh_min, 0, 100)
    if lo > hi:
        raise ValueError("rh_min must be <= rh_max")
    return (saturation_vapour_pressure(tmin) * hi + saturation_vapour_pressure(tmax) * lo) / 200


def actual_vapour_pressure_from_rh_max(tmin: float, rh_max: float) -> float:
    """Eq. 18: ea=e°(Tmin) RHmax/100, kPa; Tmin °C and RHmax in [0,100] %."""
    return saturation_vapour_pressure(tmin) * _number("rh_max", rh_max, 0, 100) / 100


def actual_vapour_pressure_from_rh_mean(tmax: float, tmin: float, rh_mean: float) -> float:
    """Eq. 19: ea=es RHmean/100, kPa; ordered extrema °C, RHmean [0,100] %."""
    return mean_saturation_vapour_pressure(tmax, tmin) * _number("rh_mean", rh_mean, 0, 100) / 100


def actual_vapour_pressure_from_tmin(tmin: float, ko: float = 0) -> float:
    """Eq. 48, with aridity correction: ea=e°(Tmin-ko), kPa.

    Tmin is °C, ko is a nonnegative °C difference; corrected dewpoint must
    remain in [-100,100] °C. FAO suggests 2–3 °C for some arid locations.
    """
    return saturation_vapour_pressure(_temperature("tmin", tmin) - _number("ko", ko, 0))


def actual_vapour_pressure_from_wet_bulb(tdry: float, twet: float, pressure: float,
                                        coefficient: float = 0.000662) -> float:
    """Eqs. 15–16: ea=e°(Twet)-a P (Tdry-Twet), kPa.

    Temperatures °C with Twet <= Tdry, positive P kPa and a °C⁻¹.
    Default a is for an aspirated psychrometer; reject negative inferred ea.
    """
    tdry, twet = _temperatures(tdry, twet)
    ea = saturation_vapour_pressure(twet) - _positive("coefficient", coefficient) * _positive("pressure", pressure) * (tdry - twet)
    return _number("inferred ea", ea, 0)


def actual_vapour_pressure_hourly(temperature: float, rh: float) -> float:
    """Eq. 54: ea=e°(Thr) RHhr/100, kPa; Thr °C and RHhr in [0,100] %."""
    return saturation_vapour_pressure(temperature) * _number("rh", rh, 0, 100) / 100


def relative_humidity(ea: float, temperature: float) -> float:
    """Eq. 10: RH=100 ea/e°(T), percent; nonnegative ea kPa, T °C.

    Values above 100 are retained to expose supersaturation/inconsistent data.
    """
    return 100 * _number("ea", ea, 0) / saturation_vapour_pressure(temperature)


def vapour_pressure_deficit(es: float, ea: float) -> float:
    """VPD=es-ea, kPa; both pressures nonnegative; signed supersaturation retained."""
    return _number("es", es, 0) - _number("ea", ea, 0)


def radiation_to_evaporation(radiation: float) -> float:
    """Eq. 20: 0.408 R, mm per period for finite signed R in MJ/m² per period."""
    return 0.408 * _number("radiation", radiation)


def day_of_year(day: date) -> int:
    """Calendar day J in [1,366]; accepts datetime.date, rejects datetime/string."""
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValueError("date must be a datetime.date, not datetime or text")
    return day.timetuple().tm_yday


def latitude_radians(latitude: float) -> float:
    """Eq. 22: phi=pi latitude/180; finite latitude in [-90,90] degrees north."""
    return math.radians(_number("latitude", latitude, -90, 90))


def inverse_relative_distance_earth_sun(j: int) -> float:
    """Eq. 23: dr=1+0.033 cos(2pi J/365), dimensionless; integer J in [1,366]."""
    return 1 + 0.033 * math.cos(2 * math.pi * _julian_day(j) / 365)


def solar_declination(j: int) -> float:
    """Eq. 24: delta=0.409 sin(2pi J/365-1.39), radians; integer J in [1,366]."""
    return 0.409 * math.sin(2 * math.pi * _julian_day(j) / 365 - 1.39)


def sunset_hour_angle(latitude: float, declination: float) -> float:
    """Eq. 25: acos(-tan(phi)tan(delta)), radians, polar-safe.

    Latitude and declination are radians in [-pi/2,pi/2]. Return 0 for
    polar night, pi for continuous daylight, pi/2 at an exact polar equinox.
    Uses the equivalent sine/cosine ratio to avoid tan at the poles.
    """
    phi = _number("latitude radians", latitude, -math.pi / 2, math.pi / 2)
    dec = _number("declination", declination, -math.pi / 2, math.pi / 2)
    a, b = math.sin(phi) * math.sin(dec), math.cos(phi) * math.cos(dec)
    if b <= 1e-15:
        return math.pi if a > 0 else 0.0 if a < 0 else math.pi / 2
    return math.acos(max(-1.0, min(1.0, -a / b)))


def extraterrestrial_radiation(latitude: float, j: int) -> float:
    """Eq. 21: daily Ra, MJ/m²/day; latitude RADIANS, integer J [1,366].

    Ra=(1440/pi) 0.0820 dr [ws sin(phi)sin(delta)+cos(phi)cos(delta)sin(ws)].
    Polar night is exactly zero; roundoff cannot produce negative radiation.
    """
    dec = solar_declination(j)
    ws = sunset_hour_angle(latitude, dec)
    return max(0.0, 1440 / math.pi * 0.0820 * inverse_relative_distance_earth_sun(j) *
               (ws * math.sin(latitude) * math.sin(dec) + math.cos(latitude) * math.cos(dec) * math.sin(ws)))


def daylight_hours(sunset_angle: float) -> float:
    """Eq. 34: N=24 ws/pi, hours/day; sunset angle radians in [0,pi]."""
    return 24 / math.pi * _number("sunset_angle", sunset_angle, 0, math.pi)


def seasonal_correction_angle(j: int) -> float:
    """Eq. 33: b=2pi(J-81)/364, radians; integer J in [1,366]."""
    return 2 * math.pi * (_julian_day(j) - 81) / 364


def seasonal_time_correction(j: int) -> float:
    """Eq. 32: Sc=.1645 sin(2b)-.1255 cos(b)-.025 sin(b), hours; J [1,366]."""
    b = seasonal_correction_angle(j)
    return 0.1645 * math.sin(2 * b) - 0.1255 * math.cos(b) - 0.025 * math.sin(b)


def solar_time_angle(time: float, timezone_longitude: float, longitude: float, j: int) -> float:
    """Eq. 31: w=pi/12[t+.06667(Lz-Lm)+Sc-12], radians.

    Clock midpoint t in [0,24] hours, longitudes in [0,360] degrees WEST.
    The longitude difference is wrapped to [-180,180] across Greenwich.
    """
    t = _number("time", time, 0, 24)
    lz = _number("timezone_longitude", timezone_longitude, 0, 360)
    lm = _number("longitude", longitude, 0, 360)
    difference = (lz - lm + 180) % 360 - 180
    return math.pi / 12 * (t + 0.06667 * difference + seasonal_time_correction(j) - 12)


def solar_time_angle_bounds(midpoint_angle: float, duration: float = 1) -> Tuple[float, float]:
    """Eqs. 29–30: w1,w2=w ± pi duration/24, radians; duration in (0,1] h."""
    w = _number("midpoint_angle", midpoint_angle, -2 * math.pi, 2 * math.pi)
    duration = _positive("duration", duration)
    if duration > 1:
        raise ValueError("duration must be <= 1 hour")
    return w - math.pi * duration / 24, w + math.pi * duration / 24


def extraterrestrial_radiation_hourly(latitude: float, j: int, start_angle: float,
                                     end_angle: float) -> float:
    """Eq. 28: integrated Ra, MJ/m²/interval; latitude and solar angles RADIANS.

    Ra=(720/pi)Gsc dr[(w2-w1)sin(phi)sin(delta)+cos(phi)cos(delta)(sin(w2)-sin(w1))].
    Ordered angles in [-pi,pi], interval <= pi/12 (one hour). Clips each
    endpoint to sunrise/sunset; wholly nocturnal intervals yield zero.
    """
    start = _number("start_angle", start_angle, -math.pi, math.pi)
    end = _number("end_angle", end_angle, -math.pi, math.pi)
    if end < start or end - start > math.pi / 12 + 1e-12:
        raise ValueError("angles must be ordered and span at most one hour")
    dec = solar_declination(j)
    ws = sunset_hour_angle(latitude, dec)
    start, end = max(start, -ws), min(end, ws)
    if end <= start:
        return 0.0
    return max(0.0, 720 / math.pi * 0.0820 * inverse_relative_distance_earth_sun(j) *
               ((end - start) * math.sin(latitude) * math.sin(dec) +
                math.cos(latitude) * math.cos(dec) * (math.sin(end) - math.sin(start))))


def _angstrom(a_s: float, b_s: float) -> Tuple[float, float]:
    a, b = _number("a_s", a_s, 0, 1), _number("b_s", b_s, 0, 1)
    if not 0 < a + b <= 1:
        raise ValueError("a_s+b_s must be in (0,1]")
    return a, b


def solar_radiation(ra: float, sunshine_hours: float, daylight: float,
                    a_s: float = 0.25, b_s: float = 0.5) -> float:
    """Eq. 35 (Angstrom): Rs=(as+bs n/N) Ra, MJ/m²/day.

    Nonnegative Ra; 0 <= n <= N <= 24 hours; coefficients nonnegative with
    0 < as+bs <= 1. When N=0, require n=Ra=0 and return zero.
    """
    ra = _number("ra", ra, 0)
    n, nmax = _number("sunshine_hours", sunshine_hours, 0, 24), _number("daylight", daylight, 0, 24)
    a, b = _angstrom(a_s, b_s)
    if n > nmax + 1e-9:
        raise ValueError("sunshine_hours must not exceed daylight")
    if nmax == 0:
        if n != 0 or ra != 0:
            raise ValueError("zero daylight requires zero sunshine and ra")
        return 0.0
    return (a + b * min(n / nmax, 1.0)) * ra


def solar_radiation_from_temperature(tmax: float, tmin: float, ra: float,
                                     coastal: bool = False, rso: Optional[float] = None,
                                     k_rs: Optional[float] = None) -> float:
    """Eq. 50: Rs=kRs sqrt(Tmax-Tmin) Ra, MJ/m²/day; extrema °C, Ra >= 0.

    kRs=0.16 inland or 0.19 coastal, °C⁻½; optional positive calibrated k_rs.
    If nonnegative Rso is supplied, cap Rs at Rso as FAO recommends.
    """
    tmax, tmin = _temperatures(tmax, tmin)
    if not isinstance(coastal, bool):
        raise ValueError("coastal must be bool")
    k = (0.19 if coastal else 0.16) if k_rs is None else _positive("k_rs", k_rs)
    rs = k * math.sqrt(tmax - tmin) * _number("ra", ra, 0)
    return rs if rso is None else min(rs, _number("rso", rso, 0))


def clear_sky_radiation(ra: float, altitude: float = 0,
                        a_s: Optional[float] = None, b_s: Optional[float] = None) -> float:
    """Eqs. 36–37: Rso=(as+bs)Ra or (0.75+0.00002z)Ra, MJ/m²/period.

    Ra >= 0, z in [-1000,11000] m; provide BOTH calibrated coefficients
    (nonnegative, sum in (0,1]) or neither. Coefficients take precedence.
    """
    ra, z = _number("ra", ra, 0), _number("altitude", altitude, -1000, 11000)
    if (a_s is None) != (b_s is None):
        raise ValueError("provide both a_s and b_s, or neither")
    if a_s is not None:
        a, b = _angstrom(a_s, b_s)
        return (a + b) * ra
    return (0.75 + 0.00002 * z) * ra


def net_shortwave_radiation(rs: float, albedo: float = 0.23) -> float:
    """Eq. 38: Rns=(1-albedo)Rs, MJ/m²/period; Rs >= 0, albedo in [0,1]."""
    return (1 - _number("albedo", albedo, 0, 1)) * _number("rs", rs, 0)


def net_longwave_radiation(tmax: float, tmin: float, ea: float, rs: float, rso: float,
                           cloudiness_ratio: Optional[float] = None,
                           hourly: bool = False) -> float:
    """Eq. 39: Rnl=sigma mean(TK^4)(.34-.14 sqrt(ea))(1.35 Rs/Rso-.35).

    Ordered extrema °C, ea kPa >= 0, Rs and Rso MJ/m²/period >= 0.
    TK=T+273.16 follows FAO; sigma=4.903e-9 for daily periods. For hourly
    output MJ/m²/h, use hourly=True and tmax=tmin=Thr (sigma divided by 24).
    Ratio is capped at 1, as published; no undocumented lower clipping or
    emissivity clipping is applied. Very low ratios/high ea extrapolate the
    empirical equation and can yield a negative Rnl.

    Rso=0 requires an explicit cloudiness_ratio in [0,1], e.g. a measured
    preceding daylight ratio. No division by zero or implicit polar estimate.
    An explicit ratio overrides Rs/Rso for nighttime cloudiness information.
    """
    tmax, tmin = _temperatures(tmax, tmin)
    ea, rs, rso = _number("ea", ea, 0), _number("rs", rs, 0), _number("rso", rso, 0)
    if not isinstance(hourly, bool):
        raise ValueError("hourly must be bool")
    if hourly and tmax != tmin:
        raise ValueError("hourly longwave requires tmax=tmin=hourly temperature")
    if cloudiness_ratio is None:
        if rso == 0:
            raise ValueError("cloudiness_ratio required when rso is zero")
        ratio = min(rs / rso, 1.0)
    else:
        ratio = _number("cloudiness_ratio", cloudiness_ratio, 0, 1)
    sigma = 4.903e-9 / (24 if hourly else 1)
    return sigma * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * ratio - 0.35)


def net_radiation(rns: float, rnl: float) -> float:
    """Eq. 40: Rn=Rns-Rnl, signed MJ/m²/period; Rns >= 0, finite signed Rnl."""
    return _number("rns", rns, 0) - _number("rnl", rnl)


def soil_heat_flux(temperature: float, previous_temperature: float, interval: float,
                    depth: float, heat_capacity: float = 2.1) -> float:
    """Eq. 41: G=cs(T-Tprevious) depth/interval, MJ/m²/day.

    Temperatures °C; interval > 0 days, depth > 0 m, heat capacity > 0
    MJ/m³/°C. Positive G means soil warming; choose depth for the interval.
    """
    t, previous = _temperature("temperature", temperature), _temperature("previous_temperature", previous_temperature)
    return _positive("heat_capacity", heat_capacity) * (t - previous) * _positive("depth", depth) / _positive("interval", interval)


def soil_heat_flux_daily() -> float:
    """Eq. 42: G=0 MJ/m²/day for grass on daily or ten-day periods."""
    return 0.0


def soil_heat_flux_monthly(previous_temperature: float, next_temperature: float) -> float:
    """Eq. 43: G=0.07(Tnext-Tprevious), MJ/m²/day; monthly mean T in °C."""
    return 0.07 * (_temperature("next_temperature", next_temperature) - _temperature("previous_temperature", previous_temperature))


def soil_heat_flux_monthly_previous(temperature: float, previous_temperature: float) -> float:
    """Eq. 44: G=0.14(Tcurrent-Tprevious), MJ/m²/day; monthly mean T in °C."""
    return 0.14 * (_temperature("temperature", temperature) - _temperature("previous_temperature", previous_temperature))


def soil_heat_flux_hourly(rn: float, daytime: Optional[bool] = None) -> float:
    """Eqs. 45–46: G=0.1 Rn by day, 0.5 Rn by night, MJ/m²/h.

    Finite signed Rn; daytime bool or None. None infers day from Rn > 0;
    pass daytime explicitly when observed sunlight and Rn sign differ.
    """
    rn = _number("rn", rn)
    if daytime is not None and not isinstance(daytime, bool):
        raise ValueError("daytime must be bool or None")
    day = rn > 0 if daytime is None else daytime
    return (0.1 if day else 0.5) * rn


def wind_speed_2m(wind: float, height: float = 2) -> float:
    """Eq. 47: u2=uz 4.87/ln(67.8z-5.42), m/s; uz >= 0, z > 6.42/67.8 m.

    Heights must give a positive logarithm. At 2 m return the measurement
    unchanged (the published rounded coefficients otherwise differ by 0.02%).
    No artificial wind floor is imposed by this equation.
    """
    wind, height = _number("wind", wind, 0), _positive("height", height)
    if height <= 6.42 / 67.8:
        raise ValueError("height too low for the FAO logarithmic wind profile")
    return wind if height == 2 else wind * 4.87 / math.log(67.8 * height - 5.42)


def _penman_monteith(tmean: float, u2: float, es: float, ea: float, delta: float,
                     gamma: float, rn: float, g: float, coefficient: float) -> float:
    t = _temperature("tmean", tmean)
    u = _number("u2", u2, 0)
    vpd = vapour_pressure_deficit(es, ea)
    d, gam = _positive("delta", delta), _positive("gamma", gamma)
    energy = _number("rn", rn) - _number("g", g)
    result = (0.408 * d * energy + gam * coefficient / (t + 273) * u * vpd) / (d + gam * (1 + 0.34 * u))
    return _number("et0", result)


def penman_monteith_daily(tmean: float, u2: float, es: float, ea: float,
                          delta: float, gamma: float, rn: float, g: float = 0) -> float:
    """Eq. 6: ET0=[.408 delta(Rn-G)+gamma 900 u2(es-ea)/(T+273)] /
    [delta+gamma(1+.34 u2)], signed mm/day.

    T °C, u2 >= 0 m/s, es and ea >= 0 kPa, delta/gamma > 0 kPa/°C;
    finite signed Rn and G in MJ/m²/day. Default daily G=0.
    """
    return _penman_monteith(tmean, u2, es, ea, delta, gamma, rn, g, 900)


def penman_monteith_hourly(tmean: float, u2: float, es: float, ea: float,
                           delta: float, gamma: float, rn: float,
                           g: Optional[float] = None, daytime: Optional[bool] = None) -> float:
    """Eq. 53: hourly Eq. 6 with 37 replacing 900, signed mm/h.

    Same validated units as daily, except Rn and G are MJ/m²/h and
    es=e°(Thr). G defaults to Eqs. 45–46; may be passed explicitly.
    FAO's 0.34 denominator is retained in both day and night periods.
    """
    default_g = soil_heat_flux_hourly(rn, daytime)
    return _penman_monteith(tmean, u2, es, ea, delta, gamma, rn, default_g if g is None else g, 37)


def hargreaves(tmax: float, tmin: float, ra: float, tmean: Optional[float] = None) -> float:
    """Eq. 52: ET0=.0023(Tmean+17.8)sqrt(Tmax-Tmin)(.408 Ra), mm/day.

    Ordered extrema °C, Ra >= 0 MJ/m²/day (NOT equivalent mm/day).
    Optional mean °C must lie within extrema. The explicit .408 conversion
    is essential: FAO Eq. 52 specifies Ra in equivalent mm/day. Signed
    extrapolation is retained below -17.8 °C; the high-level API clips it.
    """
    tmax, tmin = _temperatures(tmax, tmin)
    t = mean_temperature(tmax, tmin) if tmean is None else _temperature("tmean", tmean)
    if not tmin <= t <= tmax:
        raise ValueError("tmean must lie within tmin and tmax")
    return 0.0023 * (t + 17.8) * math.sqrt(tmax - tmin) * radiation_to_evaporation(_number("ra", ra, 0))


def calculate_daily_et0(weather: Mapping[str, Any], latitude: float,
                         altitude: float = 0, wind_height: float = 2,
                         method: str = "pm", coastal: bool = False, ko: float = 0,
                         *, g: float = 0, a_s: float = 0.25, b_s: float = 0.5,
                         polar_cloudiness_ratio: float = 0.5) -> Dict[str, Any]:
    """Calculate daily ET0 in mm/day; latitude is DEGREES north.

    Required weather: date (datetime.date), tmax/tmin (°C). Optional tmean
    must be within extrema. Humidity priority: tdew, RHmax+RHmin, RHmax,
    RHmean, then Tdew=Tmin-ko. An isolated RHmin is retained in the result
    but cannot determine ea by FAO Eqs. 17–19. Wind is m/s at wind_height;
    absent wind gives u2=2 m/s directly. Radiation priority: rs (MJ/m²/day),
    sunshine_hours (h), temperature estimate (capped at Rso). rain (mm/day)
    is validated when supplied but does not affect reference ET.

    Missing keys and None are equivalent. All supplied recognized numeric
    fields are validated, including lower-priority inputs. Unknown fields
    are ignored. Invalid data raise ValueError, never silently become missing.
    method='pm' always uses PM with flagged estimates. 'hargreaves' explicitly
    uses Eq. 52. Optional 'auto' chooses Hargreaves ONLY when wind, humidity,
    sunshine and rs are all absent; rain does not preclude temperature-only.

    Returns et0 (nonnegative float), method, flags (list[str]), u2 (float),
    rh_min (observed or estimated %, capped at 100), es/ea (kPa), ra/rs/rso/
    rn (MJ/m²/day), delta/gamma (kPa/°C), tmean (°C), and g (MJ/m²/day).
    Hargreaves returns rn/rs/rso=None; unused humidity is not synthesized.
    Polar-night PM uses polar_cloudiness_ratio in [0,1], explicitly flagged;
    it is an assumption, not a measured cloud state. Supply local information
    where available. Negative daily ET is clipped to zero with a flag.
    """
    if not isinstance(weather, Mapping):
        raise ValueError("weather must be a mapping")
    if method not in ("pm", "hargreaves", "auto"):
        raise ValueError("method must be 'pm', 'hargreaves', or 'auto'")
    if not isinstance(coastal, bool):
        raise ValueError("coastal must be bool")
    phi = latitude_radians(latitude)
    pressure = atmospheric_pressure(altitude)
    wind_speed_2m(0, wind_height)  # Validate even when wind is missing.
    ko, g = _number("ko", ko, 0), _number("g", g)
    a_s, b_s = _angstrom(a_s, b_s)
    polar_ratio = _number("polar_cloudiness_ratio", polar_cloudiness_ratio, 0, 1)
    j = day_of_year(weather.get("date"))
    tmax, tmin = _temperatures(weather.get("tmax"), weather.get("tmin"))
    tmean = mean_temperature(tmax, tmin) if weather.get("tmean") is None else _temperature("tmean", weather["tmean"])
    if not tmin <= tmean <= tmax:
        raise ValueError("tmean must lie within tmin and tmax")
    values = {}
    for key in ("rh_max", "rh_min", "rh_mean", "tdew", "wind", "sunshine_hours", "rs", "rain"):
        value = weather.get(key)
        if value is not None:
            if key == "tdew":
                value = _temperature(key, value)
                if value > tmax:
                    raise ValueError("tdew must not exceed tmax")
            else:
                upper = 100 if key.startswith("rh_") else 24 if key == "sunshine_hours" else None
                value = _number(key, value, 0, upper)
        values[key] = value
    hi, lo, mean = values["rh_max"], values["rh_min"], values["rh_mean"]
    if hi is not None and lo is not None and lo > hi:
        raise ValueError("rh_min must be <= rh_max")
    if mean is not None and ((lo is not None and mean < lo) or (hi is not None and mean > hi)):
        raise ValueError("rh_mean must lie within supplied humidity extrema")
    ra = extraterrestrial_radiation(phi, j)
    daylight = daylight_hours(sunset_hour_angle(phi, solar_declination(j)))
    if values["sunshine_hours"] is not None and values["sunshine_hours"] > daylight + 1e-9:
        raise ValueError("sunshine_hours must not exceed astronomical daylight")
    flags = []
    if method == "auto":
        temperature_only = all(values[k] is None for k in ("rh_max", "rh_min", "rh_mean", "tdew", "wind", "sunshine_hours", "rs"))
        method = "hargreaves" if temperature_only else "pm"
        if temperature_only:
            flags.append("auto_hargreaves_temperature_only")
    u2 = 2.0 if values["wind"] is None else wind_speed_2m(values["wind"], wind_height)
    if values["wind"] is None:
        flags.append("wind_estimated_2m_s")
    es = mean_saturation_vapour_pressure(tmax, tmin)
    ea = None
    if values["tdew"] is not None:
        ea = actual_vapour_pressure_from_dewpoint(values["tdew"])
    elif hi is not None and lo is not None:
        ea = actual_vapour_pressure_from_rh(tmax, tmin, hi, lo)
    elif hi is not None:
        ea = actual_vapour_pressure_from_rh_max(tmin, hi)
        flags.append("humidity_from_rh_max")
    elif mean is not None:
        ea = actual_vapour_pressure_from_rh_mean(tmax, tmin, mean)
        flags.append("humidity_from_rh_mean")
    elif method == "pm":
        ea = actual_vapour_pressure_from_tmin(tmin, ko)
        flags.append("humidity_estimated_tmin_ko")
    if ea is not None and ea > es:
        flags.append("supersaturation_ea_above_es")
    if lo is None and ea is not None:
        lo = min(100.0, relative_humidity(ea, tmax))
        flags.append("rh_min_estimated")
    delta, gamma = slope_vapour_pressure_curve(tmean), psychrometric_constant(pressure)
    rs = rso = rn = None
    if method == "hargreaves":
        flags.append("hargreaves_temperature_method")
        et0 = hargreaves(tmax, tmin, ra, tmean)
    else:
        # Calibrated Angstrom coefficients also determine Eq. 36 Rso.
        rso = clear_sky_radiation(ra, altitude) if (a_s, b_s) == (0.25, 0.5) else clear_sky_radiation(ra, altitude, a_s, b_s)
        if values["rs"] is not None:
            rs = values["rs"]
        elif values["sunshine_hours"] is not None:
            rs = solar_radiation(ra, values["sunshine_hours"], daylight, a_s, b_s)
            flags.append("radiation_from_sunshine")
        else:
            rs = solar_radiation_from_temperature(tmax, tmin, ra, coastal, rso)
            flags.append("radiation_estimated_temperature")
        if rs > rso:
            flags.append("rs_above_clear_sky")
        ratio = None
        if rso == 0:
            ratio = polar_ratio
            flags.append("polar_night_cloudiness_assumed")
        elif rs / rso < 0.3:
            flags.append("longwave_low_radiation_ratio")
        if ea > (0.34 / 0.14) ** 2:
            flags.append("longwave_high_vapour_pressure")
        rnl = net_longwave_radiation(tmax, tmin, ea, rs, rso, ratio)
        rn = net_radiation(net_shortwave_radiation(rs), rnl)
        et0 = penman_monteith_daily(tmean, u2, es, ea, delta, gamma, rn, g)
    if et0 < 0:
        flags.append("negative_et0_clipped")
    return {"et0": float(max(0.0, et0)), "method": method, "flags": flags,
            "u2": float(u2), "rh_min": lo, "rn": rn, "ea": ea, "es": es,
            "ra": ra, "rs": rs, "rso": rso, "delta": delta, "gamma": gamma,
            "tmean": tmean, "g": g}
