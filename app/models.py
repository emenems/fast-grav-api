from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.units import GravityUnit


# ── Shared field types ──────────────────────────────────────────────────────

Latitude = Annotated[float, Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees (WGS-84)")]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees (WGS-84)")]
Altitude = Annotated[
    float,
    Field(
        description=(
            "Altitude above sea level in metres. "
            "Used in Longman (1959) to compute the geocentric distance r = C·a + H, "
            "where a is Earth's equatorial radius and H is this value converted to cm."
        )
    ),
]

_MAX_SAMPLES = 10_000


# ── Tide correction ─────────────────────────────────────────────────────────

class TideRequest(BaseModel):
    """Request body for tidal corrections at an explicit list of timestamps."""

    lat: Latitude
    lon: Longitude
    alt: Altitude = Field(default=0.0)
    date_times: list[datetime] = Field(
        min_length=1,
        max_length=_MAX_SAMPLES,
        description=f"List of UTC datetimes to compute corrections for (max {_MAX_SAMPLES})",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "lat": 48.8,
                    "lon": 17.7,
                    "alt": 113.0,
                    "date_times": [
                        "2025-05-05T07:47:25Z",
                        "2025-05-05T07:48:35Z",
                        "2025-05-05T08:19:14Z",
                    ],
                }
            ]
        }
    }


# ── Coordinate conversion ────────────────────────────────────────────────────

class CoordinateConvertRequest(BaseModel):
    """One or more coordinate strings to convert to decimal degrees."""

    values: list[str] = Field(
        min_length=1,
        max_length=1_000,
        description="Coordinate strings in DMS or decimal format",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "values": [
                        "48°46'36,30101\"",
                        "17°24'05\"",
                        "48,77675",
                        "-48.77675",
                    ]
                }
            ]
        }
    }


class CoordinateResult(BaseModel):
    input: str
    decimal: float


class CoordinateConvertResponse(BaseModel):
    results: list[CoordinateResult]


# ── S-JTSK ↔ ETRS89 transformation ──────────────────────────────────────────

class JtskToEtrsRequest(BaseModel):
    x: float = Field(description="S-JTSK (JTSK03) Y-westing in metres (Czech/Slovak x convention)")
    y: float = Field(description="S-JTSK (JTSK03) X-southing in metres (Czech/Slovak y convention)")
    mode: Literal["jtsk"]

    model_config = {
        "json_schema_extra": {
            "examples": [{"x": 524551.68, "y": 1214939.24, "mode": "jtsk"}]
        }
    }


class EtrsToJtskRequest(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0, description="ETRS89 geographic latitude in decimal degrees")
    lon: float = Field(ge=-180.0, le=180.0, description="ETRS89 geographic longitude in decimal degrees")
    mode: Literal["etrs"]

    model_config = {
        "json_schema_extra": {
            "examples": [{"lat": 48.776750281, "lon": 17.683095964, "mode": "etrs"}]
        }
    }


TransformRequest = Annotated[
    JtskToEtrsRequest | EtrsToJtskRequest,
    Field(discriminator="mode"),
]


class TransformResponse(BaseModel):
    mode: str
    x: float
    y: float
    lat: float
    lon: float


# ── Tide correction ──────────────────────────────────────────────────────────

class TidePoint(BaseModel):
    date_time: datetime
    value: float


class TideResponse(BaseModel):
    lat: float
    lon: float
    alt: float
    unit: GravityUnit
    corrections: list[TidePoint]


# ── Gravity network adjustment ──────────────────────────────────────────────


