"""Behavior and safety checks for the standalone season report."""

from __future__ import annotations

import datetime
from html.parser import HTMLParser
import math
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from fieldwater.report import render_report, write_report


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def day(date="2026-06-01", **overrides):
    row = dict(date=date, et0=4.0, etc=5.0, etc_adj=4.5, rain=8.0,
               effective_rain=6.0, dr=12.0, raw=30.0, taw=70.0,
               kc=1.25, irrigation_net=0.0, irrigation_gross=0.0, ks=1.0)
    row.update(overrides)
    return row


class ReportTests(unittest.TestCase):
    def svgs(self, source):
        charts = [ET.fromstring(svg) for svg in re.findall(r"<svg\b.*?</svg>", source, re.S)]
        for chart in charts:
            self.assertEqual(chart.attrib["role"], "img")
            identifiers = {node.attrib.get("id") for node in chart.iter()}
            for identifier in chart.attrib["aria-labelledby"].split():
                self.assertIn(identifier, identifiers)
        return charts

    def test_escapes_every_input_text_context(self):
        attack = '\"><script>alert("x")</script><img src=x onerror=alert(1)>&\''
        source = render_report([day(attack, irrigation_net=10)], {attack: attack}, title=attack)
        document = Document(source)
        self.assertNotIn("<script", source)
        self.assertNotIn("<img", source)
        self.assertNotIn(attack, source)
        self.assertIn("&lt;script&gt;", source)
        self.assertIn("&quot;", source)
        self.assertIn("&#x27;", source)
        self.assertGreaterEqual("".join(document.text).count(attack), 5)
        self.assertEqual(len(self.svgs(source)), 3)
        for _, attrs in document.tags:
            self.assertFalse(any(name.startswith("on") for name in attrs))

    def test_entire_report_has_no_external_resources_or_scripts(self):
        source = render_report([day()], {"crop": "maize"})
        for tag, attrs in Document(source).tags:
            self.assertNotIn(tag, ("script", "link", "iframe", "object", "embed", "img"))
            self.assertFalse({"src", "href", "xlink:href", "srcset"} & attrs.keys())
        self.assertNotRegex(source, r"(?i)@import|url\s*\(")
        self.assertIn("prefers-color-scheme:dark", source)
        self.assertIn('name="viewport"', source)
        self.assertIn("@media(max-width:", source)

    def test_lines_bars_and_irrigation_calendar(self):
        source = render_report([
            day(datetime.date(2026, 6, 1)),
            day("2026-06-02", rain=0, dr=22, kc=1.1, irrigation_net=15, irrigation_gross=20),
            day("2026-06-03", dr=8, irrigation_gross=3),
        ], {"total_irrigation_net_mm": 15, "crop": "Maize"})
        charts = self.svgs(source)
        self.assertEqual(len(charts), 3)
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(charts[0].findall("s:rect", ns)), 3)
        for chart in charts:
            curves = [node for node in chart.findall("s:path", ns)
                      if node.attrib.get("class", "").startswith("curve")]
            self.assertTrue(curves)
            self.assertTrue(all("L" in node.attrib["d"] for node in curves))
        markers = [node for node in charts[1].findall("s:path", ns)
                   if node.attrib.get("class") == "event"]
        self.assertEqual(len(markers), 2)
        self.assertIn('<th scope="row">2026-06-02</th><td>15</td><td>20</td>', source)
        self.assertIn("Daily water depth (mm/day)", source)
        self.assertIn("All use the same daily depth scale", source)
        self.assertIn("Root-zone water depth (mm)", source)
        self.assertIn("Kc (dimensionless)", source)
        self.assertIn("2026-06-01", source)
        self.assertIn("2026-06-03", source)

    def test_rain_uses_the_same_scale_as_et(self):
        chart = self.svgs(render_report([day(et0=8, rain=8)], {}))[0]
        ns = {"s": "http://www.w3.org/2000/svg"}
        bar = chart.find("s:rect", ns)
        et0 = next(node for node in chart.findall("s:circle", ns) if node.attrib["class"] == "curve a")
        self.assertAlmostEqual(float(bar.attrib["y"]), float(et0.attrib["cy"]))

    def test_empty_report(self):
        source = render_report([], {})
        self.assertIn("No summary metadata available", source)
        self.assertEqual(source.count("No daily observations available"), 3)
        self.assertIn("No irrigation events recorded", source)
        self.assertNotIn("<svg", source)
        self.assertTrue(source.endswith("</html>"))

    def test_one_day_zero_and_extreme_finite_values(self):
        for row in (day(**{field: 0 for field in day() if field != "date"}),
                    day(et0=1.7e308, etc=-1.7e308, rain=1.7e308)):
            with self.subTest(row=row):
                charts = self.svgs(render_report([row], {}))
                self.assertEqual(len(charts), 3)
                for chart in charts:
                    for node in chart.iter():
                        for attr in ("x", "y", "cx", "cy", "width", "height"):
                            if attr in node.attrib:
                                self.assertTrue(math.isfinite(float(node.attrib[attr])))
                        if "d" in node.attrib:
                            self.assertNotRegex(node.attrib["d"].lower(), "nan|inf")

    def test_missing_values_break_curves(self):
        chart = self.svgs(render_report([day(), day(et0=None), day()], {}))[0]
        ns = {"s": "http://www.w3.org/2000/svg"}
        curve = next(node for node in chart.findall("s:path", ns) if node.attrib.get("class") == "curve a")
        self.assertEqual(curve.attrib["d"].count("M"), 2)
        self.assertNotIn("L", curve.attrib["d"])
        self.assertEqual(len(self.svgs(render_report([{"date": "2026-06-01"}], {}))), 3)

    def test_invalid_numbers_cannot_enter_svg(self):
        for value in (float("nan"), float("inf"), -float("inf"), "NaN", "1e999",
                      '\"/><script>alert(1)</script>', object()):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "et0 must be a finite number"):
                    render_report([day(et0=value)], {})

    def test_write_report_utf8_path_and_string_and_no_partial_invalid_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "season.html"
            for target in (path, str(path)):
                self.assertIsNone(write_report(target, [day()], {"crop": "玉米"}, "Season 水"))
                self.assertEqual(path.read_bytes(),
                                 render_report([day()], {"crop": "玉米"}, "Season 水").encode("utf-8"))
            previous = path.read_bytes()
            with self.assertRaises(ValueError):
                write_report(path, [day(kc=float("nan"))], {})
            self.assertEqual(path.read_bytes(), previous)

    def test_inputs_are_not_modified(self):
        row = day()
        original = row.copy()
        summary = {"crop": "Maize"}
        render_report([row], summary)
        self.assertEqual(row, original)
        self.assertEqual(summary, {"crop": "Maize"})


if __name__ == "__main__":
    unittest.main()
