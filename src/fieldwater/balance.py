"""Daily single-Kc root-zone balance and irrigation management (FAO-56, ch. 8).

The daily order is root growth, rainfall/capillary supply, morning irrigation,
stress-limited evapotranspiration, then drainage. All depths are millimetres.
Newly rooted soil has a configurable depletion fraction; its added deficit is
reported explicitly, so eq. 85 conserves water even while root depth changes.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .crops import Crop, adjust_kc, kc_curve, root_depth
from .errors import DataError
from .et0 import calculate_daily_et0
from .soils import Soil, adjust_depletion_fraction, total_available_water


@dataclass(frozen=True)
class ScheduleConfig:
    """Management settings; capacity is GROSS application in mm/day.

    initial_depletion is mm in the initial root zone. subsoil_depletion is a
    fraction of TAW in newly rooted soil (default 0: field capacity).
    deficit_fraction is target volumetric water content / theta_FC.
    mad overrides the irrigation trigger only; physiological p still sets Ks.
    """

    strategy: str = "refill"
    efficiency: float = 0.75
    mad: Optional[float] = None
    fixed_depth: float = 25.0
    interval: int = 7
    deficit_fraction: float = 0.9
    max_mm_day: Optional[float] = None
    initial_depletion: float = 0.0
    subsoil_depletion: float = 0.0
    rain_method: str = "fixed"
    rain_fraction: float = 0.8
    method: str = "pm"
    kc_ini: Optional[float] = None
    climate_adjustment: bool = True


@dataclass
class Schedule:
    """Full daily results and an auditable season summary."""

    daily: List[Dict[str, Any]]
    summary: Dict[str, Any]

    @property
    def calendar(self) -> List[Dict[str, Any]]:
        """Return irrigation events, including supplied historical applications."""
        return [row for row in self.daily if row["irrigation_net"] > 0]


def stress_coefficient(dr: float, raw: float, taw: float) -> float:
    """Return Ks (eq. 84), dimensionless, clamped to 0..1.

    Dr is depletion, RAW readily available water and TAW total available water,
    all in mm. No water stress occurs at Dr <= RAW.
    """
    if not all(math.isfinite(value) for value in (dr, raw, taw)):
        raise DataError("Ks inputs must be finite")
    if taw <= 0 or raw < 0 or raw >= taw or dr < 0:
        raise DataError("Ks needs TAW > RAW >= 0 and Dr >= 0")
    return 1.0 if dr <= raw else max(0.0, min(1.0, (taw - dr) / (taw - raw)))


def effective_rainfall(rain: float, method: str = "fixed", fraction: float = 0.8) -> float:
    """Estimate effective rain in mm using fixed fraction or monthly USDA-SCS.

    SCS: Pe=P(125-0.2P)/125 at P<=250 mm/month, else 125+0.1P.
    For method='scs', input MUST be a monthly total; run_schedule apportions
    the result to daily rain. This empirical option is not a FAO-56 equation.
    Soil storage overflow is handled separately as deep percolation.
    """
    if not math.isfinite(rain) or rain < 0:
        raise DataError("rain must be finite and nonnegative")
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise DataError("rain fraction must be 0..1")
    if method == "fixed":
        return fraction * rain
    if method == "scs":
        return rain * (125 - 0.2 * rain) / 125 if rain <= 250 else 125 + 0.1 * rain
    raise DataError("rain method must be fixed or scs")


def deep_percolation(supply: float, depletion: float, etc_adj: float) -> float:
    """Drainage beyond field capacity in mm (eq. 88 with optional CR supply)."""
    if not all(math.isfinite(value) and value >= 0 for value in (supply, depletion, etc_adj)):
        raise DataError("drainage inputs must be finite and nonnegative")
    return max(0.0, supply - depletion - etc_adj)


def relative_yield(etc: float, etc_adj: float, ky: Optional[float]) -> Optional[float]:
    """Estimate Ya/Ym by eq. 90, bounded to 0..1; None if Ky/ETc unavailable."""
    if not all(math.isfinite(value) and value >= 0 for value in (etc, etc_adj)):
        raise DataError("ET totals must be finite and nonnegative")
    if ky is None or etc == 0:
        return None
    if not math.isfinite(ky) or ky < 0:
        raise DataError("Ky must be finite and nonnegative")
    return max(0.0, min(1.0, 1 - ky * (1 - min(1.0, etc_adj / etc))))


def _validate(config: ScheduleConfig, crop: Crop, soil: Soil) -> None:
    if config.strategy not in {"refill", "fixed", "interval", "deficit", "none"}:
        raise DataError("strategy must be refill, fixed, interval, deficit, or none")
    for name in ("efficiency", "fixed_depth", "deficit_fraction", "initial_depletion", "subsoil_depletion", "rain_fraction"):
        if not math.isfinite(getattr(config, name)):
            raise DataError(f"{name} must be finite")
    if not 0 < config.efficiency <= 1:
        raise DataError("efficiency must be >0 and <=1")
    if config.mad is not None and (not math.isfinite(config.mad) or not 0.1 <= config.mad <= 0.8):
        raise DataError("MAD must be 0.1..0.8")
    if config.fixed_depth <= 0 or isinstance(config.interval, bool) or not isinstance(config.interval, int) or config.interval < 1:
        raise DataError("fixed_depth and integer interval must be positive")
    if config.max_mm_day is not None and (not math.isfinite(config.max_mm_day) or config.max_mm_day <= 0):
        raise DataError("max_mm_day must be positive gross mm/day")
    if not 0 <= config.subsoil_depletion <= 1 or not 0 <= config.rain_fraction <= 1:
        raise DataError("subsoil and rain fractions must be 0..1")
    if not 0 < config.deficit_fraction <= 1:
        raise DataError("deficit_fraction must be >0 and <=1")
    if config.strategy == "deficit" and config.deficit_fraction * soil.theta_fc <= soil.theta_wp:
        raise DataError("deficit target must exceed wilting-point water content")
    initial_taw = total_available_water(soil.theta_fc, soil.theta_wp, crop.zr_min)
    if not 0 <= config.initial_depletion <= initial_taw:
        raise DataError(f"initial depletion must be 0..{initial_taw:g} mm")
    if config.kc_ini is not None and (not math.isfinite(config.kc_ini) or config.kc_ini < 0):
        raise DataError("Kc ini must be finite and nonnegative")
    effective_rainfall(0, config.rain_method, config.rain_fraction)


def _rain_inputs(weather: Sequence[Mapping[str, Any]], config: ScheduleConfig) -> List[Tuple[float, float, List[str]]]:
    available: List[float] = []
    runoff_values: List[float] = []
    months: Dict[Tuple[int, int], List[int]] = {}
    for index, row in enumerate(weather):
        rain = float(row.get("rain") or 0)
        runoff = float(row.get("runoff") or 0)
        if not all(math.isfinite(value) and value >= 0 for value in (rain, runoff)) or runoff > rain:
            raise DataError("rain/runoff must be nonnegative and runoff <= rain")
        available.append(rain - runoff)
        runoff_values.append(runoff)
        day = row["date"]
        months.setdefault((day.year, day.month), []).append(index)
    fractions: Dict[int, Tuple[float, List[str]]] = {}
    if config.rain_method == "scs":
        for (year, month), indices in months.items():
            total = math.fsum(available[index] for index in indices)
            ratio = effective_rainfall(total, "scs") / total if total else 0.0
            flags = ["rain_scs_monthly_apportioned"]
            if len(indices) != calendar.monthrange(year, month)[1]:
                flags.append("rain_scs_partial_month")
            for index in indices:
                fractions[index] = ratio, flags
    result = []
    for index, amount in enumerate(available):
        ratio, flags = fractions.get(index, (config.rain_fraction, ["rain_fixed_fraction"]))
        result.append((amount * ratio, runoff_values[index], list(flags)))
    return result


def run_schedule(weather: Sequence[Mapping[str, Any]], site: Mapping[str, Any],
                 crop: Crop, soil: Soil, planting: date,
                 config: Optional[ScheduleConfig] = None) -> Schedule:
    """Simulate planting through crop maturity, returning daily records and totals.

    Input dates must be consecutive; weather before planting is ignored.
    A partial season is permitted and marked in the summary. An optional
    irrigation_net weather column replaces that day's automatic decision.
    SCS monthly apportionment uses all rows supplied (including forecasts),
    so its daily timing is retrospective; fixed rain is the default.
    """
    config = config or ScheduleConfig()
    _validate(config, crop, soil)
    if not weather:
        raise DataError("no weather observations")
    for index, row in enumerate(weather):
        if not isinstance(row.get("date"), date):
            raise DataError("weather date must be datetime.date")
        if index and row["date"] != weather[index - 1]["date"] + timedelta(days=1):
            raise DataError("weather dates must be consecutive and ascending")
    end = planting + timedelta(days=sum(crop.stages))
    rain_inputs = _rain_inputs(weather, config)
    selected = [(row, rain_inputs[index]) for index, row in enumerate(weather)
                if planting <= row["date"] < end]
    if not selected or selected[0][0]["date"] != planting:
        raise DataError("weather must include the planting date")
    et_values = [calculate_daily_et0(
        row, latitude=site["lat"], altitude=site.get("altitude", 0.0),
        wind_height=row.get("wind_height") or site.get("wind_height", 2.0),
        method=config.method, coastal=site.get("coastal", False), ko=site.get("ko", 0.0))
        for row, _ in selected]
    # Eqs. 62/65 use mean conditions for their respective stages, preserving
    # a piecewise linear Kc curve rather than changing the endpoints each day.
    climate_flags: List[str] = []
    if crop.key == "rice":
        climate_flags.append("rice_root_zone_only_no_ponding_model")
    mid, late = crop.kc_mid, crop.kc_end
    if config.climate_adjustment:
        boundaries = (sum(crop.stages[:2]), sum(crop.stages[:3]), sum(crop.stages))
        adjusted = []
        for value, lower, upper in ((mid, boundaries[0], boundaries[1]),
                                    (late, boundaries[1], boundaries[2])):
            stage_weather = [et for index, et in enumerate(et_values) if lower <= index < upper and et.get("rh_min") is not None]
            if not stage_weather:
                climate_flags.append("kc_climate_unadjusted_missing_stage_weather")
                adjusted.append(value)
                continue
            wind = math.fsum(et["u2"] for et in stage_weather) / len(stage_weather)
            humidity = math.fsum(et["rh_min"] for et in stage_weather) / len(stage_weather)
            adjusted.append(adjust_kc(value, wind, humidity, crop.height))
            if len(stage_weather) < upper - lower:
                climate_flags.append("kc_climate_partial_stage_mean")
        mid, late = adjusted
    daily: List[Dict[str, Any]] = []
    previous_dr = config.initial_depletion
    previous_taw = total_available_water(soil.theta_fc, soil.theta_wp, crop.zr_min)
    for (row, (rain_eff, runoff, rain_flags)), et in zip(selected, et_values):
        day = row["date"]
        age = (day - planting).days
        zr = root_depth(age, crop)
        taw = total_available_water(soil.theta_fc, soil.theta_wp, zr)
        growth = max(0.0, taw - previous_taw) * config.subsoil_depletion
        dr_start = previous_dr + growth
        flags = list(row.get("input_flags", [])) + list(et["flags"]) + rain_flags + climate_flags
        kc = kc_curve(age, crop, kc_ini=config.kc_ini, kc_mid=mid, kc_end=late)
        etc = kc * et["et0"]
        p = adjust_depletion_fraction(crop.p, etc)
        raw = p * taw
        trigger = (config.mad if config.mad is not None else p) * taw
        cr = float(row.get("capillary_rise") or 0)
        if not math.isfinite(cr) or cr < 0:
            raise DataError("capillary rise must be finite and nonnegative")
        wet_dr = max(0.0, dr_start - rain_eff - cr)
        requested = 0.0
        observed = row.get("irrigation_net")
        if observed is not None:
            requested = float(observed)
            if not math.isfinite(requested) or requested < 0:
                raise DataError("observed irrigation must be finite and nonnegative")
            flags.append("irrigation_observed")
        elif config.strategy == "interval" and age % config.interval == 0:
            requested = config.fixed_depth
        elif wet_dr >= trigger:
            if config.strategy == "refill":
                requested = wet_dr
            elif config.strategy == "fixed":
                requested = config.fixed_depth
            elif config.strategy == "deficit":
                target_dr = 1000 * soil.theta_fc * (1 - config.deficit_fraction) * zr
                requested = max(0.0, wet_dr - target_dr)
        gross = requested / config.efficiency
        # Historical observations are measurements, not subject to a future capacity cap.
        if observed is None and config.max_mm_day is not None and gross > config.max_mm_day:
            gross = config.max_mm_day
            flags.append("irrigation_capacity_limited")
        net = gross * config.efficiency
        supply = rain_eff + cr + net
        dr_after_wetting = max(0.0, dr_start - supply)
        ks = stress_coefficient(dr_after_wetting, raw, taw)
        actual = min(ks * etc, max(0.0, taw - dr_start + supply))
        if actual + 1e-12 < ks * etc:
            flags.append("et_limited_by_available_water")
        dp = deep_percolation(supply, dr_start, actual)
        dr = dr_start - supply + actual + dp
        # Only round floating-point noise at the physical bounds.
        if abs(dr) < 1e-12:
            dr = 0.0
        if abs(dr - taw) < 1e-12:
            dr = taw
        residual = dr - previous_dr - (growth - supply + actual + dp)
        result = {
            "date": day, "day": age, "et0": et["et0"], "method": et["method"],
            "kc": kc, "etc": etc, "etc_adj": actual, "ks": ks,
            "rain": float(row.get("rain") or 0), "runoff": runoff,
            "effective_rain": rain_eff, "rain_loss": float(row.get("rain") or 0) - rain_eff,
            "capillary_rise": cr, "root_depth": zr, "root_growth_depletion": growth,
            "taw": taw, "p": p, "raw": raw, "management_raw": trigger,
            "dr_start": dr_start, "dr_after_wetting": dr_after_wetting, "dr": dr,
            "irrigation_requested_net": requested, "irrigation_net": net,
            "irrigation_gross": gross, "deep_percolation": dp,
            "balance_error": residual, "is_forecast": bool(row.get("is_forecast", False)),
            "flags": list(dict.fromkeys(flags)),
        }
        daily.append(result)
        previous_dr, previous_taw = dr, taw
    totals = {key: math.fsum(row[key] for row in daily) for key in
              ("et0", "etc", "etc_adj", "rain", "runoff", "effective_rain", "rain_loss",
               "capillary_rise", "root_growth_depletion", "irrigation_net", "irrigation_gross", "deep_percolation")}
    balance_error = previous_dr - config.initial_depletion - math.fsum((
        totals["root_growth_depletion"], totals["etc_adj"], totals["deep_percolation"],
        -totals["effective_rain"], -totals["irrigation_net"], -totals["capillary_rise"]))
    complete = len(daily) == sum(crop.stages)
    yield_supported = complete and crop.key != "alfalfa"
    summary: Dict[str, Any] = {
        "crop": crop.name, "soil": soil.name, "planting": planting,
        "start": daily[0]["date"], "end": daily[-1]["date"], "days": len(daily),
        "complete_season": complete, "strategy": config.strategy,
        "efficiency": config.efficiency, "rain_method": config.rain_method,
        **totals, "initial_depletion": config.initial_depletion, "final_depletion": previous_dr,
        "balance_error": balance_error, "stress_days": sum(row["ks"] < 1 - 1e-12 for row in daily),
        "irrigation_events": sum(row["irrigation_net"] > 0 for row in daily),
        "ky": crop.ky,
        "relative_yield": relative_yield(totals["etc"], totals["etc_adj"], crop.ky) if yield_supported else None,
        "yield_note": ("Relative yield withheld: seasonal Ky is not a cutting-specific alfalfa coefficient."
                       if crop.key == "alfalfa" else
                       "Relative yield withheld for an incomplete season." if not complete else
                       "Relative yield unavailable: no single seasonal Ky selected." if crop.ky is None else
                       "Seasonal Ky approximation; ignores stress timing and non-water limits."),
        "stage_source": crop.stage_source,
        "crop_notes": crop.notes,
        "kc_mid_adjusted": mid, "kc_end_adjusted": late,
        "climate_note": "Kc endpoints use supplied stage-average weather, including forecasts; reruns may revise past Kc.",
    }
    return Schedule(daily, summary)


def next_irrigation(schedule: Schedule, as_of: date) -> Optional[Dict[str, Any]]:
    """First simulated irrigation strictly after the last observed date as_of.

    Returns None when no event occurs within the supplied weather horizon;
    this does not imply that irrigation will never be needed.
    """
    return next((row for row in schedule.calendar if row["date"] > as_of), None)
