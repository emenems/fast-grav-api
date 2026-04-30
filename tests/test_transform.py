"""Tests for S-JTSK ↔ ETRS89 transformation service and /transform/sjtsk endpoint."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.zbgis import _extract_coord

client = TestClient(app)

URL = "/coordinates/transform/sjtsk"

# ── Shared fixtures ───────────────────────────────────────────────────────────

_JOB_ID = "j_test_abc123"

_START_OK: dict[str, Any] = {"response": {"jobId": _JOB_ID}}

_POLL_EXECUTING: dict[str, Any] = {
    "response": {"jobId": _JOB_ID, "jobStatus": "esriJobExecuting"},
}

_POLL_SUCCEEDED_ETRS: dict[str, Any] = {
    "response": {"jobId": _JOB_ID, "jobStatus": "esriJobSucceeded"},
    "coords": [
        {"geocentricDec": "48.776750281"},
        {"geocentricDec": "17.683095964"},
    ],
    "responseMessage": "Transformácia prebehla úspešne",
}

_POLL_SUCCEEDED_JTSK: dict[str, Any] = {
    "response": {"jobId": _JOB_ID, "jobStatus": "esriJobSucceeded"},
    "coords": [
        {"geocentricDec": "", "value": "524551,680"},
        {"geocentricDec": "", "value": "1214939,240"},
    ],
    "responseMessage": "Transformácia prebehla úspešne",
}

_POLL_FAILED: dict[str, Any] = {
    "response": {"jobId": _JOB_ID, "jobStatus": "esriJobFailed"},
    "responseMessage": "Chyba transformácie",
}


def _resp(data: Any) -> MagicMock:
    """Build a mock httpx response."""
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


def _patch_client(get_responses: list[Any], post_response: Any):
    """Context manager that replaces httpx.AsyncClient with a controlled mock."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[_resp(r) for r in get_responses])
    mock_client.post = AsyncMock(return_value=_resp(post_response))

    patcher = patch("app.services.zbgis.httpx.AsyncClient")

    class _Ctx:
        def __enter__(self):
            MockClass = patcher.__enter__()
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=mock_client)
            instance.__aexit__ = AsyncMock(return_value=None)
            MockClass.return_value = instance
            return mock_client

        def __exit__(self, *args):
            patcher.__exit__(*args)

    return _Ctx()


# ── _extract_coord ────────────────────────────────────────────────────────────


class TestExtractCoord:
    def test_geocentric_dec_used_when_present(self):
        assert _extract_coord({"geocentricDec": "48.776750281"}) == pytest.approx(48.776750281)

    def test_value_field_used_when_geocentric_empty(self):
        assert _extract_coord({"geocentricDec": "", "value": "524551,680"}) == pytest.approx(524551.68)

    def test_value_field_used_when_geocentric_missing(self):
        assert _extract_coord({"value": "1214939,240"}) == pytest.approx(1214939.24)

    def test_comma_replaced_with_dot(self):
        assert _extract_coord({"value": "524551,680"}) == pytest.approx(524551.68)

    def test_returns_float(self):
        assert isinstance(_extract_coord({"geocentricDec": "48.0"}), float)


# ── zbgis service (via mocked httpx) ─────────────────────────────────────────


