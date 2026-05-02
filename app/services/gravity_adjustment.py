"""
Least-squares network adjustment for relative gravity surveys (Scintrex CG-5).

Port of the Slovak SRGM 1.2.1 adjustment (``VyrovnajZap.m`` by Hefty et al.).

Steps:
  1. Reduce raw reading to the benchmark via vertical gradient and sensor offset:
        g = g_raw + grad · (h · height_unit_factor + sensor_offset)
  2. Build the design matrix with one column per station (indicator) plus
     a polynomial drift model of degree ``drift_degree`` over time.
  3. Drop the reference station column (its Δg is fixed at 0), giving the
     reduced design matrix A of shape (n, k+p).
  4. Solve either:
       - weighted (uses each reading's σ), or
       - apriori (unit weights, sigma0 estimated post-fit).
  5. Recover Δg per station, absolute g, and pairwise Δg with std errors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np


_DEFAULT_GRADIENT = 0.3086  # mGal/m, free-air gradient


@dataclass(frozen=True)
class GravityMeasurement:
    """A single relative-gravity measurement at a benchmark."""

    station: str
    grav: float          # raw relative reading [mGal]
    sd: float            # measurement standard deviation [mGal]
    height: float        # sensor height entered into instrument
    timestamp: datetime


@dataclass(frozen=True)
class StationResult:
    station: str
    delta_g: float       # gravity difference relative to the reference [mGal]
    abs_g: float         # absolute gravity if a reference value was provided
    sigma: float         # std error of abs_g [mGal]


@dataclass(frozen=True)
class PairResult:
    from_station: str
    to_station: str
    delta_g: float       # mGal
    sigma: float         # mGal


@dataclass(frozen=True)
class AdjustmentResult:
    n_measurements: int
    n_stations: int
    drift_degree: int
    drift_coefficients: list[float]
    drift_sigma: list[float]
    residuals: list[float]
    residual_min: float
    residual_max: float
    model_check: float
    sigma0: float | None
    measurement_start: datetime
    measurement_end: datetime
    stations: list[StationResult]
    pairs: list[PairResult]


def adjust_survey(
    measurements: list[GravityMeasurement],
    *,
    reference_station: str,
    reference_g: float = 0.0,
    reference_sigma: float = 0.0,
    gradient: float | dict[str, float] = _DEFAULT_GRADIENT,
    default_gradient: float = _DEFAULT_GRADIENT,
    drift_degree: int = 1,
    height_unit_factor: float = 0.01,
    sensor_offset: float = 0.089,
    use_apriori: bool = False,
) -> AdjustmentResult:
    """
    Run the network adjustment.

    Parameters
    ----------
    measurements
        Time-ordered list of relative gravity measurements.
    reference_station
        Identifier of the benchmark whose absolute g is known.
    reference_g, reference_sigma
        Absolute g [mGal] and its std error at the reference station.
    gradient
        Either a scalar vertical gradient [mGal/m] applied to every station,
        or a dict ``{station: gradient}`` with ``default_gradient`` used as
        fallback for stations not present.
    drift_degree
        Polynomial degree of the gravimeter drift model (≥ 0).
    height_unit_factor
        Multiplier converting the instrument's height field to metres
        (cm → 0.01, mm → 0.001, m → 1.0, inch → 0.0254).
    sensor_offset
        Vertical offset of the sensor relative to the benchmark in metres
        (CG-5 from-bottom: 0.089 m, from-top: -0.211 m).
    use_apriori
        If True, solve with unit weights and estimate σ₀ from residuals.
        If False (default), weight each reading by its own σ.
    """
    if not measurements:
        raise ValueError("No measurements provided")
    if drift_degree < 0:
        raise ValueError("drift_degree must be non-negative")

    n = len(measurements)
    stations = [m.station for m in measurements]
    grav_r = np.array([m.grav for m in measurements], dtype=float)
    sd = np.array([m.sd for m in measurements], dtype=float)
    height = np.array([m.height for m in measurements], dtype=float)
    times = [m.timestamp for m in measurements]

    if isinstance(gradient, dict):
        grad = np.array(
            [float(gradient.get(s, default_gradient)) for s in stations], dtype=float
        )
    else:
        grad = np.full(n, float(gradient))

    grav = grav_r + grad * (height * height_unit_factor + sensor_offset)

    counts: dict[str, int] = {}
    for s in stations:
        counts[s] = counts.get(s, 0) + 1
    if reference_station not in counts:
        raise ValueError(
            f"Reference station '{reference_station}' has no measurements"
        )
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    unique = [s for s, _ in ordered if s != reference_station]
    unique = [reference_station] + unique
    k = len(unique)
    p = drift_degree

    if n <= k + p:
        raise ValueError(
            f"Insufficient measurements ({n}) for {k} stations and drift "
            f"degree {p}: need at least {k + p + 1}."
        )

    t0 = times[0]
    cas = np.array(
        [(t - t0).total_seconds() / 3600.0 for t in times], dtype=float
    )
    cas_centered = cas - cas.mean()

    AA = np.zeros((n, k + p + 1))
    col = {s: j for j, s in enumerate(unique)}
    for i, s in enumerate(stations):
        AA[i, col[s]] = 1.0
    AA[:, k] = 1.0
    for i in range(1, p + 1):
        AA[:, k + i] = cas_centered ** i

    A = AA[:, 1:]

    if use_apriori:
        ATA = A.T @ A
        theta = np.linalg.solve(ATA, A.T @ grav)
        res = A @ theta - grav
        dof = max(n - k - p - 1, 1)
        sigma0_val: float | None = float(math.sqrt(res @ res / dof))
        cov = (sigma0_val ** 2) * np.linalg.inv(ATA)
        ones = np.ones_like(theta)
        check = float((1.0 / sigma0_val ** 2) * grav @ A @ cov @ ones - ones @ theta)
    else:
        var = sd ** 2
        var = np.where(var == 0.0, np.finfo(float).eps, var)
        ATW = A.T / var
        ATWA = ATW @ A
        theta = np.linalg.solve(ATWA, ATW @ grav)
        res = A @ theta - grav
        cov = np.linalg.inv(ATWA)
        sigma0_val = None
        ones = np.ones_like(theta)
        check = float((grav / var) @ A @ cov @ ones - ones @ theta)

    kk = k - 1
    drift = theta[kk : kk + p + 1]
    drift_var = np.diag(cov[kk : kk + p + 1, kk : kk + p + 1])
    drift_sigma = np.sqrt(np.maximum(drift_var, 0.0))

    beta = theta[:kk]
    cov_beta = cov[:kk, :kk]

    station_results: list[StationResult] = [
        StationResult(
            station=reference_station,
            delta_g=0.0,
            abs_g=reference_g,
            sigma=reference_sigma,
        )
    ]
    for i, s in enumerate(unique[1:]):
        delta = float(beta[i])
        var_i = float(cov_beta[i, i])
        sigma = float(math.sqrt(max(var_i, 0.0) + reference_sigma ** 2))
        station_results.append(
            StationResult(
                station=s,
                delta_g=delta,
                abs_g=reference_g + delta,
                sigma=sigma,
            )
        )

    pairs: list[PairResult] = []
    for i in range(k):
        for j in range(i + 1, k):
            f = np.zeros(kk)
            if i > 0:
                f[i - 1] = -1.0
            if j > 0:
                f[j - 1] = 1.0
            d = float(f @ beta)
            sig = float(math.sqrt(max(f @ cov_beta @ f, 0.0)))
            pairs.append(
                PairResult(
                    from_station=unique[i],
                    to_station=unique[j],
                    delta_g=d,
                    sigma=sig,
                )
            )

    return AdjustmentResult(
        n_measurements=n,
        n_stations=k,
        drift_degree=p,
        drift_coefficients=drift.tolist(),
        drift_sigma=drift_sigma.tolist(),
        residuals=res.tolist(),
        residual_min=float(res.min()),
        residual_max=float(res.max()),
        model_check=check,
        sigma0=sigma0_val,
        measurement_start=times[0],
        measurement_end=times[-1],
        stations=station_results,
        pairs=pairs,
    )


def cg5_readings_to_measurements(
    readings,
    *,
    station_decimals: int = 4,
) -> list[GravityMeasurement]:
    """Convert ``CG5Reading`` rows to ``GravityMeasurement`` for the adjuster.

    Station IDs are normalised to a fixed-decimal string so float jitter in the
    raw file (e.g. ``51.2999992`` vs ``51.299999``) does not split a station.
    """
    out: list[GravityMeasurement] = []
    for r in readings:
        out.append(
            GravityMeasurement(
                station=f"{round(r.station, station_decimals):.{station_decimals}f}",
                grav=r.grav,
                sd=r.sd,
                height=r.alt,
                timestamp=r.timestamp,
            )
        )
    return out


def normalize_station(value: str | float, decimals: int = 4) -> str:
    """Normalise a user-provided station ID to the same string form as the parser."""
    return f"{round(float(value), decimals):.{decimals}f}"
