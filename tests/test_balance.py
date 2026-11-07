"""Conservation, daily ordering, stress, and management policy tests."""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from fieldwater.balance import (ScheduleConfig, deep_percolation, effective_rainfall,
                                next_irrigation, relative_yield, run_schedule,
                                stress_coefficient)
from fieldwater.crops import get_crop
from fieldwater.errors import DataError
from fieldwater.soils import get_soil


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr("fieldwater.balance.calculate_daily_et0", lambda *args, **kwargs:
                        {"et0": 5.0, "method": "pm", "flags": [], "u2": 2.0, "rh_min": 45.0})
    crop = replace(get_crop("maize"), zr_min=.2, zr_max=1.0, stages=(2, 3, 3, 2))
    weather = [{"date": date(2025, 5, 1) + timedelta(days=day), "tmax": 25, "tmin": 10, "rain": 0.0}
               for day in range(10)]
    return weather, {"lat": 40}, crop, get_soil("loam"), date(2025, 5, 1)


def test_ks_at_and_below_raw():
    assert stress_coefficient(0, 50, 100) == 1
    assert stress_coefficient(50, 50, 100) == 1
    assert stress_coefficient(75, 50, 100) == .5
    assert stress_coefficient(100, 50, 100) == 0
    assert stress_coefficient(110, 50, 100) == 0


@pytest.mark.parametrize("dr,raw,taw", [(-1, 50, 100), (1, 100, 100), (1, -1, 100), (1, 0, 0), (float("nan"), 50, 100)])
def test_ks_invalid(dr, raw, taw):
    with pytest.raises(DataError):
        stress_coefficient(dr, raw, taw)


@pytest.mark.parametrize("rain,expected", [(0, 0), (100, 84), (250, 150), (300, 155)])
def test_scs_monthly_formula(rain, expected):
    assert effective_rainfall(rain, "scs") == pytest.approx(expected)


def test_fixed_rain_and_drainage():
    assert effective_rainfall(20, "fixed", .75) == 15
    assert deep_percolation(50, 10, 5) == 35
    assert deep_percolation(10, 50, 5) == 0


@pytest.mark.parametrize("rain,method,fraction", [(-1, "fixed", .8), (1, "unknown", .8), (1, "fixed", 1.1), (float("nan"), "scs", .8)])
def test_bad_rain_method(rain, method, fraction):
    with pytest.raises(DataError):
        effective_rainfall(rain, method, fraction)


@pytest.mark.parametrize("strategy", ["refill", "fixed", "interval", "deficit", "none"])
def test_balance_closes_all_strategies(model, strategy):
    weather, site, crop, soil, planting = model
    rng = random.Random(56)
    for row in weather:
        row.update(rain=rng.choice([0, 0, 35, 60]), capillary_rise=rng.random(), runoff=0)
    result = run_schedule(weather, site, crop, soil, planting,
                          ScheduleConfig(strategy=strategy, subsoil_depletion=.4, initial_depletion=10,
                                         max_mm_day=15, fixed_depth=35))
    s = result.summary
    # Depletion grows with ET and drainage, and falls with external supply.
    delta = s["final_depletion"] - s["initial_depletion"]
    inputs = s["effective_rain"] + s["irrigation_net"] + s["capillary_rise"]
    outputs = s["etc_adj"] + s["deep_percolation"]
    assert outputs - inputs + s["root_growth_depletion"] == pytest.approx(delta, abs=1e-9)
    assert abs(s["balance_error"]) < 1e-9
    for row in result.daily:
        assert abs(row["balance_error"]) < 1e-9
        assert 0 <= row["dr"] <= row["taw"]
        assert 0 <= row["etc_adj"] <= row["etc"]
        assert row["irrigation_gross"] <= 15 + 1e-12
        assert row["irrigation_net"] == pytest.approx(.75 * row["irrigation_gross"])


def test_refill_morning_and_capacity(model):
    result = run_schedule(*model, ScheduleConfig(initial_depletion=25, mad=.5, max_mm_day=10))
    event = result.calendar[0]
    assert event["irrigation_gross"] == 10
    assert event["irrigation_net"] == 7.5
    assert "irrigation_capacity_limited" in event["flags"]


def test_rain_avoids_unnecessary_irrigation(model):
    weather, site, crop, soil, planting = model
    weather[0]["rain"] = 100
    result = run_schedule(weather, site, crop, soil, planting, ScheduleConfig(initial_depletion=25))
    assert result.daily[0]["irrigation_net"] == 0
    assert result.daily[0]["deep_percolation"] > 0


def test_observed_irrigation_overrides_policy_and_capacity(model):
    weather, site, crop, soil, planting = model
    weather[0]["irrigation_net"] = 30
    weather[1]["irrigation_net"] = 0
    result = run_schedule(weather, site, crop, soil, planting,
                          ScheduleConfig(strategy="none", max_mm_day=1))
    assert result.daily[0]["irrigation_net"] == 30
    assert result.daily[0]["irrigation_gross"] == 40
    assert result.daily[1]["irrigation_net"] == 0
    assert "irrigation_observed" in result.daily[0]["flags"]


