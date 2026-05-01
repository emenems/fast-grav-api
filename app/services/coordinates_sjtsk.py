from pyproj import Transformer

# EPSG:8352: S-JTSK [JTSK03] / Krovak
#   native axes: X = southing, Y = westing  (Czech/Slovak convention)
# EPSG:4258: ETRS89
#   native axes: lat, lon
# always_xy=False preserves native axis order, avoiding silent remapping.
_JTSK_TO_ETRS = Transformer.from_crs("EPSG:8352", "EPSG:4258", always_xy=False)
_ETRS_TO_JTSK = Transformer.from_crs("EPSG:4258", "EPSG:8352", always_xy=False)


def jtsk_to_etrs(x: float, y: float) -> tuple[float, float]:
    """S-JTSK (JTSK03) → ETRS89.

    Input follows the ZBGIS/Czech-Slovak convention:
      x = Y_westing, y = X_southing
    Returns (lat, lon).
    """
    lat, lon = _JTSK_TO_ETRS.transform(y, x)
    return lat, lon


def etrs_to_jtsk(lat: float, lon: float) -> tuple[float, float]:
    """ETRS89 → S-JTSK (JTSK03).

    Returns (x, y) in ZBGIS/Czech-Slovak convention:
      x = Y_westing, y = X_southing
    """
    X_southing, Y_westing = _ETRS_TO_JTSK.transform(lat, lon)
    return Y_westing, X_southing
