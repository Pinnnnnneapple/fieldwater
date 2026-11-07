"""Direct-main command checks, real example integration, and exit codes."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fieldwater.cli import main

ROOT = Path(__file__).resolve().parents[1]
WEATHER = str(ROOT / "examples/weather_demo.csv")
SITE = str(ROOT / "examples/site_demo.json")
BASE = ["--site", SITE, "--crop", "maize", "--planting", "2025-05-01", "--soil", "loam"]


def test_schedule_all_outputs(tmp_path, capsys):
    html, daily, summary = [tmp_path / name for name in ("report.html", "daily.csv", "summary.json")]
    assert main(["schedule", WEATHER, *BASE, "--html", str(html), "--csv", str(daily), "--json", str(summary)]) == 0
    output = capsys.readouterr().out
    assert "Irrigation calendar" in output and "Season summary" in output
    assert "Water balance residual" in output
    data = json.loads(summary.read_text())
    assert data["days"] == 150 and abs(data["balance_error"]) < 1e-9
    assert data["irrigation_events"] > 0
    with daily.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 150
    assert max(abs(float(row["balance_error"])) for row in rows) < 1e-9
    assert "<svg" in html.read_text()


@pytest.mark.parametrize("command,label", [("crops", "maize"), ("soils", "loam")])
def test_reference_tables(command, label, capsys):
    assert main([command]) == 0
    assert label in capsys.readouterr().out


@pytest.mark.parametrize("method,flag", [("pm", "humidity_estimated_tmin_ko"), ("hargreaves", "hargreaves_temperature_method")])
def test_temperature_only_et0(tmp_path, capsys, method, flag):
    output = tmp_path / "et0.csv"
    assert main(["et0", str(ROOT / "examples/weather_temperature_only.csv"), "--site", SITE,
                 "--method", method, "-o", str(output)]) == 0
    assert flag in capsys.readouterr().out
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 153
    assert all(float(row["et0"]) >= 0 and flag in row["flags"] for row in rows)


def test_et0_stdout(capsys):
    assert main(["et0", WEATHER, "--lat", "40", "--alt", "300"]) == 0
    rows = list(csv.DictReader(capsys.readouterr().out.splitlines()))
    assert len(rows) == 153 and "radiation_from_sunshine" in rows[0]["flags"]


@pytest.mark.parametrize("args", [[], ["unknown"], ["schedule", WEATHER], ["et0", WEATHER, "--method", "unknown"]])
def test_usage_error(args, capsys):
    assert main(args) == 2
    assert "usage:" in capsys.readouterr().err


def test_missing_file_and_site(capsys):
    assert main(["et0", "does-not-exist.csv", "--lat", "40"]) == 2
    assert "fieldwater:" in capsys.readouterr().err
    assert main(["et0", WEATHER]) == 2


def test_bad_weather_and_management(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("date,tmax,tmin\n2025-05-01,10,20\n")
    assert main(["et0", str(path), "--lat", "40"]) == 3
    assert "data error:" in capsys.readouterr().err
    assert main(["schedule", WEATHER, *BASE, "--efficiency", "0"]) == 3
    assert main(["schedule", WEATHER, *BASE, "--crop-file", "x"]) == 2


def test_unknown_crop(capsys):
    args = ["schedule", WEATHER, "--site", SITE, "--crop", "not-a-crop", "--planting", "2025-05-01", "--soil", "loam"]
    assert main(args) == 3
    assert "Unknown crop" in capsys.readouterr().err


def test_next_explicit_date(capsys):
    assert main(["next", WEATHER, *BASE, "--as-of", "2025-07-01"]) == 0
    output = capsys.readouterr().out
    assert "Next irrigation: 2025-07-05" in output
    assert "net 117.28 mm; gross 156.37 mm" in output


def test_next_no_event(capsys):
    assert main(["next", WEATHER, *BASE, "--as-of", "2025-09-30"]) == 0
    assert "No irrigation within" in capsys.readouterr().out


def test_next_forecast_column(tmp_path, capsys):
    path = tmp_path / "forecast.csv"
    with open(WEATHER) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames + ["is_forecast"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "is_forecast": row["date"] > "2025-07-01"})
    assert main(["next", str(path), *BASE]) == 0
    output = capsys.readouterr().out
    assert "after 2025-07-01" in output and "Next irrigation:" in output


def test_custom_crop_cli(tmp_path, capsys):
    crop = tmp_path / "crop.json"
    crop.write_text(json.dumps({"key": "test", "name": "Local maize", "kc_ini": .3, "kc_mid": 1.2,
                               "kc_end": .35, "height": 2, "zr_min": .3, "zr_max": 1.2, "p": .55,
                               "stages": [30, 40, 50, 30], "ky": 1.25}))
    assert main(["schedule", WEATHER, "--site", SITE, "--crop-file", str(crop), "--planting", "2025-05-01", "--soil", "loam"]) == 0
    assert "Local maize" in capsys.readouterr().out


def test_module_entrypoint():
    completed = subprocess.run([sys.executable, "-m", "fieldwater", "--version"],
                               capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert completed.stdout.strip() == "fieldwater 0.1.0"


def test_deterministic_examples(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("generate_weather", ROOT / "examples/generate_weather.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.generate(tmp_path)
    for filename in ("weather_demo.csv", "weather_temperature_only.csv"):
        assert (tmp_path / filename).read_bytes() == (ROOT / "examples" / filename).read_bytes()
