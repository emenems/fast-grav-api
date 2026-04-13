from enum import StrEnum


class GravityUnit(StrEnum):
    mgal = "mgal"
    gal = "gal"
    ugal = "ugal"
    nm_s2 = "nm_s2"


# All factors convert FROM milliGal
_MGAL_TO: dict[GravityUnit, float] = {
    GravityUnit.mgal: 1.0,
    GravityUnit.gal: 1e-3,
    GravityUnit.ugal: 1e3,
    GravityUnit.nm_s2: 1e4,   # 1 mGal = 10⁻⁵ m/s² = 10 000 nm/s²
}


def convert_from_mgal(value_mgal: float, unit: GravityUnit) -> float:
    return value_mgal * _MGAL_TO[unit]