def test_root_growth_ledger(model):
    weather, site, crop, soil, planting = model
    result = run_schedule(weather, site, crop, soil, planting, ScheduleConfig(subsoil_depletion=.5))
    expected = 1000 * (soil.theta_fc - soil.theta_wp) * (crop.zr_max - crop.zr_min) * .5
    assert result.summary["root_growth_depletion"] == pytest.approx(expected)


def test_scs_apportionment_and_partial_flags(model):
    weather, site, crop, soil, planting = model
    for row in weather:
        row["rain"] = 10
    result = run_schedule(weather, site, crop, soil, planting, ScheduleConfig(rain_method="scs"))
    assert result.summary["effective_rain"] == 84
    assert "rain_scs_partial_month" in result.daily[0]["flags"]


def test_interval_starts_at_planting(model):
    result = run_schedule(*model, ScheduleConfig(strategy="interval", interval=3, fixed_depth=10))
    assert [row["day"] for row in result.calendar] == [0, 3, 6, 9]


def test_deficit_reaches_volumetric_target(model):
    weather, site, crop, soil, planting = model
    result = run_schedule(weather, site, crop, soil, planting,
                          ScheduleConfig(strategy="deficit", deficit_fraction=.9, mad=.2, initial_depletion=25))
    row = result.daily[0]
    expected_target = 1000 * soil.theta_fc * .1 * row["root_depth"]
    assert row["dr_after_wetting"] == pytest.approx(expected_target)


def test_stress_during_dry_nonirrigated_season(model):
    weather, site, crop, soil, planting = model
    crop = replace(crop, zr_max=.2)
    result = run_schedule(weather, site, crop, soil, planting, ScheduleConfig(strategy="none", initial_depletion=25))
    assert result.summary["stress_days"] > 0
    assert result.summary["etc_adj"] < result.summary["etc"]
    assert result.summary["relative_yield"] < 1


@pytest.mark.parametrize("changes", [
    {"efficiency": 0}, {"efficiency": 1.1}, {"mad": .9}, {"max_mm_day": 0},
    {"initial_depletion": -1}, {"initial_depletion": 999}, {"subsoil_depletion": 1.1},
    {"fixed_depth": -1}, {"interval": 0}, {"rain_fraction": -1}, {"strategy": "x"},
    {"strategy": "deficit", "deficit_fraction": .1}, {"kc_ini": float("nan")},
])
def test_invalid_management(model, changes):
    with pytest.raises(DataError):
        run_schedule(*model, ScheduleConfig(**changes))


def test_partial_season_withholds_yield(model):
    weather, site, crop, soil, planting = model
    result = run_schedule(weather[:5], site, crop, soil, planting)
    assert not result.summary["complete_season"]
    assert result.summary["relative_yield"] is None


def test_no_planting_data_or_gap(model):
    weather, site, crop, soil, planting = model
    with pytest.raises(DataError):
        run_schedule(weather[1:], site, crop, soil, planting)
    with pytest.raises(DataError):
        run_schedule(weather[:2] + weather[3:], site, crop, soil, planting)


def test_next_irrigation_is_strictly_future(model):
    result = run_schedule(*model, ScheduleConfig(strategy="interval", interval=3))
    as_of = model[-1]
    assert next_irrigation(result, as_of)["date"] == as_of + timedelta(days=3)
    assert next_irrigation(result, as_of + timedelta(days=9)) is None


def test_climate_adjustment_uses_stage_means_not_daily_endpoints(model, monkeypatch):
    weather, site, crop, soil, planting = model
    for index, row in enumerate(weather):
        row["wind"] = [2, 2, 2, 2, 2, 1, 2, 6, 2, 3][index]
        row["rh_min"] = [45, 45, 45, 45, 45, 30, 45, 60, 50, 60][index]
    monkeypatch.setattr("fieldwater.balance.calculate_daily_et0", lambda row, **kwargs:
                        {"et0": 5.0, "method": "pm", "flags": [], "u2": row["wind"], "rh_min": row["rh_min"]})
    result = run_schedule(weather, site, crop, soil, planting)
    expected_mid = crop.kc_mid + .04 * (3 - 2) * (crop.height / 3) ** .3
    assert [row["kc"] for row in result.daily[5:8]] == pytest.approx([expected_mid] * 3)
    assert result.summary["kc_end_adjusted"] == crop.kc_end


def test_alfalfa_cutting_withholds_seasonal_yield(model):
    weather, site, _, soil, planting = model
    crop = replace(get_crop("alfalfa"), stages=(2, 3, 3, 2))
    result = run_schedule(weather, site, crop, soil, planting)
    assert result.summary["complete_season"]
    assert result.summary["relative_yield"] is None
    assert "cutting-specific" in result.summary["yield_note"]


def test_rice_root_zone_approximation_is_flagged(model):
    weather, site, _, soil, planting = model
    crop = replace(get_crop("rice"), stages=(2, 3, 3, 2))
    result = run_schedule(weather, site, crop, soil, planting)
    assert all("rice_root_zone_only_no_ponding_model" in row["flags"] for row in result.daily)


@pytest.mark.parametrize("etc,actual,ky,expected", [(100, 80, 1.25, .75), (100, 100, 1.25, 1), (100, 0, 1.25, 0), (100, 80, None, None), (0, 0, 1, None)])
def test_yield(etc, actual, ky, expected):
    value = relative_yield(etc, actual, ky)
    assert value is None if expected is None else value == pytest.approx(expected)
