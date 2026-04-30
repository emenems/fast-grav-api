import asyncio
from typing import Any

import httpx

_BASE_URL = "https://zbgis.skgeodesy.sk"
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": _BASE_URL,
    "Referer": f"{_BASE_URL}/rts/sk/transform",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

_CRS: dict[str, tuple[str, str]] = {
    "jtsk": ("S-JTSK (JTSK03)", "ETRS89"),
    "etrs": ("ETRS89", "S-JTSK (JTSK03)"),
}

_PENDING = {"esriJobSubmitted", "esriJobExecuting"}
_MAX_POLLS = 5
_POLL_INTERVAL = 2.0


def _extract_coord(coord: dict[str, Any]) -> float:
    geocentric = coord.get("geocentricDec", "")
    if geocentric:
        return float(geocentric)
    return float(coord["value"].replace(",", ".").strip())


async def transform_sjtsk(x: float, y: float, mode: str) -> dict[str, Any]:
    """
    Transform a point between S-JTSK (JTSK03) and ETRS89 via the ZBGIS RTS API.

    mode='jtsk'  S-JTSK → ETRS89
    mode='etrs'  ETRS89 → S-JTSK

    Returns a dict with keys: job_id, status, x, y, message.
    Raises TimeoutError if the job doesn't finish within _MAX_POLLS seconds.
    Raises httpx.HTTPStatusError on non-2xx responses from the API.
    """
    input_crs, output_crs = _CRS[mode]

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        # Initialise session cookies
        await client.get(f"{_BASE_URL}/rts/sk/transform", headers=_HEADERS)

        # Submit job
        r = await client.post(
            f"{_BASE_URL}/rts/api/transform/start",
            headers=_HEADERS,
            files={
                "inputFormat": (None, "point"),
                "inputCoordinateSystem": (None, input_crs),
                "outputCoordinateSystem": (None, output_crs),
                "xCoordinate": (None, str(x)),
                "yCoordinate": (None, str(y)),
            },
        )
        r.raise_for_status()
        job_id: str = r.json()["response"]["jobId"]

        # Poll until complete
        for _ in range(_MAX_POLLS):
            poll = await client.get(
                f"{_BASE_URL}/rts/api/transform/check/{job_id}",
                headers=_HEADERS,
                params={
                    "transformType": "point",
                    "outputCRS": output_crs,
                    "isHighSystem": "false",
                },
            )
            poll.raise_for_status()
            data = poll.json()
            status: str = data["response"]["jobStatus"]

            if status not in _PENDING:
                coords = data.get("coords", [])
                return {
                    "job_id": data["response"]["jobId"],
                    "status": status,
                    "x": _extract_coord(coords[0]) if len(coords) > 0 else None,
                    "y": _extract_coord(coords[1]) if len(coords) > 1 else None,
                    "message": data.get("responseMessage"),
                }

            await asyncio.sleep(_POLL_INTERVAL)

    raise TimeoutError(f"Job {job_id} did not complete within {_MAX_POLLS} seconds")
