"""Generate reproducible, synthetic weather at 40 N, 300 m (not observations).

Run from any directory: python3 examples/generate_weather.py
Rainfall is intermittent and summer temperatures follow a smooth seasonal cycle.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path


def generate(directory: Path) -> None:
    """Write the May-September 2025 full and temperature-only CSVs, seed 56."""
    rng = random.Random(56)
    rows = []
    start = date(2025, 5, 1)
    for index in range(153):
        day = start + timedelta(days=index)
        seasonal = math.sin(math.pi * (index + 20) / 193)
        tmean = 13 + 12 * seasonal + rng.gauss(0, 1.6)
        spread = rng.uniform(10, 16)
        wet = rng.random() < 0.19
        rain = round(min(45, rng.expovariate(1 / 12)), 1) if wet else 0
        rows.append({
            "date": day.isoformat(), "tmax": round(tmean + spread / 2, 1),
            "tmin": round(tmean - spread / 2, 1),
            "rh_max": round(min(99, rng.uniform(72, 92) + (6 if wet else 0)), 1),
            "rh_min": round(rng.uniform(28, 47) + (12 if wet else 0), 1),
            "wind": round(rng.uniform(1.2, 3.4), 2),
            "sunshine_hours": round(rng.uniform(3, 6) if wet else rng.uniform(8, 11.5), 1),
            "rain": rain,
        })
    directory.mkdir(parents=True, exist_ok=True)
    for filename, fields in (("weather_demo.csv", list(rows[0])),
                             ("weather_temperature_only.csv", ["date", "tmax", "tmin", "rain"])):
        with (directory / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent)
