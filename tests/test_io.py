"""Weather unit, validation, metadata, and serialization regressions."""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from fieldwater.errors import DataError, InputError
from fieldwater.io import load_site, load_weather, write_csv, write_json


def weather_file(tmp_path, text):
    path = tmp_path / "weather.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_aliases_and_units(tmp_path):
    path = weather_file(tmp_path, "date,tmax_f,tmin_f,rh_max,rh_min,wind_speed_10m_kmh,rs_wm2,rain_in\n2025-05-01,86,50,80,40,36,200,1\n")
    row = load_weather(path)[0]
    assert row["tmax"] == 30
    assert row["tmin"] == 10
    assert row["wind"] == 10
    assert row["wind_height"] == 10
    assert row["rs"] == pytest.approx(17.28)
    assert row["rain"] == 25.4


def test_missing_rain_flag(tmp_path):
    path = weather_file(tmp_path, "date,tmax,tmin\n2025-05-01,20,10\n")
    row = load_weather(path)[0]
    assert row["rain"] == 0
    assert row["input_flags"] == ["rain_missing_assumed_zero"]


def test_bare_rain_is_millimetres_not_inches(tmp_path):
    path = weather_file(tmp_path, "date,tmax,tmin,rain\n2025-05-01,20,10,12\n")
    assert load_weather(path)[0]["rain"] == 12


@pytest.mark.parametrize("heading,value", [
    ("tmax", "nanx"), ("tmax", "inf"), ("tmax", "NaN"),
    ("tmax", "-999"), ("tmax", "-100"), ("tmin", "99"),
    ("rh_min", "-1"), ("rh_max", "101"), ("wind", "-1"),
    ("rain", "-1"), ("rs", "-1"), ("sunshine_hours", "25"),
])
def test_invalid_weather(tmp_path, heading, value):
    row = {"date": "2025-05-01", "tmax": "25", "tmin": "10", heading: value}
    text = ",".join(row) + "\n" + ",".join(row.values()) + "\n"
    with pytest.raises(DataError):
        load_weather(weather_file(tmp_path, text))


@pytest.mark.parametrize("text", [
    "", "date,tmax,tmin\n", "tmax,tmin\n20,10\n", "date,tmean\n2025-01-01,20\n",
    "date,tmax,tmin\n01/02/2025,20,10\n", "date,tmax,tmin\n2025-01-01,10,20\n",
    "date,tmax,tmin\n2025-01-01,20,10\n2025-01-01,20,10\n",
    "date,tmax,tmin\n2025-01-01,20,10\n2025-01-03,20,10\n",
    "date,tmax,tmin,tempmax\n2025-01-01,20,10,20\n",
    "date,tmax,tmin\n2025-01-01,20\n", "date,tmax,tmin\n2025-01-01,20,10,99\n",
    "date,tmax,tmin,rh_max,rh_min\n2025-01-01,20,10,30,80\n",
])
def test_bad_csv(tmp_path, text):
    with pytest.raises(DataError):
        load_weather(weather_file(tmp_path, text))


def test_explicit_unit_override(tmp_path):
    path = weather_file(tmp_path, "date,tmax,tmin,wind,rs,rain\n2025-01-01,86,50,36,200,1\n")
    row = load_weather(path, temperature_unit="f", wind_unit="km/h", radiation_unit="w/m2", rain_unit="in")[0]
    assert (row["tmax"], row["wind"], row["rain"]) == (30, 10, 25.4)
    assert row["rs"] == pytest.approx(17.28)


def test_forecast_bool_and_missing(tmp_path):
    path = weather_file(tmp_path, "date,tmax,tmin,wind,is_forecast\n2025-01-01,20,10,NA,TRUE\n")
    row = load_weather(path)[0]
    assert row["wind"] is None and row["is_forecast"] is True


def test_site_override(tmp_path):
    path = tmp_path / "site.json"
    path.write_text(json.dumps({"latitude": 40, "alt": 300, "wind_height": 10}))
    site = load_site(path, altitude=100, wind_height=None)
    assert (site["lat"], site["altitude"], site["wind_height"]) == (40, 100, 10)


@pytest.mark.parametrize("overrides", [
    {"lat": 100}, {"lat": float("nan")}, {"lat": 40, "lon": 200},
    {"lat": 40, "wind_height": 0}, {"lat": 40, "altitude": 10000},
    {"lat": 40, "ko": -1}, {"lat": True}, {"lat": 40, "coastal": "false"},
])
def test_site_validation(overrides):
    with pytest.raises(DataError):
        load_site(**overrides)


def test_missing_site():
    with pytest.raises(InputError):
        load_site()


def test_bad_site_json(tmp_path):
    path = tmp_path / "site.json"
    path.write_text("not json")
    with pytest.raises(InputError):
        load_site(path)


def test_outputs_preserve_precision(tmp_path):
    rows = [{"date": date(2025, 1, 1), "value": 1 / 3, "flags": ["estimated", "synthetic"]}]
    write_csv(tmp_path / "out.csv", rows)
    with (tmp_path / "out.csv").open() as handle:
        row = next(csv.DictReader(handle))
    assert float(row["value"]) == 1 / 3
    assert row["flags"] == "estimated;synthetic"
    write_json(tmp_path / "out.json", rows)
    assert json.loads((tmp_path / "out.json").read_text())[0]["date"] == "2025-01-01"


def test_nonfinite_json_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_json(tmp_path / "out.json", {"value": float("nan")})
