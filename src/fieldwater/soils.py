"""Representative soil water properties and FAO56 root-zone water calculations.

Source: Allen et al. (1998), FAO Irrigation and Drainage Paper 56.
Table 19 (Chapter 7): https://www.fao.org/4/x0490e/x0490e0c.htm
Equations 82 and 83 and the ETc adjustment (Chapter 8):
https://www.fao.org/4/x0490e/x0490e0e.htm
Verification: both FAO web chapters were read on 2026-11-07; the texture
rows, water-content ranges, equations, units, and adjustment limits were checked.

SOILS contains selected representative values, not universal texture constants
or measurements at a particular site. Use measured local properties when known.
Each pair lies within Table 19's field-capacity, wilting-point, and difference
ranges. The source ranges, in m3/m3, are:

    key                theta_fc     theta_wp     theta_fc - theta_wp
    sand               .07-.17      .02-.07      .05-.11
    loamy_sand         .11-.19      .03-.10      .06-.12
    sandy_loam         .18-.28      .06-.16      .11-.15
    loam               .20-.30      .07-.17      .13-.18
    silt_loam          .22-.36      .09-.21      .13-.19
    silt               .28-.36      .12-.22      .16-.20
    silty_clay_loam    .30-.37      .17-.24      .13-.18
    silty_clay         .30-.42      .17-.29      .13-.19
    clay               .32-.40      .20-.24      .12-.20

The source labels silty clay loam as "Silt clay loam" and prints the lower
silty-clay field-capacity bound as "0-30", interpreted here as 0.30.
Clay loam, sandy clay loam, and sandy clay have no Table 19 rows and are omitted.
Calculations assume one uniform root-zone layer: volumetric contents are m3/m3,
rooting depth is metres, TAW/RAW are millimetres, and ETc is mm/day. The input p
for adjustment is the crop depletion fraction at ETc = 5 mm/day; no extra
texture correction is applied. Numeric inputs must be finite real numbers
representable as floats; booleans are rejected. Invalid types raise TypeError,
and nonfinite or out-of-range values raise ValueError.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

__all__ = [
    "Soil",
    "SOILS",
    "get_soil",
    "total_available_water",
    "readily_available_water",
    "adjust_depletion_fraction",
]


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite and representable as a float") from None
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _water_contents(theta_fc: Real, theta_wp: Real) -> tuple[float, float]:
    fc = _finite_real(theta_fc, "theta_fc")
    wp = _finite_real(theta_wp, "theta_wp")
    if not 0.0 <= wp < fc <= 1.0:
        raise ValueError("water contents must satisfy 0 <= theta_wp < theta_fc <= 1")
    return fc, wp


def _nonnegative(value: Real, name: str) -> float:
    number = _finite_real(value, name)
    if number < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return number


def _fraction(p: Real) -> float:
    number = _finite_real(p, "p")
    if not 0.0 <= number <= 1.0:
        raise ValueError("p must be between 0 and 1 inclusive")
    return number


@dataclass(frozen=True)
class Soil:
    """Immutable soil identity and volumetric field-capacity/wilting contents."""

    key: str
    name: str
    theta_fc: float
    theta_wp: float

    def __post_init__(self) -> None:
        for field in ("key", "name"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string")
            if not value.strip():
                raise ValueError(f"{field} must not be empty")
        fc, wp = _water_contents(self.theta_fc, self.theta_wp)
        object.__setattr__(self, "theta_fc", fc)
        object.__setattr__(self, "theta_wp", wp)


# Selected rounded values, not values individually prescribed by FAO.
SOILS: dict[str, Soil] = {
    soil.key: soil
    for soil in (
        Soil("sand", "Sand", 0.12, 0.04),
        Soil("loamy_sand", "Loamy sand", 0.15, 0.06),
        Soil("sandy_loam", "Sandy loam", 0.24, 0.11),
        Soil("loam", "Loam", 0.27, 0.12),
        Soil("silt_loam", "Silt loam", 0.30, 0.14),
        Soil("silt", "Silt", 0.32, 0.14),
        Soil("silty_clay_loam", "Silty clay loam", 0.34, 0.19),
        Soil("silty_clay", "Silty clay", 0.36, 0.21),
        Soil("clay", "Clay", 0.36, 0.22),
    )
}


def get_soil(name: str) -> Soil:
    """Look up a texture, ignoring case and whitespace/underscore/hyphen style.

    Raise TypeError for a non-string and ValueError for an unknown texture.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    key = "_".join(name.casefold().replace("_", " ").replace("-", " ").split())
    try:
        return SOILS[key]
    except KeyError:
        choices = ", ".join(SOILS)
        raise ValueError(f"Unknown soil texture {name!r}; choose from: {choices}") from None


def total_available_water(theta_fc: float, theta_wp: float, zr: float) -> float:
    """Return TAW in mm: 1000 * (theta_fc - theta_wp) * zr (FAO56 Eq. 82).

    Contents are volumetric fractions with 0 <= theta_wp < theta_fc <= 1;
    zr is nonnegative rooting depth in metres. Zero depth returns zero.
    Raise ValueError if the resulting water depth overflows a finite float.
    """
    fc, wp = _water_contents(theta_fc, theta_wp)
    depth = _nonnegative(zr, "zr")
    taw = 1000.0 * (fc - wp) * depth
    if not isfinite(taw):
        raise ValueError("total available water exceeds the finite float range")
    return taw


def readily_available_water(taw: float, p: float) -> float:
    """Return RAW in mm: p * taw (FAO56 Eq. 83); taw >= 0 and 0 <= p <= 1."""
    water = _nonnegative(taw, "taw")
    fraction = _fraction(p)
    return fraction * water


def adjust_depletion_fraction(p: float, etc: float) -> float:
    """Return p + 0.04 * (5 - ETc), limited to [0.1, 0.8] (FAO56 Ch. 8).

    p is the unadjusted fraction in [0, 1]; etc is nonnegative ETc in mm/day.
    """
    fraction = _fraction(p)
    evapotranspiration = _nonnegative(etc, "etc")
    return min(0.8, max(0.1, fraction + 0.04 * (5.0 - evapotranspiration)))
