from fastapi import APIRouter

from app.models import TransformRequest, TransformResponse
from app.services.coordinates_sjtsk import etrs_to_jtsk, jtsk_to_etrs

router = APIRouter(prefix="/coordinates/transform", tags=["Coordinate Transformation"])


@router.post(
    "/sjtsk",
    response_model=TransformResponse,
    summary="Transform between S-JTSK (JTSK03) and ETRS89",
    description=(
        "Transform a single point between the Slovak S-JTSK (JTSK03) datum "
        "and ETRS89 computed locally via pyproj (EPSG:8352 ↔ EPSG:4258). "
        "No external API calls — response is instant.\n\n"
        "The response always includes all four coordinate fields (`x`, `y`, `lat`, `lon`): "
        "input values are echoed back alongside the computed output values.\n\n"
        "> **Precision note:** accuracy is approximately 5 mm. "
        "For surveying-grade results requiring sub-centimetre accuracy, use the "
        "[ZBGIS RTS API](https://zbgis.skgeodesy.sk/rts/sk/transform) directly — "
        "it applies the full Slovak national datum shift grid.\n\n"
        "---\n\n"
        '**S-JTSK (JTSK03) → ETRS89** (`mode: "jtsk"`) — Y-westing / X-southing in metres '
        "(Czech/Slovak `x`/`y` convention), returns ETRS89 geographic latitude/longitude:\n\n"
        "```json\n"
        '{"x": 524551.68, "y": 1214939.24, "mode": "jtsk"}\n'
        "```\n\n"
        '**ETRS89 → S-JTSK (JTSK03)** (`mode: "etrs"`) — geographic latitude/longitude '
        "in decimal degrees, returns S-JTSK Y-westing / X-southing in metres:\n\n"
        "```json\n"
        '{"lat": 48.776750281, "lon": 17.683095964, "mode": "etrs"}\n'
        "```"
    ),
)
def transform_sjtsk_endpoint(body: TransformRequest) -> TransformResponse:
    if body.mode == "jtsk":
        lat, lon = jtsk_to_etrs(body.x, body.y)
        return TransformResponse(mode="jtsk", x=body.x, y=body.y, lat=lat, lon=lon)
    x, y = etrs_to_jtsk(body.lat, body.lon)
    return TransformResponse(mode="etrs", x=x, y=y, lat=body.lat, lon=body.lon)
