"""Tests for coordinate conversion service and /coordinates/to-decimal endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.coordinates_conversion import convert_coordinate, parse_decimal, parse_dms

client = TestClient(app)


# ── parse_dms ─────────────────────────────────────────────────────────────────


class TestParseDms:
    def test_comma_decimal_in_seconds(self):
        assert parse_dms("48°46'36,30101\"") == pytest.approx(48.7767502806, rel=1e-9)

    def test_dot_decimal_in_seconds(self):
        assert parse_dms("48°46'36.30101\"") == pytest.approx(48.7767502806, rel=1e-9)

    def test_whole_seconds(self):
        assert parse_dms("48°46'36\"") == pytest.approx(48.7766666667, rel=1e-9)

    def test_negative(self):
        assert parse_dms("-48°46'36\"") == pytest.approx(-48.7766666667, rel=1e-9)

    def test_zero(self):
        assert parse_dms("0°0'0\"") == pytest.approx(0.0)

    def test_ninety_degrees(self):
        assert parse_dms("90°0'0.0\"") == pytest.approx(90.0)

    def test_no_closing_quote(self):
        assert parse_dms("17°24'05") == pytest.approx(17.4013888889, rel=1e-9)

    def test_surrounding_double_quotes(self):
        assert parse_dms('"17°24\'05""') == pytest.approx(17.4013888889, rel=1e-9)

    def test_surrounding_single_quotes(self):
        assert parse_dms("'48°46'36\"'") == pytest.approx(48.7766666667, rel=1e-9)

    def test_escaped_quote(self):
        assert parse_dms("17°24'05\\\"") == pytest.approx(17.4013888889, rel=1e-9)

    def test_extra_whitespace(self):
        assert parse_dms("  48°46'36\"  ") == pytest.approx(48.7766666667, rel=1e-9)

    def test_non_dms_returns_none(self):
        assert parse_dms("48.77675") is None

    def test_plain_number_returns_none(self):
        assert parse_dms("not-a-coord") is None


# ── parse_decimal ─────────────────────────────────────────────────────────────


class TestParseDecimal:
    def test_dot_separator(self):
        assert parse_decimal("48.77675") == pytest.approx(48.77675)

    def test_comma_separator(self):
        assert parse_decimal("48,77675") == pytest.approx(48.77675)

    def test_negative_dot(self):
        assert parse_decimal("-48.77675") == pytest.approx(-48.77675)

    def test_negative_comma(self):
        assert parse_decimal("-48,77675") == pytest.approx(-48.77675)

    def test_integer_string(self):
        assert parse_decimal("48") == pytest.approx(48.0)

    def test_non_numeric_returns_none(self):
        assert parse_decimal("not-a-number") is None

    def test_empty_returns_none(self):
        assert parse_decimal("") is None


# ── convert_coordinate ────────────────────────────────────────────────────────


class TestConvertCoordinate:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("48°46'36,30101\"", 48.7767502806),
            ("48°46'36.30101\"", 48.7767502806),
            ("48,77675", 48.77675),
            ("48.77675", 48.77675),
            ("-48°46'36\"", -48.7766666667),
            ("-48,77675", -48.77675),
            ("0°0'0\"", 0.0),
            ("90°0'0.0\"", 90.0),
            ("48°13'22\"", 48.2227777778),
            ("17°24'05\"", 17.4013888889),
            ("17°24'05", 17.4013888889),
            ('"17°24\'05""', 17.4013888889),
            ("'48°46'36\"'", 48.7766666667),
            ("17°24'05\\\"", 17.4013888889),
        ],
    )
    def test_parametrized_conversions(self, raw: str, expected: float):
        assert convert_coordinate(raw) == pytest.approx(expected, rel=1e-9)

    def test_unrecognisable_dms_raises(self):
        with pytest.raises(ValueError, match="Unrecognisable DMS format"):
            convert_coordinate("48°broken")

    def test_unrecognisable_plain_raises(self):
        with pytest.raises(ValueError, match="Unrecognisable coordinate format"):
            convert_coordinate("not-a-coord")

    def test_returns_float(self):
        assert isinstance(convert_coordinate("48.77675"), float)


# ── /coordinates/to-decimal endpoint ─────────────────────────────────────────


class TestToDecimalEndpoint:
    URL = "/coordinates/convert/to-decimal"

    def test_single_decimal_dot(self):
        r = client.post(self.URL, json={"values": ["48.77675"]})
        assert r.status_code == 200
        result = r.json()["results"][0]
        assert result["input"] == "48.77675"
        assert result["decimal"] == pytest.approx(48.77675)

    def test_single_decimal_comma(self):
        r = client.post(self.URL, json={"values": ["48,77675"]})
        assert r.status_code == 200
        assert r.json()["results"][0]["decimal"] == pytest.approx(48.77675)

    def test_single_dms(self):
        r = client.post(self.URL, json={"values": ["48°46'36.30101\""]})
        assert r.status_code == 200
        assert r.json()["results"][0]["decimal"] == pytest.approx(48.7767502806, rel=1e-9)

    def test_batch_mixed_formats(self):
        payload = {"values": ["48°46'36,30101\"", "48,77675", "17°24'05\""]}
        r = client.post(self.URL, json=payload)
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 3
        assert results[0]["decimal"] == pytest.approx(48.7767502806, rel=1e-9)
        assert results[1]["decimal"] == pytest.approx(48.77675)
        assert results[2]["decimal"] == pytest.approx(17.4013888889, rel=1e-9)

    def test_input_echoed_back(self):
        raw = "17°24'05\""
        r = client.post(self.URL, json={"values": [raw]})
        assert r.json()["results"][0]["input"] == raw

    def test_negative_dms(self):
        r = client.post(self.URL, json={"values": ["-48°46'36\""]})
        assert r.status_code == 200
        assert r.json()["results"][0]["decimal"] == pytest.approx(-48.7766666667, rel=1e-9)

    def test_negative_decimal(self):
        r = client.post(self.URL, json={"values": ["-48,77675"]})
        assert r.status_code == 200
        assert r.json()["results"][0]["decimal"] == pytest.approx(-48.77675)

    # ── decimals param ────────────────────────────────────────────────────────

    def test_decimals_default_is_ten(self):
        r = client.post(self.URL, json={"values": ["48°46'36.30101\""]})
        assert r.json()["results"][0]["decimal"] == round(48.7767502806, 10)

    def test_decimals_four(self):
        r = client.post(self.URL + "?decimals=4", json={"values": ["48°46'36.30101\""]})
        assert r.json()["results"][0]["decimal"] == pytest.approx(48.7768, abs=1e-4)

    def test_decimals_zero_rounds_to_integer(self):
        r = client.post(self.URL + "?decimals=0", json={"values": ["48.77675"]})
        assert r.json()["results"][0]["decimal"] == pytest.approx(49.0)

    def test_decimals_applied_to_plain_decimal(self):
        r = client.post(self.URL + "?decimals=3", json={"values": ["-48,77675"]})
        assert r.json()["results"][0]["decimal"] == pytest.approx(-48.777, abs=1e-3)

    def test_decimals_applied_to_negative_dms(self):
        r = client.post(self.URL + "?decimals=4", json={"values": ["-48°46'36\""]})
        assert r.json()["results"][0]["decimal"] == pytest.approx(-48.7767, abs=1e-4)

    def test_decimals_above_15_returns_422(self):
        r = client.post(self.URL + "?decimals=16", json={"values": ["48.77675"]})
        assert r.status_code == 422

    def test_decimals_negative_returns_422(self):
        r = client.post(self.URL + "?decimals=-1", json={"values": ["48.77675"]})
        assert r.status_code == 422

    # ── error handling ────────────────────────────────────────────────────────

    def test_invalid_value_returns_422(self):
        r = client.post(self.URL, json={"values": ["not-a-coordinate"]})
        assert r.status_code == 422

    def test_mixed_valid_and_invalid_returns_422(self):
        r = client.post(self.URL, json={"values": ["48.77675", "bad-input"]})
        assert r.status_code == 422

    def test_empty_list_returns_422(self):
        r = client.post(self.URL, json={"values": []})
        assert r.status_code == 422

    def test_missing_body_returns_422(self):
        r = client.post(self.URL)
        assert r.status_code == 422
