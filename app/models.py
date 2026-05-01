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
