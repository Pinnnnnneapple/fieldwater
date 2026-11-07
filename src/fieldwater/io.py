"""CSV weather, station metadata, and portable CSV/JSON outputs.

Canonical weather units: Celsius, m/s, MJ m-2 day-1, mm, relative humidity
percent, and ISO dates. Missing meteorological observations remain None;
missing rainfall is explicitly flagged and assumed zero.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .errors import DataError, InputError

PathLike = Union[str, Path]

_ALIASES = {
    "date": ("date", "day", "time", "datetime"),
    "tmax": ("tmax", "tempmax", "maximumtemperature", "temperature2mmax", "maxtemp"),
    "tmin": ("tmin", "tempmin", "minimumtemperature", "temperature2mmin", "mintemp"),
    "tmean": ("tmean", "temp", "temperature", "meantemperature", "temperature2mmean"),
    "rh_max": ("rhmax", "maxrh", "relativehumiditymax", "relativehumidity2mmax"),
    "rh_min": ("rhmin", "minrh", "relativehumiditymin", "relativehumidity2mmin"),
    "rh_mean": ("rhmean", "rh", "humidity", "relativehumidity", "relativehumidity2mmean"),
    "tdew": ("tdew", "dewpoint", "dewpoint2m", "dewpointtemperature"),
    "wind": ("wind", "windspeed", "u2", "windspeed2m", "windspeed10m"),
    "wind_height": ("windheight", "anemometerheight"),
    "sunshine_hours": ("sunshinehours", "sunshine", "sunhours", "n"),
    "rs": ("rs", "solarradiation", "radiation", "shortwaveradiationsum"),
    "rain": ("rain", "rainfall", "precipitation", "precip", "precipitationsum"),
    "runoff": ("runoff", "ro"),
    "capillary_rise": ("capillaryrise", "cr"),
    "irrigation_net": ("irrigationnet", "observedirrigation", "irrigation"),
    "is_forecast": ("isforecast", "forecast"),
}
_MISSING = {"", "na", "n/a", "nan", "null", "none", "-999", "-9999"}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower().replace("²", "2"))


def _identify(header: str) -> Optional[str]:
    key = _normalize(header)
    for name, aliases in _ALIASES.items():
        for alias in aliases:
            if key == alias or key in {alias + suffix for suffix in
                                      ("c", "degc", "f", "degf", "pct", "percent", "ms", "mps", "kmh", "kmhr", "h", "hours", "mm", "in", "m", "mj", "mjm2day", "mjm2d", "wm2")}:
                return name
    return None


def _number(value: str, label: str) -> Optional[float]:
    if value.strip().lower() in _MISSING:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise DataError(f"{label}: expected a number, got {value!r}") from exc
    if not math.isfinite(result):
        raise DataError(f"{label}: values must be finite")
    return result


def load_weather(path: PathLike, *, temperature_unit: str = "auto",
                 wind_unit: str = "auto", radiation_unit: str = "auto",
                 rain_unit: str = "auto") -> List[Dict[str, Any]]:
    """Load consecutive daily weather from CSV; infer common column/unit names.

    Bare headings use canonical units. W/m² is a 24-hour mean (multiply by
    0.0864), km/h is divided by 3.6. Fahrenheit and inches are also accepted.
    Duplicate dates, gaps, ambiguous duplicate aliases, and invalid ranges fail.
    """
    choices = ((temperature_unit, {"auto", "c", "f"}),
               (wind_unit, {"auto", "m/s", "km/h"}),
               (radiation_unit, {"auto", "mj", "w/m2"}),
               (rain_unit, {"auto", "mm", "in"}))
    if any(value not in allowed for value, allowed in choices):
        raise DataError("unsupported weather unit option")
    records: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise DataError("weather CSV is empty")
        columns: Dict[str, str] = {}
        for header in reader.fieldnames:
            name = _identify(header)
            if name:
                if name in columns:
                    raise DataError(f"multiple CSV columns map to {name}")
                columns[name] = header
        if "date" not in columns:
            raise DataError("weather CSV needs a date column")
        if not {"tmax", "tmin"}.issubset(columns):
            raise DataError("weather CSV needs tmax and tmin for daily ET0")
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise DataError(f"line {line}: inconsistent number of columns")
            try:
                day = date.fromisoformat(row[columns["date"]].strip())
            except ValueError as exc:
                raise DataError(f"line {line}: date must be YYYY-MM-DD") from exc
            if records and day != records[-1]["date"] + timedelta(days=1):
                raise DataError(f"line {line}: dates must be consecutive and ascending")
            record: Dict[str, Any] = {"date": day, "input_flags": []}
            for name, header in columns.items():
                if name == "date":
                    continue
                cell = row[header].strip()
                if name == "is_forecast":
                    if cell.lower() not in {"0", "1", "false", "true", "", "yes", "no"}:
                        raise DataError(f"line {line}: invalid is_forecast boolean")
                    record[name] = cell.lower() in {"1", "true", "yes"}
                    continue
                value = _number(cell, f"line {line}, {name}")
                if value is None:
                    record[name] = None
                    continue
                unit_header = _normalize(header)
                if name in {"tmax", "tmin", "tmean", "tdew"}:
                    fahrenheit = temperature_unit == "f" or (temperature_unit == "auto" and unit_header.endswith("f"))
                    if fahrenheit:
                        value = (value - 32) * 5 / 9
                elif name == "wind":
                    if wind_unit == "km/h" or (wind_unit == "auto" and ("kmh" in unit_header)):
                        value /= 3.6
                    if "10m" in unit_header and "wind_height" not in columns:
                        record["wind_height"] = 10.0
                elif name == "rs":
                    if radiation_unit == "w/m2" or (radiation_unit == "auto" and "wm2" in unit_header):
                        value *= 0.0864
                elif name in {"rain", "runoff", "capillary_rise", "irrigation_net"}:
                    inch_headers = {alias + "in" for alias in _ALIASES[name]}
                    if rain_unit == "in" or (rain_unit == "auto" and unit_header in inch_headers):
                        value *= 25.4
                record[name] = value
            if record.get("tmax") is None or record.get("tmin") is None:
                raise DataError(f"line {line}: tmax/tmin are required")
            if record["tmax"] < record["tmin"]:
                raise DataError(f"line {line}: tmax must be >= tmin")
            for name in ("tmax", "tmin", "tmean", "tdew"):
                if record.get(name) is not None and not -90 <= record[name] <= 65:
                    raise DataError(f"line {line}: {name} outside supported -90..65 Celsius")
            for name in ("rh_max", "rh_min", "rh_mean"):
                if record.get(name) is not None and not 0 <= record[name] <= 100:
                    raise DataError(f"line {line}: {name} must be 0..100 percent")
            if record.get("rh_min") is not None and record.get("rh_max") is not None and record["rh_min"] > record["rh_max"]:
                raise DataError(f"line {line}: rh_min exceeds rh_max")
            for name in ("wind", "rs", "rain", "sunshine_hours", "runoff", "capillary_rise", "irrigation_net"):
                if record.get(name) is not None and record[name] < 0:
                    raise DataError(f"line {line}: {name} cannot be negative")
            if record.get("sunshine_hours") is not None and record["sunshine_hours"] > 24:
                raise DataError(f"line {line}: sunshine_hours exceeds 24")
            if record.get("rain") is None:
                record["rain"] = 0.0
                record["input_flags"].append("rain_missing_assumed_zero")
            records.append(record)
    if not records:
        raise DataError("weather CSV has no observations")
    return records


def load_site(path: Optional[PathLike] = None, **overrides: Any) -> Dict[str, Any]:
    """Load site JSON and apply non-None CLI overrides; latitude is in degrees.

    Keys: lat, lon (optional), altitude (default 0 m), wind_height (default 2 m),
    coastal (false), ko (dew-point correction in Celsius, default 0).
    """
    site: Dict[str, Any] = {"altitude": 0.0, "wind_height": 2.0, "coastal": False, "ko": 0.0}
    if path is not None:
        try:
            with open(path, encoding="utf-8") as handle:
                content = json.load(handle)
        except json.JSONDecodeError as exc:
            raise InputError(f"invalid site JSON: {exc.msg}") from exc
        if not isinstance(content, dict):
            raise InputError("site JSON must be an object")
        content = dict(content)
        for alias, canonical in (("latitude", "lat"), ("longitude", "lon"), ("alt", "altitude")):
            if alias in content:
                content[canonical] = content.pop(alias)
        site.update(content)
    site.update({key: value for key, value in overrides.items() if value is not None})
    if site.get("lat") is None:
        raise InputError("provide --lat or a site JSON containing lat")
    for key in ("lat", "lon", "altitude", "wind_height", "ko"):
        if key not in site:
            continue
        try:
            if isinstance(site[key], bool):
                raise ValueError
            site[key] = float(site[key])
        except (ValueError, TypeError) as exc:
            raise DataError(f"site {key} must be numeric") from exc
        if not math.isfinite(site[key]):
            raise DataError(f"site {key} must be finite")
    if not -90 <= site["lat"] <= 90 or not -180 <= site.get("lon", 0) <= 180:
        raise DataError("site latitude/longitude out of range")
    if not -500 <= site["altitude"] <= 9000:
        raise DataError("site altitude outside -500..9000 m")
    if site["wind_height"] <= 0.1 or site["ko"] < 0:
        raise DataError("wind_height must exceed 0.1 m and ko must be nonnegative")
    if not isinstance(site["coastal"], bool):
        raise DataError("site coastal must be a JSON boolean")
    return site


def _serial(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_serial(item) for item in value]
    if isinstance(value, dict):
        return {key: _serial(item) for key, item in value.items()}
    return value


def write_csv(path: PathLike, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a daily table, retaining full float precision for balance audits."""
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            serialized = {key: _serial(value) for key, value in row.items()}
            for key, value in serialized.items():
                if isinstance(value, list):
                    serialized[key] = ";".join(str(item) for item in value)
            writer.writerow(serialized)


def write_json(path: PathLike, data: Any) -> None:
    """Write strict UTF-8 JSON with ISO dates and no non-finite numbers."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(_serial(data), handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
