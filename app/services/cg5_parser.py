"""
Parser for Scintrex CG-5 raw survey text files.

The CG-5 raw text format begins with a banner of metadata lines starting with
``/`` followed by space-separated measurement rows of fixed columns:

    LINE STATION ALT GRAV SD TILTX TILTY TEMP TIDE DUR REJ TIME DEC.TIME+DATE TERRAIN DATE

Header (``/``-prefixed) and blank lines are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CG5Reading:
    """A single measurement row from a CG-5 survey file."""

    line: float
    station: float
    alt: float          # height in CG-5 height field (instrument unit, typically cm)
    grav: float         # raw relative gravity reading [mGal]
    sd: float           # standard deviation of reading [mGal]
    tiltx: float
    tilty: float
    temp: float
    tide: float
    dur: int
    rej: int
    timestamp: datetime
    terrain: float


def parse_cg5(text: str) -> list[CG5Reading]:
    """Parse the text of a Scintrex CG-5 survey file into a list of readings."""
    readings: list[CG5Reading] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("/") or line.startswith("\\"):
            continue
        parts = line.split()
        if len(parts) < 15:
            continue
        try:
            ts = _parse_dt(parts[11], parts[14])
            reading = CG5Reading(
                line=float(parts[0]),
                station=float(parts[1]),
                alt=float(parts[2]),
                grav=float(parts[3]),
                sd=float(parts[4]),
                tiltx=float(parts[5]),
                tilty=float(parts[6]),
                temp=float(parts[7]),
                tide=float(parts[8]),
                dur=int(float(parts[9])),
                rej=int(float(parts[10])),
                timestamp=ts,
                terrain=float(parts[13]),
            )
        except (ValueError, IndexError):
            continue
        readings.append(reading)
    if not readings:
        raise ValueError("No CG-5 measurement rows found in input")
    return readings


def _parse_dt(time_str: str, date_str: str) -> datetime:
    h, m, s = time_str.split(":")
    y, mo, d = date_str.split("/")
    return datetime(int(y), int(mo), int(d), int(h), int(m), int(s))
