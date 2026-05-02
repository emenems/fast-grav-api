"""Endpoints for gravity-network least-squares adjustment from CG-5 surveys."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.models import (
    AdjustmentResponse,
    AdjustmentSettings,
    DriftCoefficient,
    PairOut,
    StationOut,
)
from app.services.cg5_parser import parse_cg5
from app.services.gravity_adjustment import (
    AdjustmentResult,
    GravityMeasurement,
    adjust_survey,
    cg5_readings_to_measurements,
    normalize_station,
)
from app.units import GravityUnit, convert_from_mgal, convert_to_mgal

router = APIRouter(prefix="/adjustment", tags=["Network Adjustment"])

_BETA_NOTICE = (
    "**⚠️ Beta — interpret results with care.** This endpoint is new and has not "
    "yet been validated against an independent reference dataset across the full "
    "range of survey configurations. Output values, std errors, and the drift fit "
    "should be cross-checked before being used for any decision-making purpose."
)

_DESCRIPTION_COMMON = (
    f"{_BETA_NOTICE}\n\n"
    "Run a least-squares network adjustment on a relative-gravity survey "
    "(Scintrex CG-5). Each raw reading is reduced to its benchmark using the "
    "vertical gradient and sensor offset, a polynomial drift model is fitted, "
    "and absolute g per station plus pairwise Δg are returned with std errors.\n\n"
    "Method follows the Slovak SRGM 1.2.1 adjustment "
    "(Hefty et al., FCE STU Bratislava)."
)


def _normalize_settings_for_cg5(settings: AdjustmentSettings) -> AdjustmentSettings:
    """Normalise the reference-station ID so it matches the parser's output form.

    If the input is not parseable as a number it is passed through unchanged;
    `_validate_reference_station_present` will then surface a single, helpful
    "station X not in this file — here is what is" error.
    """
    try:
        ref = normalize_station(settings.reference_station)
    except (TypeError, ValueError):
        ref = settings.reference_station
    return settings.model_copy(update={"reference_station": ref})


def _validate_reference_station_present(
    measurements: list[GravityMeasurement],
    reference_station: str,
) -> None:
    available = sorted({m.station for m in measurements})
    if reference_station not in available:
        preview = ", ".join(available[:20])
        if len(available) > 20:
            preview += f", … (+{len(available) - 20} more)"
        raise HTTPException(
            status_code=422,
            detail=(
                f"`reference_station` {reference_station!r} is not present in the "
                f"uploaded survey. Stations found in the file: {preview}."
            ),
        )


def _to_response(
    result: AdjustmentResult,
    unit: GravityUnit,
) -> AdjustmentResponse:
    factor = convert_from_mgal(1.0, unit)

    drift = [
        DriftCoefficient(
            order=i,
            value=result.drift_coefficients[i] * factor,
            sigma=result.drift_sigma[i] * factor,
            unit=f"{unit.value}/h^{i}" if i > 0 else unit.value,
        )
        for i in range(len(result.drift_coefficients))
    ]

    return AdjustmentResponse(
        n_measurements=result.n_measurements,
        n_stations=result.n_stations,
        drift_degree=result.drift_degree,
        drift=drift,
        residual_min=result.residual_min * factor,
        residual_max=result.residual_max * factor,
        residuals=[r * factor for r in result.residuals],
        model_check=result.model_check,
        sigma0=None if result.sigma0 is None else result.sigma0 * factor,
        measurement_start=result.measurement_start,
        measurement_end=result.measurement_end,
        unit=unit,
        stations=[
            StationOut(
                station=s.station,
                delta_g=s.delta_g * factor,
                abs_g=s.abs_g * factor,
                sigma=s.sigma * factor,
            )
            for s in result.stations
        ],
        pairs=[
            PairOut(
                from_station=p.from_station,
                to_station=p.to_station,
                delta_g=p.delta_g * factor,
                sigma=p.sigma * factor,
            )
            for p in result.pairs
        ],
    )


def _run(
    measurements: list[GravityMeasurement],
    settings: AdjustmentSettings,
) -> AdjustmentResult:
    try:
        return adjust_survey(
            measurements,
            reference_station=settings.reference_station,
            reference_g=settings.reference_g,
            reference_sigma=settings.reference_sigma,
            gradient=settings.gradient,
            drift_degree=settings.drift_degree,
            height_unit_factor=settings.height_unit_factor,
            sensor_offset=settings.sensor_offset,
            use_apriori=settings.use_apriori,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/cg5/upload",
    response_model=AdjustmentResponse,
    summary="Adjust a CG-5 survey (file upload, beta)",
    description=_DESCRIPTION_COMMON
    + "\n\nUpload a Scintrex CG-5 survey file as `file` and supply the adjustment "
      "settings as form fields.",
)
async def adjust_cg5_upload(
    file: Annotated[
        UploadFile,
        File(description="Scintrex CG-5 raw survey text file (the `.txt` exported by the instrument)."),
    ],
    reference_station: Annotated[
        str,
        Form(
            description=(
                "ID of the benchmark whose absolute gravity is known (or fixed at 0). "
                "Must match a STATION value present in the uploaded file (CG-5 station "
                "IDs are normalised to four decimals — e.g. `692` matches `692.0000000`)."
            )
        ),
    ],
    reference_g: Annotated[
        float,
        Form(
            description=(
                "Absolute gravity at the reference station, in the same unit as the "
                "`unit` query parameter (default mGal). Used as the additive constant: "
                "every returned `abs_g` = reference_g + Δg. Leave at 0 to get pure Δg "
                "from the reference."
            )
        ),
    ] = 0.0,
    reference_sigma: Annotated[
        float,
        Form(
            description=(
                "1-σ standard error of `reference_g`, in the same unit as `unit` "
                "(default mGal). Propagated into every station's reported σ as "
                "sqrt(σ_Δg² + reference_sigma²). Leave at 0 if the tie value is "
                "treated as exact."
            )
        ),
    ] = 0.0,
    gradient: Annotated[
        float,
        Form(
            description=(
                "Vertical gravity gradient in **mGal/m** applied to every station. "
                "Used to reduce each raw reading down to the benchmark: "
                "g = g_raw + gradient · (height·height_unit_factor + sensor_offset). "
                "The free-air default is 0.3086 mGal/m."
            )
        ),
    ] = 0.3086,
    drift_degree: Annotated[
        int,
        Form(
            description=(
                "Polynomial degree of the gravimeter drift model fitted in time. "
                "0 = constant offset only, 1 = linear drift (typical for short loops), "
                "2 = quadratic (useful for >~4 h surveys with curvature). Maximum 5."
            )
        ),
    ] = 1,
    height_unit_factor: Annotated[
        float,
        Form(
            description=(
                "Multiplier that converts the CG-5 ALT field into **metres**. "
                "Pick one per the unit you entered into the instrument: "
                "0.01 if ALT was in cm, 0.001 if mm, 1.0 if m, 0.0254 if inches."
            )
        ),
    ] = 0.01,
    sensor_offset: Annotated[
        float,
        Form(
            description=(
                "Vertical offset of the sensing mass relative to the benchmark, in "
                "**metres**. Two CG-5 conventions: "
                "+0.089 if you entered the bottom-of-instrument-to-benchmark height "
                "(sensor is 0.089 m above that), "
                "-0.211 if you entered the top-of-instrument-to-benchmark height "
                "(sensor is 0.211 m below that)."
            )
        ),
    ] = 0.089,
    use_apriori: Annotated[
        bool,
        Form(
            description=(
                "Weighting mode. "
                "false (default): weighted least squares — each reading weighted by "
                "1/SD² from the CG-5 SD column. "
                "true: unit weights, with σ₀ estimated a posteriori from the residuals "
                "(use when SDs are unreliable)."
            )
        ),
    ] = False,
    unit: GravityUnit = Query(
        default=GravityUnit.mgal,
        description=(
            "Output unit for every gravity value in the response (Δg, abs_g, "
            "residuals, drift coefficients, σ). Choices: mgal, gal, ugal (µGal), "
            "nm_s2 (nm/s²), m_s2 (m/s², SI). "
            "1 mGal = 10⁻⁵ m/s² = 1000 µGal = 10000 nm/s²."
        ),
    ),
) -> AdjustmentResponse:
    if not (reference_station or "").strip():
        raise HTTPException(
            status_code=422,
            detail="`reference_station` is required and cannot be empty.",
        )

    # `reference_g` and `reference_sigma` arrive in the response unit but the
    # core adjustment works in mGal — convert here so internal arithmetic stays
    # consistent and `_to_response` can scale back uniformly.
    try:
        parsed = AdjustmentSettings(
            reference_station=reference_station,
            reference_g=convert_to_mgal(reference_g, unit),
            reference_sigma=convert_to_mgal(reference_sigma, unit),
            gradient=gradient,
            drift_degree=drift_degree,
            height_unit_factor=height_unit_factor,
            sensor_offset=sensor_offset,
            use_apriori=use_apriori,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not decode file: {exc}") from exc

    try:
        readings = parse_cg5(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    measurements = cg5_readings_to_measurements(readings)
    settings_norm = _normalize_settings_for_cg5(parsed)
    _validate_reference_station_present(measurements, settings_norm.reference_station)
    result = _run(measurements, settings_norm)
    return _to_response(result, unit)
