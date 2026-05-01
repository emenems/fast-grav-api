"""
Tests for the Longman (1959) tidal gravity implementation.
"""

from datetime import datetime

import pytest

from app.services.tides_longman import _mjd, _MJD_J1900, solve_longman_tide

# ── _mjd ─────────────────────────────────────────────────────────────────────


class TestMjd:
    def test_j1900_epoch(self):
        # Julian century origin used inside solve_longman_tide must equal 15019.5
        dt = datetime(1899, 12, 31, 12, 0, 0)
        assert _mjd(dt) == pytest.approx(15019.5, abs=1e-9)

    def test_module_constant_matches(self):
        assert _MJD_J1900 == pytest.approx(15019.5, abs=1e-9)

    def test_known_date(self):
        # MJD of 2000-01-01 12:00:00 UTC = 51544.5
        dt = datetime(2000, 1, 1, 12, 0, 0)
        assert _mjd(dt) == pytest.approx(51544.5, abs=1e-9)

    def test_fractional_day(self):
        # 06:00 UTC is exactly 0.25 of a day
        dt_midnight = datetime(2020, 6, 15, 0, 0, 0)
        dt_6h = datetime(2020, 6, 15, 6, 0, 0)
        assert _mjd(dt_6h) - _mjd(dt_midnight) == pytest.approx(0.25, abs=1e-12)

    def test_microseconds(self):
        dt_a = datetime(2020, 1, 1, 0, 0, 0, 0)
        dt_b = datetime(2020, 1, 1, 0, 0, 1, 0)  # +1 s
        dt_c = datetime(2020, 1, 1, 0, 0, 0, 500_000)  # +0.5 s
        diff_full = _mjd(dt_b) - _mjd(dt_a)
        diff_half = _mjd(dt_c) - _mjd(dt_a)
        assert diff_full == pytest.approx(1 / 86400, abs=1e-9)
        assert diff_half == pytest.approx(0.5 / 86400, abs=1e-9)


# ── solve_longman_tide ────────────────────────────────────────────────────────


class TestSolveLongmanTide:
    REF_LAT = 48.4
    REF_LON = 17.3
    REF_ALT = 0.0
    REF_DT = datetime(2012, 9, 4, 8, 14, 58, 300_000)
    REF_MGAL = -0.0536  # negative: Moon near horizon reduces vertical gravity

    def test_reference_case_magnitude(self):
        result = solve_longman_tide(self.REF_LAT, self.REF_LON, self.REF_ALT, self.REF_DT)
        assert abs(result) == pytest.approx(abs(self.REF_MGAL), abs=5e-4)

    def test_reference_case_sign(self):
        result = solve_longman_tide(self.REF_LAT, self.REF_LON, self.REF_ALT, self.REF_DT)
        assert result == pytest.approx(self.REF_MGAL, abs=5e-4)

    def test_output_in_mgal_range(self):
        # Typical tidal range is ±0.3 mGal; absolute ceiling is ~0.4 mGal
        result = solve_longman_tide(self.REF_LAT, self.REF_LON, self.REF_ALT, self.REF_DT)
        assert -0.4 < result < 0.4

    def test_altitude_effect(self):
        # Higher altitude → slightly larger r → slightly larger tidal signal
        low = solve_longman_tide(self.REF_LAT, self.REF_LON, 0.0, self.REF_DT)
        high = solve_longman_tide(self.REF_LAT, self.REF_LON, 5000.0, self.REF_DT)
        # |high| > |low| because r grows
        assert abs(high) > abs(low)

    def test_equator(self):
        result = solve_longman_tide(0.0, 0.0, 0.0, self.REF_DT)
        assert -0.4 < result < 0.4

    def test_north_pole(self):
        result = solve_longman_tide(90.0, 0.0, 0.0, self.REF_DT)
        assert -0.4 < result < 0.4

    def test_south_pole(self):
        result = solve_longman_tide(-90.0, 0.0, 0.0, self.REF_DT)
        assert -0.4 < result < 0.4

    def test_returns_float(self):
        result = solve_longman_tide(self.REF_LAT, self.REF_LON, self.REF_ALT, self.REF_DT)
        assert isinstance(result, float)

    def test_different_epochs_differ(self):
        dt1 = datetime(2020, 1, 1, 0, 0, 0)
        dt2 = datetime(2020, 1, 1, 6, 0, 0)
        r1 = solve_longman_tide(48.0, 17.0, 0.0, dt1)
        r2 = solve_longman_tide(48.0, 17.0, 0.0, dt2)
        assert r1 != pytest.approx(r2, abs=1e-6)
