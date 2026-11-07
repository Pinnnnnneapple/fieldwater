"""Scientific table checks and boundary/validation contracts (stdlib unittest).

Reference tables verified 2026-11-07 in FAO-56 chapters 6-8; source links
and the distinction between sourced data and planning assumptions live in
the two modules. Run with PYTHONPATH=src python -m unittest discover -s tests.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from fieldwater.crops import (
    CROPS, Crop, adjust_kc, crop_et, get_crop, kc_curve, load_crop, root_depth,
)
from fieldwater.soils import (
    SOILS, Soil, adjust_depletion_fraction, get_soil,
    readily_available_water, total_available_water,
)


# Independent table transcription: Kc_ini/mid/end, height, Table 22 root
# range/p, and Table 24 seasonal Ky. Range selections are explicit in notes.
_CROP_ROWS = {
    "maize": ((.30, 1.20, .35), 2., (1., 1.7), .55, 1.25),
    "wheat_spring": ((.30, 1.15, .25), 1., (1., 1.5), .55, 1.15),
    "wheat_winter": ((.70, 1.15, .25), 1., (1.5, 1.8), .55, 1.05),
    "rice": ((1.05, 1.20, .60), 1., (.5, 1.), .20, None),
    "soybean": ((.40, 1.15, .50), 1., (.6, 1.3), .50, .85),
    "potato": ((.50, 1.15, .75), .6, (.4, .6), .35, 1.1),
    "tomato": ((.60, 1.15, .80), .6, (.7, 1.5), .40, 1.05),
    "cotton": ((.35, 1.20, .50), 1.5, (1., 1.7), .65, .85),
    "sugarcane": ((.40, 1.25, .75), 3., (1.2, 2.), .65, 1.2),
    "alfalfa": ((.40, 1.20, 1.15), .7, (1., 2.), .55, 1.1),
    "sorghum": ((.30, 1.05, .55), 1.5, (1., 2.), .55, .9),
    "barley": ((.30, 1.15, .25), 1., (1., 1.5), .55, None),
    "sunflower": ((.35, 1.15, .35), 2., (.8, 1.5), .45, .95),
    "groundnut": ((.40, 1.15, .60), .4, (.5, 1.), .50, .70),
    "onion": ((.70, 1.05, .75), .4, (.3, .6), .30, 1.1),
    "cabbage": ((.70, 1.05, .95), .4, (.5, .8), .45, .95),
    "lettuce": ((.70, 1., .95), .3, (.3, .5), .30, None),
    "pepper": ((.60, 1.05, .90), .7, (.5, 1.), .30, 1.1),
    "citrus": ((.70, .65, .70), 4., (1.2, 1.5), .50, None),
    "grapes": ((.30, .85, .45), 2., (1., 2.), .35, .85),
    "olive": ((.65, .70, .70), 4., (1.2, 1.7), .65, None),
}

# Table 19 ranges, including the available-water difference constraint.
_SOIL_RANGES = {
    "sand": ((.07, .17), (.02, .07), (.05, .11)),
    "loamy_sand": ((.11, .19), (.03, .10), (.06, .12)),
    "sandy_loam": ((.18, .28), (.06, .16), (.11, .15)),
    "loam": ((.20, .30), (.07, .17), (.13, .18)),
    "silt_loam": ((.22, .36), (.09, .21), (.13, .19)),
    "silt": ((.28, .36), (.12, .22), (.16, .20)),
    "silty_clay_loam": ((.30, .37), (.17, .24), (.13, .18)),
    "silty_clay": ((.30, .42), (.17, .29), (.13, .19)),
    "clay": ((.32, .40), (.20, .24), (.12, .20)),
}


class CropTableTests(unittest.TestCase):
    def test_all_requested_crops_match_sourced_parameters(self):
        for key, (coeffs, height, roots, p, ky) in _CROP_ROWS.items():
            with self.subTest(crop=key):
                crop = get_crop(key)
                self.assertEqual((crop.kc_ini, crop.kc_mid, crop.kc_end), coeffs)
                self.assertEqual(crop.height, height)
                self.assertEqual((crop.zr_min, crop.zr_max), roots)
                self.assertEqual(crop.p, p)
                self.assertEqual(crop.ky, ky)

    def test_every_entry_is_immutable_and_has_provenance(self):
        for key, crop in CROPS.items():
            with self.subTest(crop=key):
                self.assertEqual(crop.key, key)
                self.assertEqual(len(crop.stages), 4)
                self.assertGreater(sum(crop.stages), 0)
                self.assertIn("FAO-56 Table 11:", crop.stage_source)
                self.assertIn("Root-growth assumption", crop.notes)
                with self.assertRaises(FrozenInstanceError):
                    crop.p = .2

    def test_missing_ky_is_explicit(self):
        for crop in CROPS.values():
            if crop.ky is None:
                with self.subTest(crop=crop.key):
                    self.assertIn("No sourced universal single seasonal Ky", crop.notes)

    def test_rice_saturation_caveat(self):
        self.assertIn("saturation", get_crop("rice").notes)
        self.assertIn("ponded-water", get_crop("rice").notes)

    def test_sorghum_source_total_inconsistency_is_not_hidden(self):
        crop = get_crop("sorghum")
        self.assertEqual(sum(crop.stages), 125)
        self.assertIn("130", crop.notes)

    def test_stages_keep_regional_context(self):
        expected = {"maize": (30, 40, 50, 30), "wheat_spring": (20, 25, 60, 30),
                    "wheat_winter": (30, 140, 40, 30), "rice": (30, 30, 60, 30),
                    "soybean": (20, 35, 60, 25), "potato": (25, 30, 45, 30),
                    "tomato": (30, 40, 45, 30), "cotton": (30, 50, 60, 55),
                    "sugarcane": (35, 60, 190, 120), "alfalfa": (10, 20, 20, 10),
                    "sorghum": (20, 35, 40, 30), "barley": (20, 25, 60, 30),
                    "sunflower": (25, 35, 45, 25), "groundnut": (25, 35, 45, 25),
                    "onion": (15, 25, 70, 40), "cabbage": (40, 60, 50, 15),
                    "lettuce": (20, 30, 15, 10), "pepper": (30, 35, 40, 20),
                    "citrus": (60, 90, 120, 95), "grapes": (20, 50, 75, 60),
                    "olive": (30, 90, 60, 90)}
        for key, stages in expected.items():
            with self.subTest(crop=key):
                self.assertEqual(get_crop(key).stages, stages)

    def test_climate_variants_use_distinct_sourced_stage_lengths(self):
        self.assertEqual(get_crop("maize arid").stages, (25, 40, 45, 30))
        self.assertEqual(get_crop("maize humid").stages, (20, 35, 40, 30))
        self.assertEqual(get_crop("soybean tropical").stages, (15, 15, 40, 15))
        self.assertEqual(get_crop("sugarcane ratoon").stages, (25, 70, 135, 50))
        self.assertIsNot(get_crop("maize arid"), get_crop("maize"))

    def test_winter_wheat_frozen_variant(self):
        crop = get_crop("wheat winter frozen")
        self.assertEqual(crop.kc_ini, .40)
        self.assertEqual(crop.stages, (160, 75, 75, 25))
        self.assertEqual(get_crop("wheat winter").kc_ini, .70)

    def test_wine_grapes_have_wine_specific_kc_and_p(self):
        crop = get_crop("wine grapes")
        self.assertEqual((crop.kc_mid, crop.p), (.70, .45))
        self.assertEqual(crop.stages, (30, 60, 40, 80))

    def test_aliases_and_case_separator_normalization(self):
        for alias, key in {"  MAIZE--grain  ": "maize", "spring wheat": "wheat_spring",
                           "winter-wheat": "wheat_winter", "PEANUT": "groundnut",
                           "soybeans": "soybean", "sugar cane": "sugarcane",
                           "bell pepper": "pepper", "olives": "olive"}.items():
            with self.subTest(alias=alias):
                self.assertIs(get_crop(alias), CROPS[key])

    def test_ambiguous_wheat_default_is_spring(self):
        self.assertIs(get_crop("wheat"), get_crop("spring wheat"))

    def test_unknown_crop_error_lists_choices(self):
        with self.assertRaisesRegex(ValueError, "Unknown crop 'unknown'; choose from:.*maize"):
            get_crop("unknown")

    def test_name_type_validation(self):
        for value in (None, True, 3, []):
            with self.subTest(value=value), self.assertRaisesRegex(TypeError, "crop name must be a string"):
                get_crop(value)


class CropValidationTests(unittest.TestCase):
    def setUp(self):
        self.crop = get_crop("maize")

    def test_numeric_type_validation_in_all_fields(self):
        for field in ("kc_ini", "kc_mid", "kc_end", "height", "zr_min", "zr_max", "p", "ky"):
            for value in (True, "0.5", complex(1, 0), []):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(TypeError, field):
                    replace(self.crop, **{field: value})

    def test_nonfinite_numeric_fields_rejected(self):
        for field in ("kc_ini", "kc_mid", "kc_end", "height", "zr_min", "zr_max", "p", "ky"):
            for value in (math.nan, math.inf, -math.inf, 10 ** 400):
                with self.subTest(field=field, value=str(value)[:20]), self.assertRaisesRegex(ValueError, "finite"):
                    replace(self.crop, **{field: value})

    def test_invalid_numeric_ranges(self):
        invalid = {"kc_ini": -1, "kc_mid": -1, "kc_end": -1, "height": 0,
                   "zr_min": 0, "zr_max": .5, "p": 1.1, "ky": -1}
        for field, value in invalid.items():
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                replace(self.crop, **{field: value})

    def test_p_and_ky_boundaries(self):
        for p in (0, 1):
            self.assertEqual(replace(self.crop, p=p).p, p)
        self.assertEqual(replace(self.crop, ky=0).ky, 0)
        self.assertIsNone(replace(self.crop, ky=None).ky)

    def test_stages_must_be_immutable_integers(self):
        for stages in ([1, 2, 3, 4], (1., 2, 3, 4), (True, 2, 3, 4), "1234"):
            with self.subTest(stages=stages), self.assertRaises(TypeError):
                replace(self.crop, stages=stages)

    def test_invalid_stage_lengths(self):
        for stages in ((1, 2, 3), (1, 2, 3, 4, 5), (1, -2, 3, 4), (0, 0, 0, 0)):
            with self.subTest(stages=stages), self.assertRaises(ValueError):
                replace(self.crop, stages=stages)

    def test_text_fields_validated(self):
        for field in ("key", "name", "stage_source", "notes"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                replace(self.crop, **{field: None})
        for field in ("key", "name", "stage_source"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.crop, **{field: "  "})
        self.assertEqual(replace(self.crop, notes="").notes, "")


class CurveTests(unittest.TestCase):
    def setUp(self):
        self.crop = replace(get_crop("maize"), kc_ini=.2, kc_mid=1.2, kc_end=.4,
                            stages=(2, 4, 3, 4), zr_min=.2, zr_max=1.4)

    def test_initial_stage_is_constant(self):
        self.assertEqual(kc_curve(0, self.crop), .2)
        self.assertEqual(kc_curve(1, self.crop), .2)

    def test_development_starts_at_initial_coefficient(self):
        self.assertEqual(kc_curve(2, self.crop), .2)
        self.assertAlmostEqual(kc_curve(3, self.crop), .45)

    def test_development_midpoint(self):
        self.assertAlmostEqual(kc_curve(4, self.crop), .7)

    def test_midseason_boundary_and_plateau(self):
        for day in (6, 7, 8, 9):
            self.assertEqual(kc_curve(day, self.crop), 1.2)

    def test_late_season_midpoint(self):
        self.assertAlmostEqual(kc_curve(11, self.crop), .8)

    def test_end_is_at_total_not_last_day(self):
        self.assertAlmostEqual(kc_curve(12, self.crop), .6)
        self.assertEqual(kc_curve(13, self.crop), .4)
        self.assertEqual(kc_curve(10 ** 100, self.crop), .4)

    def test_overrides_include_zero_and_do_not_mutate(self):
        self.assertEqual(kc_curve(0, self.crop, kc_ini=0), 0)
        self.assertEqual(kc_curve(6, self.crop, kc_mid=0), 0)
        self.assertEqual(kc_curve(13, self.crop, kc_end=0), 0)
        self.assertAlmostEqual(kc_curve(4, self.crop, .4, .8, .2), .6)
        self.assertEqual(self.crop.kc_ini, .2)

    def test_every_override_is_validated_even_when_unused(self):
        for field in ("kc_ini", "kc_mid", "kc_end"):
            for value, error in ((True, TypeError), ("1", TypeError), (-1, ValueError),
                                 (math.nan, ValueError), (math.inf, ValueError)):
                with self.subTest(field=field, value=value), self.assertRaises(error):
                    kc_curve(0, self.crop, **{field: value})

    def test_increasing_late_season_citrus_is_supported(self):
        crop = get_crop("citrus")
        late_start = sum(crop.stages[:3])
        self.assertEqual(kc_curve(late_start, crop), .65)
        self.assertGreater(kc_curve(late_start + 10, crop), .65)
        self.assertEqual(kc_curve(sum(crop.stages), crop), .70)

    def test_zero_development_skips_ramp(self):
        crop = replace(self.crop, stages=(2, 0, 3, 4))
        self.assertEqual(kc_curve(1, crop), .2)
        self.assertEqual(kc_curve(2, crop), 1.2)
        self.assertEqual(root_depth(2, crop), 1.4)

    def test_zero_initial_and_mid_stages(self):
        crop = replace(self.crop, stages=(0, 4, 0, 4))
        self.assertEqual(kc_curve(0, crop), .2)
        self.assertAlmostEqual(kc_curve(2, crop), .7)
        self.assertEqual(kc_curve(4, crop), 1.2)
        self.assertAlmostEqual(kc_curve(6, crop), .8)

    def test_zero_late_stage_jumps_to_endpoint(self):
        crop = replace(self.crop, stages=(2, 4, 3, 0))
        self.assertEqual(kc_curve(8, crop), 1.2)
        self.assertEqual(kc_curve(9, crop), .4)

    def test_only_initial_or_only_late_stage(self):
        initial = replace(self.crop, stages=(3, 0, 0, 0))
        self.assertEqual(kc_curve(2, initial), .2)
        self.assertEqual(kc_curve(3, initial), .4)
        late = replace(self.crop, stages=(0, 0, 0, 4))
        self.assertEqual(kc_curve(0, late), 1.2)
        self.assertAlmostEqual(kc_curve(2, late), .8)

    def test_day_validation_for_both_curves(self):
        for function in (kc_curve, root_depth):
            for day in (True, 1., "1", None):
                with self.subTest(function=function.__name__, day=day), self.assertRaisesRegex(TypeError, "day must be an integer"):
                    function(day, self.crop)
            with self.assertRaisesRegex(ValueError, "day must be >= 0"):
                function(-1, self.crop)

    def test_crop_type_validation(self):
        for function in (kc_curve, root_depth):
            with self.assertRaisesRegex(TypeError, "crop must be a Crop"):
                function(0, "maize")

    def test_root_initial_development_and_final_boundaries(self):
        self.assertEqual(root_depth(0, self.crop), .2)
        self.assertEqual(root_depth(2, self.crop), .2)
        self.assertAlmostEqual(root_depth(4, self.crop), .8)
        self.assertEqual(root_depth(6, self.crop), 1.4)
        self.assertEqual(root_depth(10 ** 100, self.crop), 1.4)

    def test_constant_root_depth(self):
        crop = replace(self.crop, zr_max=.2)
        for day in range(15):
            self.assertEqual(root_depth(day, crop), .2)

    def test_all_crop_curves_are_bounded_and_roots_are_monotonic(self):
        for crop in CROPS.values():
            with self.subTest(crop=crop.key):
                days = range(sum(crop.stages) + 2)
                kc = [kc_curve(day, crop) for day in days]
                roots = [root_depth(day, crop) for day in days]
                self.assertGreaterEqual(min(kc), min(crop.kc_ini, crop.kc_mid, crop.kc_end) - 1e-12)
                self.assertLessEqual(max(kc), max(crop.kc_ini, crop.kc_mid, crop.kc_end) + 1e-12)
                self.assertEqual(roots, sorted(roots))
                self.assertEqual(roots[0], crop.zr_min)
                self.assertEqual(roots[-1], crop.zr_max)


class ClimateAndETTests(unittest.TestCase):
    def test_reference_climate_leaves_kc_unchanged(self):
        for crop in CROPS.values():
            with self.subTest(crop=crop.key):
                self.assertEqual(adjust_kc(crop.kc_mid, 2, 45, crop.height), crop.kc_mid)

    def test_equation62_exact_unit_height_factor(self):
        # h=3 m makes the height factor 1: .04*(4-2)-.004*(25-45)=.16.
        self.assertAlmostEqual(adjust_kc(1.2, 4, 25, 3), 1.36)

    def test_height_exponent_matches_equation(self):
        self.assertAlmostEqual(adjust_kc(1.2, 4, 25, 2), 1.2 + .16 * (2 / 3) ** .3)

    def test_wind_and_humidity_have_correct_direction(self):
        self.assertGreater(adjust_kc(1.2, 4, 45, 2), 1.2)
        self.assertLess(adjust_kc(1.2, 2, 80, 2), 1.2)

    def test_dry_endpoint_is_not_adjusted(self):
        for kc in (0, .25, .35, .449999):
            with self.subTest(kc=kc):
                self.assertEqual(adjust_kc(kc, 6, 20, 3), kc)

    def test_exact_point45_is_adjusted(self):
        self.assertAlmostEqual(adjust_kc(.45, 4, 25, 3), .61)

    def test_empirical_domain_clips_wind_humidity_and_tall_height(self):
        self.assertEqual(adjust_kc(1.2, 0, 0, 20), adjust_kc(1.2, 1, 20, 10))
        self.assertEqual(adjust_kc(1.2, 20, 100, 3), adjust_kc(1.2, 6, 80, 3))

    def test_short_vegetation_has_no_aerodynamic_adjustment(self):
        self.assertEqual(adjust_kc(1.2, 4, 25, .05), 1.2)
        self.assertGreater(adjust_kc(1.2, 4, 25, .1), 1.2)

    def test_climate_inputs_are_validated_before_dry_endpoint_bypass(self):
        for key, value, error in (("kc", -1, ValueError), ("u2", -1, ValueError),
                                  ("rh_min", 101, ValueError), ("rh_min", -1, ValueError),
                                  ("height", 0, ValueError), ("height", -1, ValueError)):
            args = dict(kc=.25, u2=2, rh_min=45, height=1)
            args[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(error):
                adjust_kc(**args)
        for key in ("kc", "u2", "rh_min", "height"):
            for value, error in ((True, TypeError), ("2", TypeError), (math.inf, ValueError), (math.nan, ValueError)):
                args = dict(kc=.25, u2=2, rh_min=45, height=1)
                args[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(error):
                    adjust_kc(**args)

    def test_standard_crop_et_and_zero_boundaries(self):
        self.assertEqual(crop_et(1.2, 5), 6)
        self.assertEqual(crop_et(0, 5), 0)
        self.assertEqual(crop_et(1.2, 0), 0)

    def test_et_input_validation_and_overflow(self):
        for position in (0, 1):
            for value, error in ((True, TypeError), ("5", TypeError), (-1, ValueError),
                                 (math.nan, ValueError), (math.inf, ValueError)):
                args = [1.2, 5]
                args[position] = value
                with self.subTest(position=position, value=value), self.assertRaises(error):
                    crop_et(*args)
        with self.assertRaisesRegex(ValueError, "crop ET must be finite"):
            crop_et(1e308, 1e308)


class CustomCropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "crop.json"
        self.data = asdict(get_crop("maize"))
        self.data.update(key="custom", name="Custom cultivar", stage_source="Local observed stages")

    def write_load(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return load_crop(self.path)

    def test_round_trip_preserves_values_and_freezes_stages(self):
        crop = self.write_load(self.data)
        self.assertEqual(crop.key, "custom")
        self.assertEqual(crop.stages, (30, 40, 50, 30))
        self.assertIsInstance(crop.stages, tuple)
        with self.assertRaises(FrozenInstanceError):
            crop.notes = "changed"

    def test_optional_fields_have_explicit_defaults(self):
        for field in ("ky", "stage_source", "notes"):
            del self.data[field]
        crop = self.write_load(self.data)
        self.assertIsNone(crop.ky)
        self.assertIn("not independently verified", crop.stage_source)
        self.assertEqual(crop.notes, "")

    def test_loading_does_not_mutate_registry(self):
        before = dict(CROPS)
        self.write_load(self.data)
        self.assertEqual(CROPS, before)

    def test_null_ky_and_unicode_text(self):
        self.data.update(ky=None, name="水稻试验", notes="Observed locally")
        self.assertEqual(self.write_load(self.data).name, "水稻试验")

    def test_unknown_fields_rejected(self):
        self.data["executable"] = "ignored code must not execute"
        with self.assertRaisesRegex(ValueError, "Invalid crop JSON: unknown fields: executable"):
            self.write_load(self.data)

    def test_required_fields_rejected_with_exact_field_name(self):
        del self.data["kc_mid"]
        with self.assertRaisesRegex(ValueError, "Invalid crop JSON: missing fields: kc_mid"):
            self.write_load(self.data)

    def test_duplicate_json_fields_rejected(self):
        self.path.write_text('{"key":"one","key":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid crop JSON: duplicate JSON field: key"):
            load_crop(self.path)

    def test_nonfinite_json_constants_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            self.data["kc_mid"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "non-finite JSON constant"):
                self.write_load(self.data)

    def test_overflowing_json_exponent_rejected(self):
        raw = json.dumps(self.data).replace('"kc_mid": 1.2', '"kc_mid": 1e400')
        self.path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "kc_mid must be finite"):
            load_crop(self.path)

    def test_json_object_required(self):
        for value in (None, [], 5, "string"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "top-level value must be an object"):
                self.write_load(value)

    def test_invalid_custom_stages_rejected(self):
        for stages in ([1, 2, 3], [True, 2, 3, 4], [1., 2, 3, 4],
                       [1, -2, 3, 4], [0, 0, 0, 0], "1234", None):
            self.data["stages"] = stages
            with self.subTest(stages=stages), self.assertRaisesRegex(ValueError, "Invalid crop JSON:"):
                self.write_load(self.data)

    def test_custom_numeric_strings_and_booleans_rejected(self):
        for value in ("1.2", True, -1):
            self.data["kc_mid"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid crop JSON: kc_mid"):
                self.write_load(self.data)

    def test_malformed_json_and_invalid_utf8_rejected(self):
        for raw in (b'{"key":', b'\xff\xfe'):
            self.path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Invalid crop JSON:"):
                load_crop(self.path)

    def test_oversized_json_rejected(self):
        self.path.write_bytes(b" " * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "file exceeds 1 MiB"):
            load_crop(self.path)

    def test_missing_file_preserves_oserror(self):
        with self.assertRaises(FileNotFoundError):
            load_crop(self.path)


class SoilTests(unittest.TestCase):
    def test_all_soils_within_table19_ranges_including_difference(self):
        self.assertEqual(set(SOILS), set(_SOIL_RANGES))
        for key, ranges in _SOIL_RANGES.items():
            with self.subTest(soil=key):
                soil = get_soil(key)
                self.assertEqual(soil.key, key)
                for value, (low, high) in zip((soil.theta_fc, soil.theta_wp,
                                               soil.theta_fc - soil.theta_wp), ranges):
                    self.assertGreaterEqual(value, low - 1e-12)
                    self.assertLessEqual(value, high + 1e-12)

    def test_soils_are_immutable(self):
        for soil in SOILS.values():
            with self.subTest(soil=soil.key), self.assertRaises(FrozenInstanceError):
                soil.theta_fc = .5

    def test_normalized_soil_lookup(self):
        for name in ("SANDY LOAM", "  sandy--loam ", "sandy_loam", "sandy\tloam"):
            self.assertIs(get_soil(name), SOILS["sandy_loam"])

    def test_unknown_soil_lists_choices(self):
        with self.assertRaisesRegex(ValueError, "Unknown soil texture.*choose from:.*sand"):
            get_soil("unknown")

    def test_soil_name_type_validation(self):
        for value in (None, True, 3):
            with self.subTest(value=value), self.assertRaises(TypeError):
                get_soil(value)

    def test_soil_constructor_content_validation(self):
        for fc, wp in ((.2, .2), (.1, .2), (1.1, .2), (.2, -.1), (math.inf, .1), (.2, math.nan)):
            with self.subTest(fc=fc, wp=wp), self.assertRaises(ValueError):
                Soil("bad", "Bad", fc, wp)
        for fc, wp in ((True, .1), (.2, "0.1")):
            with self.subTest(fc=fc, wp=wp), self.assertRaises(TypeError):
                Soil("bad", "Bad", fc, wp)

    def test_soil_identity_validation(self):
        for key, name in (("", "Sand"), ("sand", " ")):
            with self.subTest(key=key, name=name), self.assertRaises(ValueError):
                Soil(key, name, .2, .1)
        with self.assertRaises(TypeError):
            Soil(None, "Sand", .2, .1)


class WaterTests(unittest.TestCase):
    def test_equation82_metre_to_millimetre_conversion(self):
        self.assertAlmostEqual(total_available_water(.30, .15, 1.2), 180)

    def test_zero_root_depth(self):
        self.assertEqual(total_available_water(.30, .15, 0), 0)

    def test_every_crop_soil_pair_has_physical_water_bounds(self):
        for crop in CROPS.values():
            for soil in SOILS.values():
                with self.subTest(crop=crop.key, soil=soil.key):
                    taw = total_available_water(soil.theta_fc, soil.theta_wp, crop.zr_max)
                    raw = readily_available_water(taw, crop.p)
                    self.assertGreater(taw, 0)
                    self.assertGreaterEqual(raw, 0)
                    self.assertLessEqual(raw, taw)

    def test_equation83_fraction_and_boundaries(self):
        self.assertEqual(readily_available_water(180, .5), 90)
        self.assertEqual(readily_available_water(180, 0), 0)
        self.assertEqual(readily_available_water(180, 1), 180)
        self.assertEqual(readily_available_water(0, .5), 0)

    def test_depletion_adjustment_reference_et(self):
        self.assertEqual(adjust_depletion_fraction(.55, 5), .55)

    def test_depletion_adjustment_demand_direction(self):
        self.assertAlmostEqual(adjust_depletion_fraction(.55, 3), .63)
        self.assertAlmostEqual(adjust_depletion_fraction(.55, 8), .43)

    def test_depletion_adjustment_clamps(self):
        self.assertEqual(adjust_depletion_fraction(.7, 0), .8)
        self.assertEqual(adjust_depletion_fraction(.3, 20), .1)
        self.assertEqual(adjust_depletion_fraction(0, 5), .1)
        self.assertEqual(adjust_depletion_fraction(1, 5), .8)

    def test_exact_depletion_clamp_boundaries(self):
        self.assertAlmostEqual(adjust_depletion_fraction(.5, 15), .1)
        self.assertAlmostEqual(adjust_depletion_fraction(.6, 0), .8)

    def test_invalid_water_contents(self):
        for fc, wp in ((.2, .2), (.1, .2), (1.01, .1), (.2, -.1)):
            with self.subTest(fc=fc, wp=wp), self.assertRaisesRegex(ValueError, "0 <= theta_wp < theta_fc <= 1"):
                total_available_water(fc, wp, 1)

    def test_zero_wilting_and_unit_capacity_are_permitted(self):
        self.assertEqual(total_available_water(1, 0, 1), 1000)

    def test_all_water_functions_reject_nonfinite_and_wrong_types(self):
        functions = ((total_available_water, [.3, .1, 1]),
                     (readily_available_water, [100, .5]),
                     (adjust_depletion_fraction, [.5, 5]))
        for function, args in functions:
            for index in range(len(args)):
                for bad, error in ((True, TypeError), (".3", TypeError), (None, TypeError),
                                   (math.nan, ValueError), (math.inf, ValueError),
                                   (-math.inf, ValueError), (10 ** 400, ValueError)):
                    values = args.copy()
                    values[index] = bad
                    with self.subTest(function=function.__name__, index=index, bad=str(bad)[:20]), self.assertRaises(error):
                        function(*values)

    def test_negative_depth_water_and_et_rejected(self):
        with self.assertRaises(ValueError):
            total_available_water(.3, .1, -1)
        with self.assertRaises(ValueError):
            readily_available_water(-1, .5)
        with self.assertRaises(ValueError):
            adjust_depletion_fraction(.5, -1)

    def test_invalid_p_for_both_water_functions(self):
        for p in (-.1, 1.1):
            with self.subTest(p=p):
                with self.assertRaises(ValueError):
                    readily_available_water(100, p)
                with self.assertRaises(ValueError):
                    adjust_depletion_fraction(p, 5)

    def test_taw_overflow_is_reported(self):
        with self.assertRaisesRegex(ValueError, "finite float range"):
            total_available_water(1, 0, 1e308)


if __name__ == "__main__":
    unittest.main()
