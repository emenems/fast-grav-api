"""
Vertical tidal gravity correction — Longman (1959).

Reference: I. M. Longman, "Formulas for Computing the Tidal Accelerations Due
to the Moon and the Sun", J. Geophys. Res., 64(12), 2351-2355, 1959.

Orbital constants follow Bartels (1957) as used in the Slovak geodetic
implementation.  Love-number amplitude factor 1.16 is from
Torge, Gravimetry, eqs. 3.28-3.29.
"""

import math
from datetime import datetime

# Julian centuries from J1900.0 (1899-12-31 12:00:00 UT)
# MJD of that epoch: JD 2415020.0 - 2400000.5 = 15019.5
_MJD_J1900 = 15019.5


def _mjd(dt: datetime) -> float:
    """Modified Julian Date for a naive UTC datetime (MJD = JD - 2400000.5)."""
    y, mo, d = dt.year, dt.month, dt.day
    h, mi = dt.hour, dt.minute
    sec = dt.second + dt.microsecond / 1e6

    a = (14 - mo) // 12
    yy = y + 4800 - a
    m = mo + 12 * a - 3
    jdn = d + (153 * m + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    jd = jdn + (h - 12) / 24.0 + mi / 1440.0 + sec / 86400.0
    return jd - 2400000.5


def solve_longman_tide(lat: float, lon: float, alt: float, dt: datetime) -> float:
    """
    Vertical tidal gravity correction [mGal] using Longman (1959).

    Parameters
    ----------
    lat : Latitude  [degrees, north positive]
    lon : Longitude [degrees, east positive]
    alt : Height above ellipsoid [m]
    dt  : Naive UTC datetime

    Returns
    -------
    Tidal correction [mGal], vertical component, Love-number corrected (x1.16).
    """
    DEG = math.pi / 180
    MINS = DEG / 60
    SECS = DEG / 3600
    rev = 2 * math.pi

    # Constants (Pettit 1954 / Schureman 1941 / Longman 1959)
    i = 5.145 * DEG  # (22) inclination of Moon's orbit to ecliptic
    omega = 23.452 * DEG  # (0)  obliquity of ecliptic
    G = 6.670e-11  # gravitational constant [m^3 kg^-1 s^-2]
    M = 7.3537e22  # mass of Moon [kg]
    S = 1.993e30  # mass of Sun [kg]
    m = 0.074804  # ratio of mean solar to lunar mean motion
    a = 6.378270e6  # equatorial radius of Earth [m]
    c1 = 1.495e11  # mean Earth-Sun distance [m]
    c = 3.84402e8  # mean Earth-Moon distance [m]
    e = 0.05490  # eccentricity of Moon's orbit

    # Observer position
    FI = lat * DEG
    LAMBDA = lon * DEG
    H = alt

    mjd = _mjd(dt)

    # Fractional UTC day (MJD epoch is midnight, so mod gives time-of-day directly)
    t0 = mjd % 1  # (24 prerequisite)

    # Greenwich hour angle of Sun, shifted to observer longitude
    t = 15 * DEG * 24 * (t0 - 0.5) + LAMBDA  # (24)

    # Julian centuries from J1900.0
    T = (mjd - _MJD_J1900) / 36525

    # Geocentric distance to observer (accounts for Earth's flattening)
    C = math.sqrt(1 / (1 + 0.006738 * math.sin(FI) ** 2))  # (34)
    r = C * a + H  # (33)

    # ── Orbital elements (Bartels 1957 coefficients, primed equations) ───────

    # Mean longitude of Moon from referred equinox
    s = (
        270 * DEG
        + 26 * MINS
        + 11.72 * SECS
        + (1336 * rev + 1108406.05 * SECS) * T
        + 7.128 * SECS * T**2
        + 0.0072 * SECS * T**3
    )  # (10')

    # Mean longitude of lunar perigee
    p = (
        334 * DEG
        + 19 * MINS
        + 46.42 * SECS
        + (11 * rev + 392522.51 * SECS) * T
        - 37.15 * SECS * T**2
        - 0.036 * SECS * T**3
    )  # (11')

    # Mean longitude of Sun
    h = 279 * DEG + 41 * MINS + 48.05 * SECS + 129602768.11 * SECS * T + 1.080 * SECS * T**2  # (12')

    # Longitude of ascending node of Moon's orbit on ecliptic
    N = (
        259 * DEG
        + 10 * MINS
        + 59.81 * SECS
        - (5 * rev + 482911.24 * SECS) * T
        + 7.48 * SECS * T**2
        + 0.007 * SECS * T**3
    )  # (19')

    # Mean longitude of solar perigee
    p1 = 281 * DEG + 13 * MINS + 14.99 * SECS + 6188.47 * SECS * T + 1.62 * SECS * T**2 + 0.011 * SECS * T**3  # (26')

    # Eccentricity of Earth's orbit around Sun
    e1 = 0.01675104 - 0.00004180 * T - 0.000000126 * T**2  # (27)

    # ── Distances ─────────────────────────────────────────────────────────────

    a_ = 1 / (c * (1 - e**2))  # (31)
    a1_ = 1 / (c1 * (1 - e1**2))  # (32)

    # Earth-Moon distance [m]
    d = 1 / (
        1 / c
        + a_ * e * math.cos(s - p)
        + a_ * e**2 * math.cos(2 * (s - p))
        + (15 / 8) * a_ * m * e * math.cos(s - 2 * h + p)
        + a_ * m**2 * math.cos(2 * (s - h))
    )  # (29)

    # Earth-Sun distance [m]
    D = 1 / (1 / c1 + a1_ * e1 * math.cos(h - p1))  # (30)

    # ── Derived orbital parameters ────────────────────────────────────────────

    # Inclination of Moon's orbit to equator
    I = math.acos(math.cos(omega) * math.cos(i) - math.sin(omega) * math.sin(i) * math.cos(N))  # (20)

    # Angle from ascending node A to vernal equinox (in equatorial plane)
    v = math.asin(math.sin(i) * math.sin(N) / math.sin(I))  # (21)

    # Auxiliary angle alpha relating node A to vernal equinox
    sin_alfa = math.sin(omega) * math.sin(N) / math.sin(I)  # (16)
    cos_alfa = math.cos(N) * math.cos(v) + math.sin(N) * math.sin(v) * math.cos(omega)  # (17)
    alfa = 2 * math.atan(sin_alfa / (1 + cos_alfa))  # (18)

    # Angle from ascending node A to referred equinox (in orbital plane)
    xi = N - alfa  # (14)

    # Mean argument of latitude of Moon (from node A, in orbital plane)
    sigma = s - xi  # (13)

    # True argument of latitude of Moon
    l = (
        sigma
        + 2 * e * math.sin(s - p)
        + (5 / 4) * e**2 * math.sin(2 * (s - p))
        + (15 / 4) * m * e * math.sin(s - 2 * h + p)
        + (11 / 8) * m**2 * math.sin(2 * (s - h))
    )  # (9)

    # Right ascension of observer's meridian measured from node A
    chi = t + h - v  # (23)

    # True longitude of Sun from vernal equinox
    l1 = h + 2 * e1 * math.sin(h - p1)  # (25)

    # Right ascension of observer's meridian from vernal equinox
    chi1 = t + h  # (28)

    # ── Zenith angles ─────────────────────────────────────────────────────────

    # Zenith angle of Moon (eq. 7)
    cos_theta = math.sin(FI) * math.sin(I) * math.sin(l) + math.cos(FI) * (
        math.cos(I / 2) ** 2 * math.cos(l - chi) + math.sin(I / 2) ** 2 * math.cos(l + chi)
    )
    theta = math.acos(max(-1.0, min(1.0, cos_theta)))

    # Zenith angle of Sun (eq. 8)
    cos_fi = math.sin(FI) * math.sin(omega) * math.sin(l1) + math.cos(FI) * (
        math.cos(omega / 2) ** 2 * math.cos(l1 - chi1) + math.sin(omega / 2) ** 2 * math.cos(l1 + chi1)
    )
    fi = math.acos(max(-1.0, min(1.0, cos_fi)))

    # ── Tidal accelerations ───────────────────────────────────────────────────

    # Vertical Moon tide [m/s^2]  (eq. 1)
    gm = (G * M * r / d**3) * (3 * math.cos(theta) ** 2 - 1) + 1.5 * (G * M * r**2 / d**4) * (
        5 * math.cos(theta) ** 3 - 3 * math.cos(theta)
    )

    # Vertical Sun tide [m/s^2]  (eq. 3)
    gs = (G * S * r / D**3) * (3 * math.cos(fi) ** 2 - 1)

    # Total, Love-number corrected (x1.16), converted to mGal (x1e5)  (eq. 5)
    return 1.16 * (gm + gs) * 1e5
