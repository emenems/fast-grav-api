from fastapi import APIRouter, HTTPException, Query

from app.models import CoordinateConvertRequest, CoordinateConvertResponse, CoordinateResult
from app.services.coordinates_conversion import convert_coordinate

router = APIRouter(prefix="/coordinates/convert", tags=["Coordinate Conversion"])


@router.post(
    "/to-decimal",
    response_model=CoordinateConvertResponse,
    summary="Parse coordinates to decimal degrees",
    description=(
        "Parse coordinate strings to decimal degrees.\n\n"
        "**Supported formats:**\n"
        "- DMS with degree symbol: `48°46'36.30101\"` or `48°46'36,30101\"`\n"
        "- Decimal with dot: `48.77675`\n"
        "- Decimal with comma: `48,77675`\n"
        "- Signed/negative values: `-48°46'36\"` or `-48,77675`\n\n"
        "Multiple values can be submitted in a single request. "
        "Use `decimals` to control the precision of the returned values (default 10)."
    ),
)
async def to_decimal(
    body: CoordinateConvertRequest,
    decimals: int = Query(default=10, ge=0, le=15, description="Number of decimal places to round to"),
) -> CoordinateConvertResponse:
    results: list[CoordinateResult] = []
    errors: list[str] = []

    for value in body.values:
        try:
            raw = convert_coordinate(value)
            results.append(CoordinateResult(input=value, decimal=round(raw, decimals)))
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    return CoordinateConvertResponse(results=results)
