import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial

from fastapi import APIRouter, HTTPException, Query

from tidegravity import solve_longman_tide_scalar

from app.models import (
    TideBatchRequest,
    TideBatchResponse,
    TideSeriesPoint,
    TideSeriesRequest,
    TideSeriesResponse,
)
from app.units import GravityUnit, convert_from_mgal

router = APIRouter(prefix="/tides", tags=["Tidal Corrections"])


def _naive_utc(dt: datetime) -> datetime:
    """Return a timezone-naive UTC datetime (required by tidegravity)."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _compute_series(
    lat: float,
    lon: float,
    alt: float,
    timestamps: list[datetime],
) -> list[float]:
    """Compute tidal corrections for a list of naive UTC timestamps. Runs in a thread."""
    results = []
    for t in timestamps:
        _, _, total = solve_longman_tide_scalar(lat, lon, alt, t)
        results.append(float(total))
    return results



@router.post(
    "/series",
    response_model=TideSeriesResponse,
    summary="Time-series tidal gravity corrections at a static location",
    description=(
        "Compute tidal gravity corrections over a time window at a fixed location. "
        "Samples are evenly spaced by `resolution_seconds`. "
        "Both `start_date_time` and `end_date_time` are inclusive. Maximum 10 000 samples per request."
    ),
)
async def tide_series(
    body: TideSeriesRequest,
    unit: GravityUnit = Query(default=GravityUnit.mgal, description="Output unit for the correction values"),
) -> TideSeriesResponse:
    step = timedelta(seconds=body.resolution_seconds)
    naive_start = _naive_utc(body.start_date_time)
    naive_end = _naive_utc(body.end_date_time)

    # Build the full list of timestamps up front
    timestamps: list[datetime] = []
    t = naive_start
    while t <= naive_end:
        timestamps.append(t)
        t += step

    loop = asyncio.get_running_loop()
    try:
        mgal_values = await loop.run_in_executor(
            None,
            partial(_compute_series, body.lat, body.lon, body.alt, timestamps),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    corrections = [
        TideSeriesPoint(
            date_time=ts.replace(tzinfo=timezone.utc),
            value=convert_from_mgal(mgal, unit),
        )
        for ts, mgal in zip(timestamps, mgal_values)
    ]

    return TideSeriesResponse(
        lat=body.lat,
        lon=body.lon,
        alt=body.alt,
        start_date_time=body.start_date_time,
        end_date_time=body.end_date_time,
        resolution_seconds=body.resolution_seconds,
        unit=unit,
        corrections=corrections,
    )


@router.post(
    "/corrections",
    response_model=TideBatchResponse,
    summary="Tidal gravity corrections for an explicit list of timestamps",
    description=(
        "Compute tidal gravity corrections at a fixed location for an arbitrary, "
        "potentially irregular list of UTC datetimes. Useful for survey data where "
        "observations are not evenly spaced. Maximum 10 000 timestamps per request."
    ),
)
async def tide_corrections_batch(
    body: TideBatchRequest,
    unit: GravityUnit = Query(default=GravityUnit.mgal, description="Output unit for the correction values"),
) -> TideBatchResponse:
    timestamps = [_naive_utc(dt) for dt in body.date_times]

    loop = asyncio.get_running_loop()
    try:
        mgal_values = await loop.run_in_executor(
            None,
            partial(_compute_series, body.lat, body.lon, body.alt, timestamps),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    corrections = [
        TideSeriesPoint(
            date_time=ts.replace(tzinfo=timezone.utc),
            value=convert_from_mgal(mgal, unit),
        )
        for ts, mgal in zip(timestamps, mgal_values)
    ]

    return TideBatchResponse(
        lat=body.lat,
        lon=body.lon,
        alt=body.alt,
        unit=unit,
        corrections=corrections,
    )
