import asyncio
from datetime import datetime, timezone
from functools import partial

from fastapi import APIRouter, HTTPException, Query

from app.services.tides_longman import solve_longman_tide
from app.models import TideRequest, TideResponse, TidePoint
from app.units import GravityUnit, convert_from_mgal

router = APIRouter(prefix="/tides", tags=["Tidal Corrections"])


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _compute(lat: float, lon: float, alt: float, timestamps: list[datetime]) -> list[float]:
    return [solve_longman_tide(lat, lon, alt, t) for t in timestamps]


@router.post(
    "/corrections",
    response_model=TideResponse,
    summary="Tidal gravity corrections (Longman 1959)",
    description=(
        "Compute vertical tidal gravity corrections at a fixed location for a list of UTC datetimes.\n\n"
        "**Method:** Longman (1959) — *Formulas for Computing the Tidal Accelerations Due to the Moon "
        "and the Sun*, J. Geophys. Res., 64(12), 2351–2355. "
        "Orbital constants follow Bartels (1957). "
        "The Love-number amplitude factor of 1.16 (Torge, *Gravimetry*, eqs. 3.28–3.29) is applied "
        "to account for Earth's elastic deformation.\n\n"
        "**Output:** vertical component of the combined lunar and solar tidal acceleration. "
        "Positive values indicate the tide increases observed gravity; negative values indicate a reduction.\n\n"
        "Pass a single-element list for a one-off correction. Maximum 10 000 timestamps per request."
    ),
)
async def tide_corrections(
    body: TideRequest,
    unit: GravityUnit = Query(default=GravityUnit.mgal, description="Output unit for the correction values"),
) -> TideResponse:
    timestamps = [_naive_utc(dt) for dt in body.date_times]

    loop = asyncio.get_running_loop()
    try:
        mgal_values = await loop.run_in_executor(
            None,
            partial(_compute, body.lat, body.lon, body.alt, timestamps),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TideResponse(
        lat=body.lat,
        lon=body.lon,
        alt=body.alt,
        unit=unit,
        corrections=[
            TidePoint(
                date_time=ts.replace(tzinfo=timezone.utc),
                value=convert_from_mgal(mgal, unit),
            )
            for ts, mgal in zip(timestamps, mgal_values)
        ],
    )
