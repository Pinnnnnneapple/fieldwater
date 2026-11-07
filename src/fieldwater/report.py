"""Dependency-free, self-contained HTML reports for daily water balances."""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union


_DEFAULT_TITLE = "fieldwater season report"
_FIELDS = ("et0", "etc", "etc_adj", "rain", "effective_rain", "dr", "raw",
           "taw", "kc", "irrigation_net", "irrigation_gross", "ks")
_CSS = """
:root{color-scheme:light dark;--bg:#f3f6f5;--panel:#fff;--ink:#18352e;
--muted:#546b64;--grid:#d8e2de;--a:#087a63;--b:#be5824;--c:#7354b3;--rain:#297fb4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1120px;margin:auto;padding:36px 24px 64px}header{margin-bottom:28px}
h1{font-size:clamp(1.8rem,4vw,3rem);line-height:1.15;overflow-wrap:anywhere}
h2{font-size:1.25rem;margin:0 0 8px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;
font-size:.75rem;font-weight:700;color:var(--a)}.muted,caption{color:var(--muted)}
section{background:var(--panel);border:1px solid var(--grid);border-radius:16px;
padding:24px;margin:20px 0}p{margin:8px 0 16px}svg{display:block;width:100%;height:auto;
min-width:600px}text{fill:var(--muted);font:13px system-ui,sans-serif}
.grid{stroke:var(--grid);stroke-width:1}.curve{fill:none;stroke-width:2.5;
stroke-linejoin:round;stroke-linecap:round}.a{stroke:var(--a)}.b{stroke:var(--b)}
.c{stroke:var(--c);stroke-dasharray:7 4}.rain{fill:var(--rain);opacity:.48}
.event{fill:var(--panel);stroke:var(--c);stroke-width:2}.legend{display:flex;gap:10px 24px;
flex-wrap:wrap;list-style:none;padding:0;margin:12px 0;font-size:.9rem}
.legend i{display:inline-block;width:24px;margin-right:7px;vertical-align:middle;
border-top:3px solid var(--a)}.legend .b{border-color:var(--b)}
.legend .c{border-color:var(--c);border-top-style:dashed}
.legend .rain{height:10px;background:var(--rain);border:0}
.legend .event{width:10px;height:10px;border:2px solid var(--c);transform:rotate(45deg)}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
caption{text-align:left;padding-bottom:12px}th,td{padding:10px 12px;border-bottom:1px solid var(--grid);
text-align:left;overflow-wrap:anywhere}th{font-weight:600}tbody tr:last-child>*{border-bottom:0}
.empty{padding:28px 0;color:var(--muted)}footer{color:var(--muted);font-size:.85rem}
@media(prefers-color-scheme:dark){:root{--bg:#101d19;--panel:#172923;--ink:#e3eee9;
--muted:#aec4b9;--grid:#345044;--a:#66d9b2;--b:#ffb078;--c:#c5a7ff;--rain:#74bdf0}}
@media(max-width:640px){main{padding:24px 12px}section{padding:16px}th,td{padding:8px}}
@media print{body{background:white}section{break-inside:avoid}.scroll{overflow:visible}
svg{min-width:0}main{padding:0}}
"""


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _number(value: Any, field: str, index: int) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Daily row {}: {} must be a finite number".format(index, field)) from None
    if not math.isfinite(number):
        raise ValueError("Daily row {}: {} must be a finite number".format(index, field))
    return number


def _display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return format(value, ".4g") if math.isfinite(value) else "—"
    return str(value)


def _metric_label(key: Any) -> str:
    """Attach units to known model metrics without trusting arbitrary text."""
    depths = {"et0", "etc", "etc_adj", "rain", "runoff", "effective_rain", "rain_loss",
              "capillary_rise", "root_growth_depletion", "irrigation_net", "irrigation_gross",
              "deep_percolation", "initial_depletion", "final_depletion", "balance_error"}
    text = str(key)
    if text in depths:
        return text.replace("_", " ") + " (mm)"
    if text in {"relative_yield", "ky", "efficiency", "kc_mid_adjusted", "kc_end_adjusted"}:
        return text.replace("_", " ") + " (dimensionless)"
    return text.replace("_", " ")


