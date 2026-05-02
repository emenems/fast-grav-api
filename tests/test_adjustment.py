"""
Tests for the gravity-network adjustment service and CG-5 parser.

Uses the bundled sample survey ``Dubnik_jesen_SIET_201709.txt`` and its
reference output from the SRGM 1.2.1 Matlab implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cg5_parser import parse_cg5
from app.services.gravity_adjustment import (
    adjust_survey,
    cg5_readings_to_measurements,
    normalize_station,
)

SAMPLE_FILE = Path(__file__).resolve().parents[1] / "SRGM_1.2.1" / "Dubnik_jesen_SIET_201709.txt"


@pytest.fixture(scope="module")
def cg5_text() -> str:
    return SAMPLE_FILE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def measurements(cg5_text):
    readings = parse_cg5(cg5_text)
    return cg5_readings_to_measurements(readings)


# ── parser ──────────────────────────────────────────────────────────────────


class TestParseCG5:
    def test_row_count_matches_matlab(self, cg5_text):
        # The bundled survey contains 100 measurement rows.
        assert len(parse_cg5(cg5_text)) == 100

    def test_first_row(self, cg5_text):
        first = parse_cg5(cg5_text)[0]
        assert first.station == pytest.approx(692.0)
        assert first.grav == pytest.approx(7148.650)
        assert first.sd == pytest.approx(0.012)
        assert first.alt == pytest.approx(59.1)
        assert first.timestamp.year == 2017
        assert first.timestamp.hour == 8
        assert first.timestamp.minute == 49

    def test_skip_blank_input(self):
        with pytest.raises(ValueError):
            parse_cg5("/ header only\n\n")


# ── adjustment ──────────────────────────────────────────────────────────────


class TestAdjustSurvey:
    """
    Reference values from the bundled
    ``VYROVNANIE_Dubnik_jesen_SIET_201709.txt`` (SRGM 1.2.1).

    The reference run used: drift degree 2, reference station = 692
    (with absolute g = 0 → reported abs_g equals Δg from reference),
    gradient = 0.3086 mGal/m, and the CG-5 "from-top" sensor offset of
    -0.211 m (the survey entered benchmark-to-instrument-top heights).
    """

    REF = "692"
    DRIFT_DEG = 2
    SENSOR_OFFSET = -0.211
    EXPECTED_DELTAS = {
        "692": 0.0,
        "3552.0100": 3.4634,
        "1.1000": -41.6212,
        "7.1000": -4.3076,
        "8.1000": 0.1935,
        "12.1000": 2.6511,
        "26.1000": -2.2575,
        "42.1000": -3.3628,
        "43.1000": -2.7951,  # contains a high-rejection outlier reading
        "51.1000": 20.7717,
        "51.3000": -0.0143,
        "706": 0.3764,
        "3513.1003": -42.0701,
    }

    def _adjust(self, measurements, **overrides):
        kwargs = dict(
            reference_station=normalize_station(self.REF),
            drift_degree=self.DRIFT_DEG,
            sensor_offset=self.SENSOR_OFFSET,
        )
        kwargs.update(overrides)
        return adjust_survey(measurements, **kwargs)

    def test_basic_shape(self, measurements):
        result = self._adjust(measurements)
        assert result.n_measurements == 100
        assert result.n_stations == 13
        assert result.drift_degree == 2
        assert len(result.drift_coefficients) == 3

    def test_drift_coefficients_match_reference(self, measurements):
        # Reference: c0 ≈ 7148.7997, c1 ≈ 0.0054, c2 ≈ -0.0017 mGal/h^i
        result = self._adjust(measurements)
        c0, c1, c2 = result.drift_coefficients
        assert c0 == pytest.approx(7148.7997, abs=1e-3)
        assert c1 == pytest.approx(0.0054, abs=1e-3)
        assert c2 == pytest.approx(-0.0017, abs=1e-3)

    def test_station_deltas_match_reference(self, measurements):
        result = self._adjust(measurements)
        by_station = {normalize_station(s.station): s for s in result.stations}
        for raw, expected in self.EXPECTED_DELTAS.items():
            key = normalize_station(raw)
            assert key in by_station, f"missing station {key}"
            got = by_station[key].delta_g
            # Loose tolerance for one station containing a heavily
            # downweighted outlier reading; tight for the rest.
            tol = 1e-2 if raw == "43.1000" else 2e-3
            assert got == pytest.approx(expected, abs=tol), (
                f"station {raw}: got {got:.4f}, expected {expected:.4f}"
            )

    def test_residual_max_in_expected_range(self, measurements):
        # Reference: max residual ≈ 0.0113 mGal at station 3552.01
        result = self._adjust(measurements)
        assert result.residual_max == pytest.approx(0.0113, abs=2e-3)

    def test_model_check_near_zero(self, measurements):
        result = self._adjust(measurements)
        assert abs(result.model_check) < 1e-6

    def test_pairs_count(self, measurements):
        result = self._adjust(measurements)
        # 13 stations → C(13, 2) = 78 unique pairs
        assert len(result.pairs) == 78

    def test_pair_consistency_with_station_deltas(self, measurements):
        # For any pair (a, b) in the output, Δg(a→b) must equal Δg(b) - Δg(a)
        result = self._adjust(measurements)
        deltas = {s.station: s.delta_g for s in result.stations}
        for p in result.pairs:
            expected = deltas[p.to_station] - deltas[p.from_station]
            assert p.delta_g == pytest.approx(expected, abs=1e-9)

    def test_absolute_g_uses_reference(self, measurements):
        result = self._adjust(measurements, reference_g=987000.0)
        ref_row = next(s for s in result.stations if s.station == normalize_station(self.REF))
        assert ref_row.abs_g == 987000.0
        for s in result.stations:
            assert s.abs_g == pytest.approx(987000.0 + s.delta_g, abs=1e-9)

    def test_apriori_mode_runs(self, measurements):
        result = self._adjust(measurements, use_apriori=True)
        assert result.sigma0 is not None and result.sigma0 > 0

    def test_rejects_unknown_reference(self, measurements):
        with pytest.raises(ValueError, match="(?i)reference"):
            adjust_survey(
                measurements,
                reference_station="does-not-exist",
                drift_degree=1,
            )

    def test_rejects_too_few_measurements(self):
        from datetime import datetime as _dt

        from app.services.gravity_adjustment import GravityMeasurement
        only_one = [
            GravityMeasurement(
                station="A", grav=1.0, sd=0.01, height=0.0, timestamp=_dt(2020, 1, 1)
            )
        ]
        with pytest.raises(ValueError, match="Insufficient"):
            adjust_survey(only_one, reference_station="A", drift_degree=1)


# ── HTTP layer ──────────────────────────────────────────────────────────────


class TestAdjustmentEndpoints:
    def test_json_endpoint_is_removed(self):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5",
            json={"cg5_content": "ignored", "settings": {"reference_station": "1"}},
        )
        assert resp.status_code == 404

    def test_upload_endpoint_returns_full_response(self, cg5_text):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={
                "reference_station": "692",
                "drift_degree": "2",
                "sensor_offset": "-0.211",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["n_measurements"] == 100
        assert data["n_stations"] == 13
        assert len(data["pairs"]) == 78
        ref_row = next(s for s in data["stations"] if s["station"] == "692.0000")
        assert ref_row["delta_g"] == 0.0

    def test_upload_endpoint_with_form_settings(self, cg5_text):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={
                "reference_station": "692",
                "drift_degree": "2",
                "sensor_offset": "-0.211",
                "use_apriori": "false",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["n_measurements"] == 100
        assert data["unit"] == "mgal"

    def test_upload_endpoint_reference_g_in_request_unit(self, cg5_text):
        # reference_g is supplied in the same unit as `unit` (here m/s²).
        # The reference-station abs_g must round-trip back to that exact value.
        client = TestClient(app)
        ref_g_si = 9.80888292
        resp = client.post(
            "/adjustment/cg5/upload?unit=m_s2",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={
                "reference_station": "692",
                "reference_g": str(ref_g_si),
                "drift_degree": "2",
                "sensor_offset": "-0.211",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        ref_row = next(s for s in data["stations"] if s["station"] == "692.0000")
        assert ref_row["abs_g"] == pytest.approx(ref_g_si, rel=1e-12)
        # Δg from the matlab reference for station 3552.01 is +3.4634 mGal
        # = 3.4634e-5 m/s². Therefore abs_g(3552.01) ≈ ref_g_si + 3.4634e-5.
        s_3552 = next(s for s in data["stations"] if s["station"] == "3552.0100")
        assert s_3552["abs_g"] == pytest.approx(ref_g_si + 3.4634e-5, abs=1e-7)

    def test_upload_rejects_non_numeric_reference_station(self, cg5_text):
        # The Swagger UI placeholder "string" must not blow up the server.
        # The error should be the same "not present, here are the available stations"
        # message the user would see for any other mismatch — that is universally
        # actionable regardless of *why* the input is wrong.
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={"reference_station": "string"},
        )
        assert resp.status_code == 422
        body = resp.text
        assert "string" in body
        assert "not present" in body.lower()
        # The actual station IDs from the file are listed back to the user.
        assert "692" in body

    def test_upload_rejects_empty_reference_station(self, cg5_text):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={"reference_station": "   "},
        )
        assert resp.status_code == 422
        assert "reference_station" in resp.text

    def test_upload_rejects_unknown_reference_station(self, cg5_text):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={"reference_station": "9999"},
        )
        assert resp.status_code == 422
        body = resp.text
        assert "9999" in body
        # The available stations should be listed back to help the user.
        assert "692" in body

    def test_upload_rejects_garbage_file(self):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload",
            files={"file": ("not-a-survey.txt", "not a CG-5 file at all\n", "text/plain")},
            data={"reference_station": "1"},
        )
        assert resp.status_code == 422
        assert "CG-5" in resp.text or "measurement" in resp.text

    def test_upload_endpoint_unit_conversion(self, cg5_text):
        client = TestClient(app)
        resp = client.post(
            "/adjustment/cg5/upload?unit=ugal",
            files={"file": ("survey.txt", cg5_text, "text/plain")},
            data={
                "reference_station": "692",
                "drift_degree": "2",
                "sensor_offset": "-0.211",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["unit"] == "ugal"
        # 1 mGal = 1000 µGal — reference (matlab) Δg at 3552.01 is 3.4634 mGal
        ref_to_3552 = next(
            s for s in data["stations"] if s["station"] == "3552.0100"
        )
        assert ref_to_3552["delta_g"] == pytest.approx(3463.4, abs=10.0)
