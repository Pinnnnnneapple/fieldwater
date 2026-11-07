"""FAO-56 single crop coefficients and simple daily crop curves.

Verification: checked the FAO HTML tables on 2026-11-07:
https://www.fao.org/4/x0490e/x0490e0b.htm (Tables 11, 12; equations 58, 62, 65)
https://www.fao.org/4/x0490e/x0490e0e.htm (Tables 22, 24).
Table 24 reproduces seasonal Ky from FAO-33. These are planning defaults,
not locally calibrated crop parameters. Kc is dimensionless, heights and
root depths are metres, ET is mm/day, and stage lengths are days.

Table 11 stages describe particular planting dates/regions; see stage_source.
Where Table 12 gives a range, notes identify the selected value. Group-header
Kc_ini values apply to the crops below them. Initial Kc depends strongly on
wetting frequency and is not adjusted here. Table 22 p is for ETc near 5 mm/day.

IMPORTANT ROOT ASSUMPTION: zr_min/zr_max store the lower/upper bounds of
Table 22's *maximum effective* rooting-depth range. Treating zr_min as the
initial depth and growing linearly to zr_max is a provisional scheduling
assumption, not a FAO seedling-root observation. Supply locally observed
depths for seedlings, restricted soils, and established perennial crops.

Curves use elapsed time at the START of a zero-based day: initial [0, Li),
development [Li, Li+Ld), mid-season [Li+Ld, Li+Ld+Lm), late season
[Li+Ld+Lm, total). The transition starts at the preceding coefficient;
Kc_end is reached at day=total, not total-1. Nonnegative days beyond total
hold Kc_end/root maximum; callers must delimit the actual growing season.
Zero-length stages are skipped (possibly making a discontinuity).

Public functions reject booleans/non-real numbers with TypeError, non-finite
or out-of-range numbers with ValueError, and negative/noninteger days with
ValueError/TypeError. No climate adjustment or stress factor is automatic.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
import math
from numbers import Real
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

__all__ = ["Crop", "CROPS", "get_crop", "load_crop", "kc_curve",
           "root_depth", "adjust_kc", "crop_et"]


def _number(name: str, value: Real, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum:g}")
    return result


@dataclass(frozen=True)
class Crop:
    """Immutable parameters; stages=(initial, development, mid, late).

    All coefficients and Ky are nonnegative and finite; height and zr_min
    are positive; zr_max >= zr_min; p is in [0, 1]. Stage lengths must be
    an immutable tuple of four nonnegative integers with a positive total.
    None means no sourced single seasonal Ky has been supplied.
    """

    key: str
    name: str
    kc_ini: float
    kc_mid: float
    kc_end: float
    height: float
    zr_min: float
    zr_max: float
    p: float
    stages: Tuple[int, int, int, int]
    ky: Optional[float] = None
    stage_source: str = "User-supplied stage lengths; not independently verified."
    notes: str = ""

    def __post_init__(self) -> None:
        for field in ("key", "name", "stage_source", "notes"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string")
            if field != "notes" and not value.strip():
                raise ValueError(f"{field} must not be empty")
        for field in ("kc_ini", "kc_mid", "kc_end", "height", "zr_min", "zr_max", "p"):
            object.__setattr__(self, field, _number(field, getattr(self, field)))
        if self.height <= 0:
            raise ValueError("height must be > 0")
        if self.zr_min <= 0:
            raise ValueError("zr_min must be > 0")
        if self.zr_max < self.zr_min:
            raise ValueError("zr_max must be >= zr_min")
        if self.p > 1:
            raise ValueError("p must be <= 1")
        if self.ky is not None:
            object.__setattr__(self, "ky", _number("ky", self.ky))
        if not isinstance(self.stages, tuple):
            raise TypeError("stages must be a tuple of four integers")
        if len(self.stages) != 4:
            raise ValueError("stages must contain exactly four lengths")
        if any(isinstance(x, bool) or not isinstance(x, int) for x in self.stages):
            raise TypeError("stage lengths must be integers")
        if any(x < 0 for x in self.stages):
            raise ValueError("stage lengths must be >= 0")
        if sum(self.stages) == 0:
            raise ValueError("total stage length must be > 0")


_ROOT_NOTE = ("Root-growth assumption: Table 22 maximum-depth range used as "
              "initial/final depths; calibrate locally. ")
_NO_KY = "No sourced universal single seasonal Ky value; ky=None. "


def _entry(key, name, coeffs, height, roots, p, stages, ky, region, notes=""):
    return Crop(key, name, *coeffs, height, *roots, p, stages, ky,
                "FAO-56 Table 11: " + region,
                _ROOT_NOTE + (_NO_KY if ky is None else "Ky: FAO-56 Table 24 (FAO-33). ")
                + notes)


# The defaults select one explicitly identified regional example per crop.
# Alternate stages/climates remain separate records rather than aliases.
_DEFAULTS = [
    _entry("maize", "Maize (grain)", (.30, 1.20, .35), 2.0, (1.0, 1.7), .55,
           (30, 40, 50, 30), 1.25, "Spain/California, April",
           "Dry grain harvest: Kc_end=0.35 (Table 12 range 0.60-0.35)."),
    _entry("wheat_spring", "Spring wheat", (.30, 1.15, .25), 1.0, (1.0, 1.5), .55,
           (20, 25, 60, 30), 1.15, "Barley/Oats/Wheat, 35-45 degrees latitude, March/April",
           "Kc_end=0.25 selected from 0.25-0.40 for dry harvest."),
    _entry("wheat_winter", "Winter wheat (non-frozen soil)", (.70, 1.15, .25), 1.0,
           (1.5, 1.8), .55, (30, 140, 40, 30), 1.05, "Mediterranean, November",
           "Non-frozen-soil Kc_ini; dry-harvest Kc_end=0.25 from 0.25-0.40."),
    _entry("rice", "Rice (paddy)", (1.05, 1.20, .60), 1.0, (.5, 1.0), .20,
           (30, 30, 60, 30), None, "Tropics/Mediterranean, December/May",
           "Kc_end=0.60 selected from 0.90-0.60. Table 22 rice p=0.20 refers to "
           "saturation, not ordinary FC-WP depletion: a ponded-water balance is required. "
           "Initial Kc assumes standing water and subhumid moderate conditions (Table 14)."),
    _entry("soybean", "Soybean", (.40, 1.15, .50), 1.0, (.6, 1.3), .50,
           (20, 35, 60, 25), .85, "Central USA, May; development=35 from 30/35",
           "Height=1.0 m selected from Table 12 range 0.5-1.0 m."),
    _entry("potato", "Potato", (.50, 1.15, .75), .6, (.4, .6), .35,
           (25, 30, 45, 30), 1.1, "Continental climate, May"),
    _entry("tomato", "Tomato", (.60, 1.15, .80), .6, (.7, 1.5), .40,
           (30, 40, 45, 30), 1.05, "Mediterranean, April/May",
           "Kc_end=0.80 is a representative choice within Table 12 range 0.70-0.90."),
    _entry("cotton", "Cotton", (.35, 1.20, .50), 1.5, (1.0, 1.7), .65,
           (30, 50, 60, 55), .85, "Egypt/Pakistan/California, March-May",
           "Selected Kc_mid=1.20 (1.15-1.20), Kc_end=0.50 (0.70-0.50), "
           "height=1.5 m (1.2-1.5)."),
    _entry("sugarcane", "Sugarcane (virgin)", (.40, 1.25, .75), 3.0, (1.2, 2.0), .65,
           (35, 60, 190, 120), 1.2, "virgin crop, low latitudes"),
    _entry("alfalfa", "Alfalfa hay (first cutting)", (.40, 1.20, 1.15), .7,
           (1.0, 2.0), .55, (10, 20, 20, 10), 1.1, "first cutting, California, January/April",
           "Individual cutting-period Kc, not averaged-season Kc. Reset the curve at "
           "cutting; seasonal Ky=1.1 must not be interpreted as a cutting-specific Ky."),
    _entry("sorghum", "Sorghum (grain)", (.30, 1.05, .55), 1.5, (1.0, 2.0), .55,
           (20, 35, 40, 30), .9, "USA/Pakistan/Mediterranean, May/June",
           "Kc_mid=1.05 and height=1.5 m represent Table 12 ranges 1.00-1.10 and 1-2 m. "
           "Stage components sum to 125 days; FAO HTML's total column says 130. "
           "The four listed components are retained without inventing a correction."),
    _entry("barley", "Barley", (.30, 1.15, .25), 1.0, (1.0, 1.5), .55,
           (20, 25, 60, 30), None, "Barley/Oats/Wheat, 35-45 degrees latitude, March/April"),
    _entry("sunflower", "Sunflower", (.35, 1.15, .35), 2.0, (.8, 1.5), .45,
           (25, 35, 45, 25), .95, "Mediterranean/California, April/May",
           "Kc_mid=1.15 selected from Table 12 range 1.00-1.15."),
    _entry("groundnut", "Groundnut (peanut)", (.40, 1.15, .60), .4, (.5, 1.0), .50,
           (25, 35, 45, 25), .70, "West Africa, dry season"),
    _entry("onion", "Onion (dry)", (.70, 1.05, .75), .4, (.3, .6), .30,
           (15, 25, 70, 40), 1.1, "dry onion, Mediterranean, April"),
    _entry("cabbage", "Cabbage", (.70, 1.05, .95), .4, (.5, .8), .45,
           (40, 60, 50, 15), .95, "California desert, September"),
    _entry("lettuce", "Lettuce", (.70, 1.00, .95), .3, (.3, .5), .30,
           (20, 30, 15, 10), None, "Mediterranean, April"),
    _entry("pepper", "Sweet pepper (bell)", (.60, 1.05, .90), .7, (.5, 1.0), .30,
           (30, 35, 40, 20), 1.1, "Europe/Mediterranean, April/June; initial=30 from 25/30"),
    _entry("citrus", "Citrus (70% canopy, bare ground)", (.70, .65, .70), 4.0,
           (1.2, 1.5), .50, (60, 90, 120, 95), None, "Mediterranean, January",
           "Table 24 Ky=1.1-1.3 is a range; no universal single value selected. "
           "Table 12 assumes 70% canopy and no active ground cover. Established roots "
           "do not reset annually; supply appropriate constant depths."),
    _entry("grapes", "Grapes (table or raisin)", (.30, .85, .45), 2.0, (1.0, 2.0), .35,
           (20, 50, 75, 60), .85, "California, March",
           "Table/raisin coefficients and depletion fraction; wine grapes differ. "
           "Established roots do not reset annually."),
    _entry("olive", "Olive (40-60% canopy)", (.65, .70, .70), 4.0, (1.2, 1.7), .65,
           (30, 90, 60, 90), None, "Mediterranean, March",
           "Height=4 m represents Table 12 range 3-5 m. Active-season coefficients; "
           "winter/off-season is not modeled. Table 12 footnote 24 also gives a "
           "different seasonal Spanish example. Established roots do not reset annually."),
]

CROPS: Dict[str, Crop] = {crop.key: crop for crop in _DEFAULTS}


def _variant(base: str, key: str, name: str, region: str, **changes) -> None:
    CROPS[key] = replace(CROPS[base], key=key, name=name,
                         stage_source="FAO-56 Table 11: " + region, **changes)


_variant("maize", "maize_arid", "Maize (grain, arid)", "arid climate, December/January",
         stages=(25, 40, 45, 30))
_variant("maize", "maize_humid", "Maize (grain, humid)", "Nigeria (humid), June",
         stages=(20, 35, 40, 30))
_variant("wheat_winter", "wheat_winter_frozen", "Winter wheat (frozen soil)",
         "Idaho, October", kc_ini=.40, stages=(160, 75, 75, 25),
         notes=_ROOT_NOTE + "Frozen-soil Kc_ini=0.40; dry-harvest Kc_end=0.25. "
         "Ky: FAO-56 Table 24 (FAO-33). Dormancy requires local stage adjustment.")
_variant("soybean", "soybean_tropical", "Soybean (tropical)", "tropics, December",
         stages=(15, 15, 40, 15))
_variant("sugarcane", "sugarcane_ratoon", "Sugarcane (ratoon)", "ratoon, low latitudes",
         stages=(25, 70, 135, 50))
_variant("grapes", "grapes_wine", "Grapes (wine)", "wine, mid latitudes, April",
         kc_mid=.70, p=.45, stages=(30, 60, 40, 80),
         notes=_ROOT_NOTE + "Wine-grape Kc and p; height=2 m selected from 1.5-2 m. "
         "Ky=0.85 is Table 24's grape value, not a wine-specific calibration. "
         "Established roots do not reset annually.")

_ALIASES = {
    "maize_grain": "maize", "grain_maize": "maize", "corn": "maize",
    "field_corn": "maize", "spring_wheat": "wheat_spring", "wheat": "wheat_spring",
    "winter_wheat": "wheat_winter", "soybeans": "soybean", "sugar_cane": "sugarcane",
    "peanut": "groundnut", "peanuts": "groundnut", "groundnuts": "groundnut",
    "dry_onion": "onion", "onion_dry": "onion", "bell_pepper": "pepper",
    "sweet_pepper": "pepper", "sweet_peppers": "pepper", "olives": "olive",
    "grape": "grapes", "wine_grapes": "grapes_wine", "alfalfa_hay": "alfalfa",
}


def get_crop(name: str) -> Crop:
    """Look up a key/alias, ignoring case, whitespace and hyphen separators.

    ValueError lists canonical choices for an unknown name. Bare 'wheat'
    selects spring wheat; winter wheat must be requested explicitly.
    """
    if not isinstance(name, str):
        raise TypeError("crop name must be a string")
    key = "_".join(name.strip().lower().replace("-", " ").replace("_", " ").split())
    key = _ALIASES.get(key, key)
    try:
        return CROPS[key]
    except KeyError:
        raise ValueError(f"Unknown crop {name!r}; choose from: {', '.join(sorted(CROPS))}") from None


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def load_crop(path: Union[str, Path]) -> Crop:
    """Read a UTF-8 JSON object containing Crop fields, without registry mutation.

    Required fields: key, name, kc_ini, kc_mid, kc_end, height, zr_min,
    zr_max, p, stages (array of four integers). Optional: ky (default null),
    stage_source (default explicitly unverified), notes (default empty).
    Unknown/duplicate fields, NaN/Infinity, wrong types, and invalid ranges
    raise ValueError prefixed 'Invalid crop JSON:'. OSError propagates for
    unreadable files. Files over 1 MiB are rejected before parsing.
    """
    with Path(path).open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    try:
        if len(raw) > 1024 * 1024:
            raise ValueError("file exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_pairs,
                          parse_constant=_invalid_constant)
        if not isinstance(data, dict):
            raise ValueError("top-level value must be an object")
        unknown = set(data) - {field.name for field in fields(Crop)}
        if unknown:
            raise ValueError("unknown fields: " + ", ".join(sorted(unknown)))
        required = {"key", "name", "kc_ini", "kc_mid", "kc_end", "height",
                    "zr_min", "zr_max", "p", "stages"}
        missing = required - set(data)
        if missing:
            raise ValueError("missing fields: " + ", ".join(sorted(missing)))
        if not isinstance(data["stages"], list):
            raise ValueError("stages must be an array of four integers")
        data["stages"] = tuple(data["stages"])
        return Crop(**data)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"Invalid crop JSON: {exc}") from exc


def _day_crop(day: int, crop: Crop) -> None:
    if isinstance(day, bool) or not isinstance(day, int):
        raise TypeError("day must be an integer")
    if day < 0:
        raise ValueError("day must be >= 0")
    if not isinstance(crop, Crop):
        raise TypeError("crop must be a Crop")


def kc_curve(day: int, crop: Crop, kc_ini: Optional[float] = None,
             kc_mid: Optional[float] = None, kc_end: Optional[float] = None) -> float:
    """Return four-stage Kc at start of zero-based day; see module boundaries.

    Optional nonnegative finite overrides replace individual coefficients;
    zero is a valid override. No adjustment is applied automatically.
    """
    _day_crop(day, crop)
    ini = _number("kc_ini", crop.kc_ini if kc_ini is None else kc_ini)
    mid = _number("kc_mid", crop.kc_mid if kc_mid is None else kc_mid)
    end = _number("kc_end", crop.kc_end if kc_end is None else kc_end)
    li, ld, lm, ll = crop.stages
    if day >= li + ld + lm + ll:
        return end
    if day < li:
        return ini
    if day < li + ld:
        return ini + (mid - ini) * ((day - li) / ld)
    if day < li + ld + lm:
        return mid
    return mid + (end - mid) * ((day - li - ld - lm) / ll)


def root_depth(day: int, crop: Crop) -> float:
    """Hold zr_min initially, grow through development, then hold zr_max.

    Growth starts at Li and reaches zr_max at Li+Ld. With Ld=0 the
    depth jumps at Li. This is the provisional assumption described above,
    not a physiological root model; mature perennials need local depths.
    """
    _day_crop(day, crop)
    li, ld, _, _ = crop.stages
    if day < li:
        return float(crop.zr_min)
    if day >= li + ld:
        return float(crop.zr_max)
    return crop.zr_min + (crop.zr_max - crop.zr_min) * ((day - li) / ld)


def adjust_kc(kc: float, u2: float, rh_min: float, height: float) -> float:
    """Apply FAO-56 eq. 62/65: Kc + [.04(u2-2)-.004(RHmin-45)](h/3)^.3.

    Intended for stage-average Kc_mid/Kc_end, not daily Kc or Kc_ini.
    Without a stage argument, values <0.45 are treated as dry-harvest
    endpoints and left unchanged; 0.45 is adjusted. For an unusually low
    Kc_mid this convenience rule cannot distinguish the stage.

    u2 is wind at 2 m (m/s); RHmin is percent (not a fraction). Physical
    inputs require u2>=0, 0<=RHmin<=100, h>0. For adjustment they are
    clipped to the FAO empirical domain u2=[1,6], RHmin=[20,80], h<=10.
    Below 0.1 m no correction is made (FAO-56's short-vegetation rule).
    This explicit boundary policy avoids extrapolation. Clipping is not
    evidence that these equations are validated for extreme conditions.
    """
    kc = _number("kc", kc)
    u2 = _number("u2", u2)
    rh_min = _number("rh_min", rh_min)
    height = _number("height", height)
    if rh_min > 100:
        raise ValueError("rh_min must be <= 100")
    if height <= 0:
        raise ValueError("height must be > 0")
    if kc < .45 or height < .1:
        return kc
    wind = min(6.0, max(1.0, u2))
    humidity = min(80.0, max(20.0, rh_min))
    h = min(10.0, max(.1, height))
    return kc + (.04 * (wind - 2.0) - .004 * (humidity - 45.0)) * (h / 3.0) ** .3


def crop_et(kc: float, et0: float) -> float:
    """Standard, unstressed ETc=Kc*ET0 (FAO-56 eq. 58), in ET0's units.

    Both inputs must be finite and nonnegative. Typically ET0 is mm/day.
    """
    result = _number("kc", kc) * _number("et0", et0)
    if not math.isfinite(result):
        raise ValueError("crop ET must be finite")
    return result
