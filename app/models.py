from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

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

_MAX_SERIES_SAMPLES = 10_000


# ── Time-series tide correction ─────────────────────────────────────────────

class TideSeriesRequest(BaseModel):
    """Request body for a tidal correction time-series at a static location."""

    lat: Latitude
    lon: Longitude
    alt: Altitude = Field(default=0.0)
    start_date_time: datetime = Field(description="UTC start of the time series (inclusive)")
    end_date_time: datetime = Field(description="UTC end of the time series (inclusive)")
    resolution_seconds: int = Field(
        default=3600,
        ge=1,
        description="Time step between samples in seconds (default: 3600 = 1 hour)",
    )

    @model_validator(mode="after")
    def validate_window(self) -> "TideSeriesRequest":
        start = self.start_date_time.astimezone(timezone.utc)
        end = self.end_date_time.astimezone(timezone.utc)

        if end <= start:
            raise ValueError("end must be after start")

        n_samples = int((end - start).total_seconds() / self.resolution_seconds) + 1
        if n_samples > _MAX_SERIES_SAMPLES:
            raise ValueError(
                f"Request would produce {n_samples} samples; maximum is {_MAX_SERIES_SAMPLES}. "
                f"Increase resolution_seconds or shorten the window."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "lat": 48.8000000,
                    "lon": 17.7000000,
                    "alt": 113.0,
                    "start_date_time": "2024-06-15T00:00:00Z",
                    "end_date_time": "2024-06-15T23:00:00Z",
                    "resolution_seconds": 3600,
                }
            ]
        }
    }


class TideSeriesPoint(BaseModel):
    date_time: datetime
    value: float


class TideSeriesResponse(BaseModel):
    lat: float
    lon: float
    alt: float
    start_date_time: datetime
    end_date_time: datetime
    resolution_seconds: int
    unit: GravityUnit
    corrections: list[TideSeriesPoint]


# ── Batch (arbitrary timestamps) tide correction ────────────────────────────

_MAX_BATCH_SAMPLES = 10_000


class TideBatchRequest(BaseModel):
    """Request body for tidal corrections at an explicit list of timestamps."""

    lat: Latitude
    lon: Longitude
    alt: Altitude = Field(default=0.0)
    date_times: list[datetime] = Field(
        min_length=1,
        max_length=_MAX_BATCH_SAMPLES,
        description=f"List of UTC datetimes to compute corrections for (max {_MAX_BATCH_SAMPLES})",
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


class TideBatchResponse(BaseModel):
    lat: float
    lon: float
    alt: float
    unit: GravityUnit
    corrections: list[TideSeriesPoint]