class AdjustmentSettings(BaseModel):
    """Tunable parameters for the network adjustment."""

    reference_station: str = Field(
        description=(
            "ID of the benchmark whose absolute gravity is known (or fixed at 0). "
            "Must match a station present in the input. For CG-5 inputs, station IDs "
            "are normalised to four decimals (e.g. `692` matches `692.0000000`)."
        )
    )
    reference_g: float = Field(
        default=0.0,
        description=(
            "Absolute gravity at the reference station, in the same unit as the "
            "`unit` query parameter (default mGal). Returned `abs_g` for every "
            "station = reference_g + Δg. Leave at 0 to get Δg from the reference."
        ),
    )
    reference_sigma: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "1-σ standard error of `reference_g`, in the same unit as `unit` "
            "(default mGal). Propagated into every station's reported σ as "
            "sqrt(σ_Δg² + reference_sigma²). Use 0 if the tie value is treated as exact."
        ),
    )
    gradient: float = Field(
        default=0.3086,
        description=(
            "Vertical gravity gradient in **mGal/m**, applied to every station. "
            "Free-air default is 0.3086 mGal/m. Used to reduce each reading to the "
            "benchmark: g = g_raw + gradient · (height·height_unit_factor + sensor_offset)."
        ),
    )
    drift_degree: int = Field(
        default=1,
        ge=0,
        le=5,
        description=(
            "Polynomial degree of the gravimeter drift model fitted in time. "
            "0 = constant offset, 1 = linear (typical), 2 = quadratic, up to 5."
        ),
    )
    height_unit_factor: float = Field(
        default=0.01,
        gt=0.0,
        description=(
            "Multiplier that converts the input `height` field into **metres**. "
            "0.01 if heights are in cm (CG-5 default), 0.001 if mm, 1.0 if m, "
            "0.0254 if inches."
        ),
    )
    sensor_offset: float = Field(
        default=0.089,
        description=(
            "Vertical offset of the sensing mass relative to the benchmark, in "
            "**metres**. CG-5: +0.089 if the entered height was bottom-of-instrument "
            "to benchmark (sensor is 0.089 m above that); -0.211 if top-of-instrument "
            "to benchmark (sensor is 0.211 m below that)."
        ),
    )
    use_apriori: bool = Field(
        default=False,
        description=(
            "Weighting mode. false (default): weighted LS using each reading's SD. "
            "true: unit weights, with σ₀ estimated a posteriori from residuals."
        ),
    )


class StationOut(BaseModel):
    station: str = Field(description="Benchmark identifier (normalised to 4 decimals for CG-5 inputs).")
    delta_g: float = Field(description="Gravity difference from the reference station, in `unit`.")
    abs_g: float = Field(description="Absolute gravity (= reference_g + delta_g), in `unit`.")
    sigma: float = Field(description="1-σ standard error of `abs_g`, in `unit`. "
                                     "Includes the propagated `reference_sigma`.")


class PairOut(BaseModel):
    from_station: str = Field(description="Benchmark identifier of the start of the tie.")
    to_station: str = Field(description="Benchmark identifier of the end of the tie.")
    delta_g: float = Field(description="Gravity difference g(to) - g(from), in `unit`.")
    sigma: float = Field(description="1-σ standard error of the tie, in `unit`.")


class DriftCoefficient(BaseModel):
    order: int = Field(description="Polynomial order: 0 is the constant term, 1 the linear, etc.")
    value: float = Field(description="Coefficient value, in the unit shown by `unit`.")
    sigma: float = Field(description="1-σ standard error of the coefficient, same unit as `value`.")
    unit: str = Field(description="Composite unit for this coefficient, e.g. `mgal` or `mgal/h^1`.")


class AdjustmentResponse(BaseModel):
    n_measurements: int = Field(description="Number of measurements that were adjusted.")
    n_stations: int = Field(description="Number of unique stations in the adjustment.")
    drift_degree: int = Field(description="Polynomial degree of the fitted drift model.")
    drift: list[DriftCoefficient] = Field(
        description="Drift polynomial coefficients in increasing order "
                    "(constant first, then linear, then quadratic, ...)."
    )
    residual_min: float = Field(description="Minimum residual (model − observation), in `unit`.")
    residual_max: float = Field(description="Maximum residual (model − observation), in `unit`.")
    residuals: list[float] = Field(
        description="Per-measurement residuals (model − observation), in `unit`, "
                    "in the same order as the input."
    )
    model_check: float = Field(
        description="Internal consistency check of the normal-equation solution; "
                    "should be ~0 (machine precision)."
    )
    sigma0: float | None = Field(
        description="A-posteriori unit-weight standard error in `unit` "
                    "(only set when `use_apriori` is true; otherwise null)."
    )
    measurement_start: datetime = Field(description="Timestamp of the first measurement.")
    measurement_end: datetime = Field(description="Timestamp of the last measurement.")
    unit: GravityUnit = Field(description="Unit applied to every gravity value in this response.")
    stations: list[StationOut] = Field(
        description="One row per unique station — the reference station appears first with delta_g = 0."
    )
    pairs: list[PairOut] = Field(
        description="All pairwise gravity ties (every station vs every other station), "
                    "C(n_stations, 2) rows."
    )
