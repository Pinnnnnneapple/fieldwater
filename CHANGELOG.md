# Changelog

## 0.1.0 — 2026-11-07

- Daily and hourly FAO-56 Penman-Monteith equations and supporting functions.
- Temperature-only Hargreaves ET0 and flagged missing-data estimates.
- Crop and soil reference tables, regional growth stages, custom crop JSON.
- Daily irrigation policies, root growth, stress, efficiency, and capacity limits.
- CSV/JSON outputs, forecast advice, and self-contained HTML season reports.
- Deterministic demonstration weather and published-example regression tests.

This first release supports planning and education. Calibrate inputs and
management assumptions locally before field use.

### Platform support and fixes before release

- Require Python 3.10+; test on 3.10–3.14 on Linux, Windows, and macOS.
- Fix Windows example byte comparisons with LF checkouts and consistent UTF-8,
  LF output for CSV, JSON, and HTML files.