class TestZbgisService:
    async def test_jtsk_to_etrs_success(self):
        from app.services.zbgis import transform_sjtsk

        with _patch_client(
            get_responses=[None, _POLL_SUCCEEDED_ETRS],
            post_response=_START_OK,
        ):
            result = await transform_sjtsk(524551.68, 1214939.24, "jtsk")

        assert result["status"] == "esriJobSucceeded"
        assert result["x"] == pytest.approx(48.776750281)
        assert result["y"] == pytest.approx(17.683095964)
        assert result["job_id"] == _JOB_ID

    async def test_etrs_to_jtsk_success(self):
        from app.services.zbgis import transform_sjtsk

        with _patch_client(
            get_responses=[None, _POLL_SUCCEEDED_JTSK],
            post_response=_START_OK,
        ):
            result = await transform_sjtsk(48.776750281, 17.683095964, "etrs")

        assert result["status"] == "esriJobSucceeded"
        assert result["x"] == pytest.approx(524551.68)
        assert result["y"] == pytest.approx(1214939.24)

    async def test_polls_through_executing_status(self):
        from app.services.zbgis import transform_sjtsk

        with patch("app.services.zbgis._POLL_INTERVAL", 0):
            with _patch_client(
                get_responses=[None, _POLL_EXECUTING, _POLL_EXECUTING, _POLL_SUCCEEDED_ETRS],
                post_response=_START_OK,
            ):
                result = await transform_sjtsk(524551.68, 1214939.24, "jtsk")

        assert result["status"] == "esriJobSucceeded"

    async def test_timeout_when_max_polls_exceeded(self):
        from app.services import zbgis
        from app.services.zbgis import transform_sjtsk

        with patch.object(zbgis, "_MAX_POLLS", 2), patch("app.services.zbgis._POLL_INTERVAL", 0):
            with _patch_client(
                get_responses=[None, _POLL_EXECUTING, _POLL_EXECUTING],
                post_response=_START_OK,
            ):
                with pytest.raises(TimeoutError):
                    await transform_sjtsk(524551.68, 1214939.24, "jtsk")

    async def test_coords_none_when_missing(self):
        from app.services.zbgis import transform_sjtsk

        poll_no_coords = {
            "response": {"jobId": _JOB_ID, "jobStatus": "esriJobSucceeded"},
            "responseMessage": "ok",
        }
        with _patch_client(get_responses=[None, poll_no_coords], post_response=_START_OK):
            result = await transform_sjtsk(0.0, 0.0, "jtsk")

        assert result["x"] is None
        assert result["y"] is None


# ── /transform/sjtsk endpoint ────────────────────────────────────────────────


class TestTransformEndpoint:
    def _mock_service(self, return_value: dict[str, Any] | None = None, side_effect=None):
        mock = AsyncMock(return_value=return_value, side_effect=side_effect)
        return patch("app.routers.tranformation.transform_sjtsk", mock)

    def test_jtsk_to_etrs_200(self):
        service_result = {
            "job_id": _JOB_ID,
            "status": "esriJobSucceeded",
            "x": 48.776750281,
            "y": 17.683095964,
            "message": "Transformácia prebehla úspešne",
        }
        with self._mock_service(service_result):
            r = client.post(URL, json={"x": 524551.68, "y": 1214939.24, "mode": "jtsk"})

        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "jtsk"
        assert body["lat"] == pytest.approx(48.776750281)
        assert body["lon"] == pytest.approx(17.683095964)
        assert body["job_id"] == _JOB_ID

    def test_etrs_to_jtsk_200(self):
        service_result = {
            "job_id": _JOB_ID,
            "status": "esriJobSucceeded",
            "x": 524551.68,
            "y": 1214939.24,
            "message": "Transformácia prebehla úspešne",
        }
        with self._mock_service(service_result):
            r = client.post(URL, json={"lat": 48.776750281, "lon": 17.683095964, "mode": "etrs"})

        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "etrs"
        assert body["x"] == pytest.approx(524551.68)
        assert body["y"] == pytest.approx(1214939.24)

    def test_job_failed_returns_502(self):
        service_result = {
            "job_id": _JOB_ID,
            "status": "esriJobFailed",
            "x": None,
            "y": None,
            "message": "Chyba transformácie",
        }
        with self._mock_service(service_result):
            r = client.post(URL, json={"x": 0.0, "y": 0.0, "mode": "jtsk"})

        assert r.status_code == 502

    def test_timeout_returns_504(self):
        with self._mock_service(side_effect=TimeoutError("timed out")):
            r = client.post(URL, json={"x": 524551.68, "y": 1214939.24, "mode": "jtsk"})

        assert r.status_code == 504

    def test_http_error_returns_502(self):
        exc = httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock(status_code=500))
        with self._mock_service(side_effect=exc):
            r = client.post(URL, json={"x": 524551.68, "y": 1214939.24, "mode": "jtsk"})

        assert r.status_code == 502

    def test_network_error_returns_502(self):
        with self._mock_service(side_effect=httpx.ConnectError("unreachable")):
            r = client.post(URL, json={"x": 524551.68, "y": 1214939.24, "mode": "jtsk"})

        assert r.status_code == 502

    def test_invalid_mode_returns_422(self):
        r = client.post(URL, json={"x": 524551.68, "y": 1214939.24, "mode": "wgs84"})
        assert r.status_code == 422

    def test_missing_x_returns_422(self):
        r = client.post(URL, json={"y": 1214939.24, "mode": "jtsk"})
        assert r.status_code == 422

    def test_missing_body_returns_422(self):
        r = client.post(URL)
        assert r.status_code == 422
