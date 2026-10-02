"""Parity with the frozen R outputs, for calculations whose rules did not change.

Calculation version 2 corrected the other R-era calculations; those are covered
by hand-computed tests in test_calculations.py instead.
"""

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from invest_core.calculations import sp500_scv_heatmap, sp500_scv_rolling
from invest_core.data import load_data

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "r_outputs"
PHASE1_YEAR_END = 2023


def read_fixture(name: str) -> pd.DataFrame:
    frame = pd.read_csv(FIXTURE_DIR / f"{name}.csv")
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def assert_matches_fixture(actual: pd.DataFrame, fixture_name: str) -> None:
    expected = read_fixture(fixture_name)
    actual = actual.reset_index(drop=True)
    assert actual.columns.tolist() == expected.columns.tolist()
    assert_frame_equal(actual, expected, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-10)


def test_sp500_scv_rolling_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_rolling(load_data(), year_end=PHASE1_YEAR_END), "sp500_scv_rolling_default")


def test_sp500_scv_heatmap_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_heatmap(load_data(), year_end=PHASE1_YEAR_END), "sp500_scv_heatmap_default")
