"""Tests for S-JTSK ↔ ETRS89 transformation service and /transform/sjtsk endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.coordinates_sjtsk import etrs_to_jtsk, jtsk_to_etrs

client = TestClient(app)

URL = "/coordinates/transform/sjtsk"

# Reference point validated against ZBGIS RTS API
_JTSK_X = 524551.68
_JTSK_Y = 1214939.24
_ETRS_LAT = 48.776750281
_ETRS_LON = 17.683095964
_PREC_DEG = 1e-4   # ~11 m in latitude — well above pyproj's ~5 mm accuracy
_PREC_M = 0.02     # 2 cm — covers single-direction (~5 mm) and roundtrip (~1 cm) error


# ── service ───────────────────────────────────────────────────────────────────


class TestSjtskService:
    def test_jtsk_to_etrs_lat(self):
        lat, _ = jtsk_to_etrs(_JTSK_X, _JTSK_Y)
        assert lat == pytest.approx(_ETRS_LAT, abs=_PREC_DEG)

    def test_jtsk_to_etrs_lon(self):
        _, lon = jtsk_to_etrs(_JTSK_X, _JTSK_Y)
        assert lon == pytest.approx(_ETRS_LON, abs=_PREC_DEG)

    def test_etrs_to_jtsk_x(self):
        x, _ = etrs_to_jtsk(_ETRS_LAT, _ETRS_LON)
        assert x == pytest.approx(_JTSK_X, abs=_PREC_M)

    def test_etrs_to_jtsk_y(self):
        _, y = etrs_to_jtsk(_ETRS_LAT, _ETRS_LON)
        assert y == pytest.approx(_JTSK_Y, abs=_PREC_M)

    def test_roundtrip_jtsk_to_etrs_to_jtsk(self):
        lat, lon = jtsk_to_etrs(_JTSK_X, _JTSK_Y)
        x, y = etrs_to_jtsk(lat, lon)
        assert x == pytest.approx(_JTSK_X, abs=_PREC_M)
        assert y == pytest.approx(_JTSK_Y, abs=_PREC_M)


# ── endpoint ──────────────────────────────────────────────────────────────────


class TestTransformEndpoint:
    def test_jtsk_to_etrs_status(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "jtsk"})
        assert r.status_code == 200

    def test_jtsk_to_etrs_mode(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "jtsk"})
        assert r.json()["mode"] == "jtsk"

    def test_jtsk_to_etrs_echoes_input(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "jtsk"})
        body = r.json()
        assert body["x"] == pytest.approx(_JTSK_X)
        assert body["y"] == pytest.approx(_JTSK_Y)

    def test_jtsk_to_etrs_computed_output(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "jtsk"})
        body = r.json()
        assert body["lat"] == pytest.approx(_ETRS_LAT, abs=_PREC_DEG)
        assert body["lon"] == pytest.approx(_ETRS_LON, abs=_PREC_DEG)

    def test_jtsk_to_etrs_all_fields_present(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "jtsk"})
        body = r.json()
        assert all(k in body for k in ("mode", "x", "y", "lat", "lon"))

    def test_etrs_to_jtsk_status(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": _ETRS_LON, "mode": "etrs"})
        assert r.status_code == 200

    def test_etrs_to_jtsk_mode(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": _ETRS_LON, "mode": "etrs"})
        assert r.json()["mode"] == "etrs"

    def test_etrs_to_jtsk_echoes_input(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": _ETRS_LON, "mode": "etrs"})
        body = r.json()
        assert body["lat"] == pytest.approx(_ETRS_LAT)
        assert body["lon"] == pytest.approx(_ETRS_LON)

    def test_etrs_to_jtsk_computed_output(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": _ETRS_LON, "mode": "etrs"})
        body = r.json()
        assert body["x"] == pytest.approx(_JTSK_X, abs=_PREC_M)
        assert body["y"] == pytest.approx(_JTSK_Y, abs=_PREC_M)

    def test_etrs_to_jtsk_all_fields_present(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": _ETRS_LON, "mode": "etrs"})
        body = r.json()
        assert all(k in body for k in ("mode", "x", "y", "lat", "lon"))

    def test_invalid_mode_returns_422(self):
        r = client.post(URL, json={"x": _JTSK_X, "y": _JTSK_Y, "mode": "wgs84"})
        assert r.status_code == 422

    def test_missing_x_returns_422(self):
        r = client.post(URL, json={"y": _JTSK_Y, "mode": "jtsk"})
        assert r.status_code == 422

    def test_missing_body_returns_422(self):
        r = client.post(URL)
        assert r.status_code == 422

    def test_lat_out_of_range_returns_422(self):
        r = client.post(URL, json={"lat": 91.0, "lon": _ETRS_LON, "mode": "etrs"})
        assert r.status_code == 422

    def test_lon_out_of_range_returns_422(self):
        r = client.post(URL, json={"lat": _ETRS_LAT, "lon": 181.0, "mode": "etrs"})
        assert r.status_code == 422
