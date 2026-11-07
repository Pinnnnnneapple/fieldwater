"""Command-line irrigation calendar, reference ET, and reference tables."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .balance import Schedule, ScheduleConfig, next_irrigation, run_schedule
from .crops import CROPS, get_crop, load_crop
from .errors import InputError
from .et0 import calculate_daily_et0
from .io import load_site, load_weather, write_csv, write_json
from .report import write_report
from .soils import SOILS, get_soil


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def _weather_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("weather", help="daily CSV, dates must be consecutive")
    parser.add_argument("--site", help="JSON station metadata")
    parser.add_argument("--lat", type=float, help="latitude, degrees north positive")
    parser.add_argument("--lon", type=float, help="longitude, degrees east positive")
    parser.add_argument("--alt", "--altitude", dest="altitude", type=float, help="station altitude, m")
    parser.add_argument("--wind-height", type=float, help="anemometer height, m (default 2)")
    parser.add_argument("--coastal", action="store_true", default=None, help="use kRs=0.19 instead of 0.16")
    parser.add_argument("--ko", type=float, help="Tdew=Tmin-Ko correction, Celsius")
    parser.add_argument("--method", choices=("pm", "hargreaves"), default="pm")
    parser.add_argument("--temperature-unit", choices=("auto", "c", "f"), default="auto")
    parser.add_argument("--wind-unit", choices=("auto", "m/s", "km/h"), default="auto")
    parser.add_argument("--radiation-unit", choices=("auto", "mj", "w/m2"), default="auto")
    parser.add_argument("--rain-unit", choices=("auto", "mm", "in"), default="auto")


def _schedule_arguments(parser: argparse.ArgumentParser) -> None:
    _weather_arguments(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--crop", help="built-in crop key; see fieldwater crops")
    group.add_argument("--crop-file", help="custom crop JSON")
    parser.add_argument("--planting", required=True, type=_date)
    parser.add_argument("--soil", required=True, help="texture key; see fieldwater soils")
    parser.add_argument("--mad", type=float, help="management trigger fraction 0.1..0.8")
    parser.add_argument("--efficiency", type=float, default=0.75, help="net/gross ratio (default 0.75)")
    parser.add_argument("--strategy", choices=("refill", "fixed", "interval", "deficit", "none", "fixed-depth", "fixed-interval"), default="refill")
    parser.add_argument("--fixed-depth", type=float, default=25.0, help="net application depth for fixed/interval, mm")
    parser.add_argument("--interval", type=int, default=7, help="interval days; first application is planting day")
    parser.add_argument("--deficit-fraction", type=float, default=0.9, help="target water content / field capacity (default 0.9)")
    parser.add_argument("--max-mm-day", type=float, help="system capacity in GROSS mm/day")
    parser.add_argument("--initial-depletion", type=float, default=0.0, help="initial root-zone depletion, mm")
    parser.add_argument("--subsoil-depletion", type=float, default=0.0, help="depletion fraction in newly rooted soil, 0..1")
    parser.add_argument("--rain-method", choices=("fixed", "scs"), default="fixed")
    parser.add_argument("--rain-fraction", type=float, default=0.8)
    parser.add_argument("--kc-ini", type=float, help="locally calibrated initial Kc")
    parser.add_argument("--no-climate-adjustment", action="store_true", help="use tabulated Kc mid/end")
    parser.add_argument("--html", help="self-contained season report path")
    parser.add_argument("--csv", help="daily balance CSV path")
    parser.add_argument("--json", help="summary and irrigation calendar JSON path")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without inspecting process arguments."""
    parser = argparse.ArgumentParser(prog="fieldwater", description="FAO-56 evapotranspiration and irrigation scheduling")
    parser.add_argument("--version", action="version", version=f"fieldwater {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    et = sub.add_parser("et0", help="daily reference evapotranspiration")
    _weather_arguments(et)
    et.add_argument("-o", "--output", help="output CSV; otherwise write daily CSV to stdout")
    sub.add_parser("crops", help="list built-in crop coefficients and growth stages")
    sub.add_parser("soils", help="list representative soil water characteristics")
    schedule = sub.add_parser("schedule", help="daily balance, irrigation calendar, and season summary")
    _schedule_arguments(schedule)
    forecast = sub.add_parser("next", help="next irrigation within supplied forecast horizon")
    _schedule_arguments(forecast)
    forecast.add_argument("--as-of", type=_date, help="last historical date; otherwise before first forecast=true row, or today")
    return parser


def _load(args: argparse.Namespace) -> Any:
    site = load_site(args.site, lat=args.lat, lon=args.lon, altitude=args.altitude,
                     wind_height=args.wind_height, coastal=args.coastal, ko=args.ko)
    weather = load_weather(args.weather, temperature_unit=args.temperature_unit,
                           wind_unit=args.wind_unit, radiation_unit=args.radiation_unit,
                           rain_unit=args.rain_unit)
    return weather, site


def print_calendar(schedule: Schedule) -> None:
    """Print actual simulated event depths and an audit-oriented season summary."""
    print("Irrigation calendar (simulated; verify locally)")
    print("Date          Net (mm)  Gross (mm)")
    for row in schedule.calendar:
        print(f"{row['date'].isoformat()}  {row['irrigation_net']:9.2f}  {row['irrigation_gross']:10.2f}")
    if not schedule.calendar:
        print("No irrigation within the supplied weather horizon.")
    summary = schedule.summary
    print(f"\nSeason summary: {summary['crop']} / {summary['soil']} ({summary['days']} days)")
    print(f"ETc: {summary['etc']:.2f} mm; ETc adjusted: {summary['etc_adj']:.2f} mm")
    print(f"Rain: {summary['rain']:.2f} mm; effective rain: {summary['effective_rain']:.2f} mm")
    print(f"Irrigation net/gross: {summary['irrigation_net']:.2f} / {summary['irrigation_gross']:.2f} mm")
    print(f"Deep percolation: {summary['deep_percolation']:.2f} mm; stress days: {summary['stress_days']}")
    estimate = summary["relative_yield"]
    print("Relative yield (Ky approximation): " + (f"{estimate:.3f}" if estimate is not None else "unavailable"))
    print(f"Water balance residual: {summary['balance_error']:.3e} mm")
    if not summary["complete_season"]:
        print("Partial season: weather ends before the selected growth stages finish.")
    if any("rice_root_zone_only_no_ponding_model" in row["flags"] for row in schedule.daily):
        print("Rice: root-zone approximation only; operational paddy scheduling requires a ponded-water balance.")


def _execute(args: argparse.Namespace) -> int:
    if args.command == "crops":
        print("Crop               Kc ini/mid/end     Height(m)  Zr min/max(m)  p     Stages(days)     Ky")
        for key, crop in CROPS.items():
            ky = "n/a" if crop.ky is None else f"{crop.ky:.2f}"
            print(f"{key:18} {crop.kc_ini:.2f}/{crop.kc_mid:.2f}/{crop.kc_end:.2f}       {crop.height:5.2f}      {crop.zr_min:.2f}/{crop.zr_max:.2f}    {crop.p:.2f}  {'/'.join(str(n) for n in crop.stages):16} {ky}")
        print("FAO-56 Tables 11/12/22 starting values; verify crop, cultivar, climate, and table footnotes.")
        print("Ky unavailable where no supported seasonal value is provided; see docs/reference-tables.md.")
        return 0
    if args.command == "soils":
        print("Texture             theta FC  theta WP  Available water (mm/m)")
        for key, soil in SOILS.items():
            print(f"{key:20} {soil.theta_fc:8.3f}  {soil.theta_wp:8.3f}  {1000 * (soil.theta_fc - soil.theta_wp):9.1f}")
        print("Representative texture values within FAO-56 Table 19 ranges; measure locally.")
        return 0
    weather, site = _load(args)
    if args.command == "et0":
        rows = []
        for row in weather:
            result = calculate_daily_et0(row, latitude=site["lat"], altitude=site["altitude"],
                                         wind_height=row.get("wind_height") or site["wind_height"],
                                         method=args.method, coastal=site["coastal"], ko=site["ko"])
            rows.append({"date": row["date"], **result,
                         "flags": list(row["input_flags"]) + list(result["flags"])})
        if args.output:
            write_csv(args.output, rows)
            print(f"Wrote {len(rows)} daily ET0 estimates to {args.output} (method: {args.method}).")
            flags = sorted({flag for row in rows for flag in row["flags"]})
            print("Flags: " + (", ".join(flags) if flags else "none"))
        else:
            keys = list(dict.fromkeys(key for row in rows for key in row))
            writer = csv.DictWriter(sys.stdout, fieldnames=keys, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "flags": ";".join(row["flags"])})
        return 0
    crop = load_crop(args.crop_file) if args.crop_file else get_crop(args.crop)
    config = ScheduleConfig(
        strategy={"fixed-depth": "fixed", "fixed-interval": "interval"}.get(args.strategy, args.strategy),
        efficiency=args.efficiency, mad=args.mad, fixed_depth=args.fixed_depth, interval=args.interval,
        deficit_fraction=args.deficit_fraction, max_mm_day=args.max_mm_day,
        initial_depletion=args.initial_depletion, subsoil_depletion=args.subsoil_depletion,
        rain_method=args.rain_method, rain_fraction=args.rain_fraction, method=args.method,
        kc_ini=args.kc_ini, climate_adjustment=not args.no_climate_adjustment)
    result = run_schedule(weather, site, crop, get_soil(args.soil), args.planting, config)
    if args.html:
        write_report(args.html, result.daily, result.summary, title=f"fieldwater: {crop.name}")
    if args.csv:
        write_csv(args.csv, result.daily)
    if args.json:
        write_json(args.json, {**result.summary, "site": site, "management": vars(config),
                               "irrigation_calendar": result.calendar})
    if args.command == "next":
        forecast_dates = [row["date"] for row in weather if row.get("is_forecast")]
        as_of = args.as_of or (min(forecast_dates) - timedelta(days=1) if forecast_dates else date.today())
        event = next_irrigation(result, as_of)
        print(f"Forecast advice after {as_of.isoformat()} (weather through {weather[-1]['date'].isoformat()})")
        if event is None:
            print("No irrigation within the supplied forecast/crop horizon.")
        else:
            print(f"Next irrigation: {event['date'].isoformat()}; net {event['irrigation_net']:.2f} mm; gross {event['irrigation_gross']:.2f} mm")
        return 0
    print_calendar(result)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; return 0 success, 2 usage/IO failure, or 3 invalid data."""
    try:
        args = build_parser().parse_args(argv)
        return _execute(args)
    except SystemExit as exc:
        return int(exc.code)
    except (OSError, InputError, UnicodeError, csv.Error) as exc:
        print(f"fieldwater: {exc}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError) as exc:
        print(f"fieldwater: data error: {exc}", file=sys.stderr)
        return 3
