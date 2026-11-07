# Contributing

Use Python 3.10 or newer. Runtime code uses only the standard library.

```bash
git clone https://github.com/Pinnnnnneapple/fieldwater.git
cd fieldwater
python -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m pytest -q
```

For a scientific change, cite the original equation or table, state units,
and add an independent numerical regression or conservation check. Explain
whether a parameter is a published value, a representative selection from a
range, or a local assumption. Never relabel synthetic data as observations.
Keep public functions typed and documented, and preserve Python 3.10 support.

For bug reports, include the command, version, input column headings, station
units, expected result, and a small shareable reproducer. Remove personal or
restricted weather data. The issue templates cover the required information.

Regenerate examples after changes that affect results:

```bash
python3 examples/generate_weather.py
PYTHONPATH=src python3 -m fieldwater schedule examples/weather_demo.csv \
  --site examples/site_demo.json --crop maize --planting 2025-05-01 --soil loam \
  --html examples/output/maize_schedule.html \
  --csv examples/output/maize_schedule.csv --json examples/output/maize_schedule.json
```

Report security issues privately to the repository maintainers through GitHub
when private reporting is available. Treat each other with respect and discuss
scientific assumptions using evidence and reproducible examples.