def _chart(chart_id: str, heading: str, description: str, dates: Sequence[str],
           rows: Sequence[Mapping[str, Optional[float]]],
           series: Sequence[tuple], unit: str, rain: bool = False,
           events: bool = False) -> str:
    legend = ['<li><i class="{}" aria-hidden="true"></i>{}</li>'.format(style, label)
              for _, label, style in series]
    if rain:
        legend.append('<li><i class="rain" aria-hidden="true"></i>Rain (mm/day)</li>')
    if events:
        legend.append('<li><i class="event" aria-hidden="true"></i>Irrigation event</li>')
    start = '<section><h2>{}</h2><p class="muted">{}</p>'.format(heading, description)
    if not rows:
        return start + '<p class="empty">No daily observations available.</p></section>'
    fields = [field for field, _, _ in series] + (["rain"] if rain else [])
    values = [row[field] for row in rows for field in fields if row[field] is not None]
    # Normalize before subtraction so even extreme finite inputs cannot overflow.
    magnitude = max([abs(v) for v in values] + [1.0])
    lower = min([v / magnitude for v in values] + [0.0])
    upper = max([v / magnitude for v in values] + [0.0])
    if lower == upper:
        upper = 1.0
    span = upper - lower

    def x(index: int) -> float:
        return 90 + (index / (len(rows) - 1) * 830 if len(rows) > 1 else 415)

    def y(value: float) -> float:
        return 250 - ((value / magnitude - lower) / span) * 200

    parts = [start, '<ul class="legend">' + "".join(legend) + '</ul>',
             '<div class="scroll" tabindex="0" role="region" aria-label="Scrollable chart">',
             '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 330" role="img" '
             'aria-labelledby="{0}-title {0}-desc">'.format(chart_id),
             '<title id="{}-title">{}</title>'.format(chart_id, heading),
             '<desc id="{}-desc">{} Dates: {} to {}. Missing values break lines. '
             'Observations are equally spaced.</desc>'.format(
                 chart_id, description, _escape(dates[0]), _escape(dates[-1])),
             '<text x="90" y="24">{}</text>'.format(unit)]
    for tick in range(5):
        normalized = lower + span * tick / 4
        position = 250 - tick * 50
        label = normalized * magnitude
        parts.append('<path class="grid" d="M90 {0} H920"/><text x="80" y="{1}" '
                     'text-anchor="end">{2}</text>'.format(position, position + 4, format(label, ".3g")))
    if rain:
        width = min(24.0, 600 / len(rows))
        for index, row in enumerate(rows):
            value = row["rain"]
            if value is not None:
                top, bottom = sorted((y(value), y(0)))
                parts.append('<rect class="rain" x="{:.2f}" y="{:.2f}" width="{:.2f}" '
                             'height="{:.2f}"><title>{}: rain {} mm/day</title></rect>'.format(
                                 x(index) - width / 2, top, width, bottom - top,
                                 _escape(dates[index]), format(value, ".4g")))
    for field, label, style in series:
        commands = []
        connected = False
        for index, row in enumerate(rows):
            value = row[field]
            if value is None:
                connected = False
                continue
            commands.append('{}{:.2f} {:.2f}'.format('L' if connected else 'M', x(index), y(value)))
            connected = True
            parts.append('<circle class="curve {}" cx="{:.2f}" cy="{:.2f}" r="2">'
                         '<title>{}: {} {}</title></circle>'.format(
                             style, x(index), y(value), _escape(dates[index]), label, format(value, ".4g")))
        parts.append('<path class="curve {}" d="{}"/>'.format(style, " ".join(commands)))
    if events:
        for index, row in enumerate(rows):
            if (row["irrigation_net"] or 0) > 0 or (row["irrigation_gross"] or 0) > 0:
                position = y(row["dr"]) if row["dr"] is not None else 250
                parts.append('<path class="event" d="M{0:.2f} {1:.2f} l5 5 -5 5 -5 -5 Z">'
                             '<title>{2}: irrigation; net {3} mm, gross {4} mm</title></path>'.format(
                                 x(index), position - 5, _escape(dates[index]),
                                 _display(row["irrigation_net"]), _display(row["irrigation_gross"])))
    for index in sorted({0, len(rows) // 2, len(rows) - 1}):
        anchor = 'middle' if len(rows) == 1 else ('start' if index == 0 else 'end' if index == len(rows)-1 else 'middle')
        parts.append('<text x="{:.2f}" y="278" text-anchor="{}">{}</text>'.format(
            x(index), anchor, _escape(dates[index])))
    parts.append('<text x="505" y="315" text-anchor="middle">Date · equally spaced observations</text>'
                 '</svg></div></section>')
    return "".join(parts)


def render_report(daily: Sequence[Mapping[str, Any]], summary: Mapping[str, Any],
                  title: str = _DEFAULT_TITLE) -> str:
    """Render a season report. Missing numeric values are gaps; invalid ones raise ValueError.

    Rows retain their supplied order. Date labels and all metadata are treated as text.
    Daily depths share a mm/day axis; depletion thresholds share a separate mm axis.
    """
    dates = [str(row.get("date", "—")) for row in daily]
    rows = [{field: _number(row.get(field), field, index) for field in _FIELDS}
            for index, row in enumerate(daily)]
    safe_title = _escape(title)
    period = '{} — {}'.format(_escape(dates[0]), _escape(dates[-1])) if dates else 'No daily observations'
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>{}</title><style>{}</style></head><body><main>'.format(safe_title, _CSS),
             '<header><div class="eyebrow">Fieldwater · Season overview</div><h1>{}</h1>'
             '<p class="muted">{} · {} observations</p></header>'.format(safe_title, period, len(rows)),
             '<section><h2>Season summary</h2>']
    if summary:
        parts.append('<table><caption>Season totals, management settings, and crop / soil metadata. Water depths are millimetres.</caption>'
                     '<thead><tr><th scope="col">Metric</th><th scope="col">Value</th></tr></thead><tbody>')
        for key, value in summary.items():
            parts.append('<tr><th scope="row">{}</th><td>{}</td></tr>'.format(_escape(_metric_label(key)), _escape(_display(value))))
        parts.append('</tbody></table>')
    else:
        parts.append('<p class="empty">No summary metadata available.</p>')
    parts.append('</section>')
    parts.append(_chart('water', 'Evapotranspiration and rainfall',
                        'ET0 (reference) and ETc (crop) are lines; rain is bars. All use the same daily depth scale.',
                        dates, rows, [('et0', 'ET0 (mm/day)', 'a'), ('etc', 'ETc (mm/day)', 'b')],
                        'Daily water depth (mm/day)', rain=True))
    parts.append(_chart('depletion', 'Root-zone depletion and irrigation',
                        'Dr: depletion; RAW: readily available water; TAW: total available water. Diamonds mark irrigation dates.',
                        dates, rows, [('dr', 'Dr (mm)', 'a'), ('raw', 'RAW (mm)', 'b'), ('taw', 'TAW (mm)', 'c')],
                        'Root-zone water depth (mm)', events=True))
    parts.append(_chart('coefficient', 'Crop coefficient', 'Kc describes crop water demand relative to reference ET0.',
                        dates, rows, [('kc', 'Kc (dimensionless)', 'a')], 'Kc (dimensionless)'))
    parts.append('<section><h2>Irrigation calendar</h2>')
    events = [(dates[index], row) for index, row in enumerate(rows)
              if (row['irrigation_net'] or 0) > 0 or (row['irrigation_gross'] or 0) > 0]
    if events:
        parts.append('<div class="scroll"><table><caption>Days with positive net or gross irrigation.</caption>'
                     '<thead><tr><th scope="col">Date</th><th scope="col">Net (mm)</th>'
                     '<th scope="col">Gross (mm)</th></tr></thead><tbody>')
        for date, row in events:
            parts.append('<tr><th scope="row">{}</th><td>{}</td><td>{}</td></tr>'.format(
                _escape(date), _display(row['irrigation_net']), _display(row['irrigation_gross'])))
        parts.append('</tbody></table></div>')
    else:
        parts.append('<p class="empty">No irrigation events recorded.</p>')
    parts.append('</section><footer>Decision support: calibrate crop, soil, rainfall, and irrigation assumptions locally. '
                 'Daily observations are shown in supplied order. Missing values are gaps; '
                 'chart spacing represents observations, not elapsed time.</footer></main></body></html>')
    return "".join(parts)


def write_report(path: Union[str, Path], daily: Sequence[Mapping[str, Any]],
                 summary: Mapping[str, Any], title: str = _DEFAULT_TITLE) -> None:
    """Write a UTF-8 HTML report to an existing directory."""
    report = render_report(daily, summary, title)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        handle.write(report)
