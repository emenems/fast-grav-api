import httpx
from fastapi import APIRouter, HTTPException
from typing import Union

from app.models import (
    AsyncTransformStatus,
    AsyncTransformSubmitted,
    EtrsToJtskResponse,
    JtskToEtrsResponse,
    TransformRequest,
    TransformResponse,
)
from app.services.zbgis import check_sjtsk_job, submit_sjtsk_job, transform_sjtsk

router = APIRouter(prefix="/coordinates/transform", tags=["Coordinate Transformation"])


@router.post(
    "/sjtsk",
    response_model=Union[JtskToEtrsResponse, EtrsToJtskResponse],
    summary="Transform between S-JTSK (JTSK03) and ETRS89",
    description=(
        "Transform a single point between the Slovak/Czech S-JTSK (JTSK03) datum "
        "and ETRS89 using the ZBGIS RTS API (zbgis.skgeodesy.sk).\n\n"
        "The endpoint delegates to an async job on the Slovak geodesy authority API and "
        "polls until the result is ready (max ~5 s); returns 504 if ZBGIS does not respond in time.\n\n"
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


@router.post(
    "/sjtsk/async",
    response_model=AsyncTransformSubmitted,
    status_code=202,
    summary="Submit an async S-JTSK ↔ ETRS89 transformation job",
    description=(
        "Submit a coordinate transformation job and return immediately with a `job_id`. "
        "Poll `GET /coordinates/transform/sjtsk/async/{job_id}` to retrieve the result.\n\n"
        "Accepts the same request body as `POST /coordinates/transform/sjtsk`."
    ),
)
async def submit_sjtsk_endpoint(body: TransformRequest) -> AsyncTransformSubmitted:
    coord1 = body.x if body.mode == "jtsk" else body.lat
    coord2 = body.y if body.mode == "jtsk" else body.lon

    try:
        result = await submit_sjtsk_job(coord1, coord2, body.mode)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API returned {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API unreachable: {exc}")

    return AsyncTransformSubmitted(**result)


@router.get(
    "/sjtsk/async/{job_id}",
    response_model=AsyncTransformStatus,
    summary="Poll an async S-JTSK ↔ ETRS89 transformation job",
    description=(
        "Check the status of a job submitted via `POST /coordinates/transform/sjtsk/async`.\n\n"
        "While the job is still running, `status` will be `esriJobExecuting`. "
        "When complete, `status` is `esriJobSucceeded` and the coordinate fields are populated."
    ),
)
async def check_sjtsk_endpoint(job_id: str) -> AsyncTransformStatus:
    try:
        result = await check_sjtsk_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API returned {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"ZBGIS API unreachable: {exc}")

    if result["mode"] == "jtsk":
        return AsyncTransformStatus(
            job_id=result["job_id"],
            status=result["status"],
            mode=result["mode"],
            lat=result["x"],
            lon=result["y"],
            message=result["message"],
        )
    return AsyncTransformStatus(
        job_id=result["job_id"],
        status=result["status"],
        mode=result["mode"],
        x=result["x"],
        y=result["y"],
        message=result["message"],
    )
