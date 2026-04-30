from datetime import datetime, timezone
from typing import Annotated

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


class TidePoint(BaseModel):
    date_time: datetime
    value: float


class TideResponse(BaseModel):
    lat: float
    lon: float
    alt: float
    unit: GravityUnit
    corrections: list[TidePoint]
