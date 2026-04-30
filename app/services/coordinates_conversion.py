import re

_DMS_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<sign>[+-])?                         # optional sign
    (?P<deg>\d+)\s*°\s*                     # degrees
    (?P<min>\d+)\s*['']\s*                  # minutes (' or ')
    (?P<sec>\d+(?:[.,]\d+)?)\s*[\\]?[""]?  # seconds, optional backslash + closing quote
    \s*$
    """,
    re.VERBOSE,
)


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_dms(value: str) -> float | None:
    """Parse a Degrees°Minutes'Seconds" string to decimal degrees."""
    value = _strip_outer_quotes(value.strip())
    m = _DMS_PATTERN.match(value.strip())
    if not m:
        return None
    sign = -1 if m.group("sign") == "-" else 1
    deg = float(m.group("deg"))
    minutes = float(m.group("min"))
    sec = float(m.group("sec").replace(",", "."))
    return sign * (deg + minutes / 60 + sec / 3600)


def parse_decimal(value: str) -> float | None:
    """Parse a plain decimal number (comma or dot separator)."""
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def convert_coordinate(value: str) -> float:
    """
    Convert a coordinate string to decimal degrees.

    Accepts DMS (48°46'36.301"), decimal-dot (48.77675), or decimal-comma (48,77675).
    Raises ValueError for unrecognisable input.
    """
    if "°" in value:
        result = parse_dms(value)
        if result is None:
            raise ValueError(f"Unrecognisable DMS format: '{value}'")
        return result

    result = parse_decimal(value)
    if result is not None:
        return result

    raise ValueError(f"Unrecognisable coordinate format: '{value}'")
