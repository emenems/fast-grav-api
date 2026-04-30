import httpx
from fastapi import APIRouter, HTTPException
from typing import Union

from app.models import (
    EtrsToJtskResponse,
    JtskToEtrsResponse,
    TransformRequest,
    TransformResponse,
)
from app.services.zbgis import transform_sjtsk

router = APIRouter(prefix="/coordinates/transform", tags=["Coordinate Transformation"])


@router.post(
    "/sjtsk",
    response_model=Union[JtskToEtrsResponse, EtrsToJtskResponse],
    summary="Transform between S-JTSK (JTSK03) and ETRS89",
    description=(
        "Transform a single point between the Slovak/Czech S-JTSK (JTSK03) datum "
        "and ETRS89 using the ZBGIS RTS API (zbgis.skgeodesy.sk).\n\n"
        "The endpoint delegates to an async job on the Slovak geodesy authority API and "
        "polls until the result is ready. Typical response time is 1–3 seconds.\n\n"
        "---\n\n"
        "**S-JTSK (JTSK03) → ETRS89** (`mode: \"jtsk\"`) — northing/easting in metres, "
        "returns ETRS89 geographic latitude/longitude:\n\n"
        "```json\n"
        '{"x": 524551.68, "y": 1214939.24, "mode": "jtsk"}\n'
        "```\n\n"
        "**ETRS89 → S-JTSK (JTSK03)** (`mode: \"etrs\"`) — geographic latitude/longitude in decimal degrees, "
        "returns S-JTSK northing/easting in metres:\n\n"
        "```json\n"
        '{"lat": 48.776750281, "lon": 17.683095964, "mode": "etrs"}\n'
        "```"
    ),
)
async def transform_sjtsk_endpoint(body: TransformRequest) -> TransformResponse:
    coord1 = body.x if body.mode == "jtsk" else body.lat
    coord2 = body.y if body.mode == "jtsk" else body.lon

    try:
        result = await transform_sjtsk(coord1, coord2, body.mode)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API returned {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API unreachable: {exc}")

    if result["status"] != "esriJobSucceeded":
        raise HTTPException(
            status_code=502,
            detail=f"Transformation failed: {result.get('message') or result['status']}",
        )

    if body.mode == "jtsk":
        return JtskToEtrsResponse(
            mode="jtsk",
            job_id=result["job_id"],
            status=result["status"],
            lat=result["x"],
            lon=result["y"],
            message=result["message"],
        )
    return EtrsToJtskResponse(
        mode="etrs",
        job_id=result["job_id"],
        status=result["status"],
        x=result["x"],
        y=result["y"],
        message=result["message"],
    )
