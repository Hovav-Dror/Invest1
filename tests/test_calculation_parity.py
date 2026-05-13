from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from invest_core.calculations import (
    CalculationInputError,
    commission_effect,
    commission_tax_scenarios,
    independent_commissions,
    kupat_gemel,
    portfolio_over_time,
    portfolio_summary,
    sp500_risk,
    sp500_scv_heatmap,
    sp500_scv_rolling,
    tax_events,
    trinity,
    us_global_rolling,
    us_world_rolling,
)
from invest_core.data import load_data

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "r_outputs"
PHASE1_TAX_END = "2023-01-01"
PHASE1_MONTHLY_END = "2024-01-01"
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


def test_tax_events_default_matches_r_fixture():
    assert_matches_fixture(tax_events(load_data(), end=PHASE1_TAX_END), "tax_events_default")


def test_tax_events_no_cpi_matches_r_fixture():
    assert_matches_fixture(tax_events(load_data(), end=PHASE1_TAX_END, adjust_cpi=False), "tax_events_no_cpi")


def test_commission_effect_default_matches_r_fixture():
    assert_matches_fixture(commission_effect(load_data(), end=PHASE1_TAX_END), "commission_effect_default")


def test_commission_tax_default_matches_r_fixture():
    assert_matches_fixture(commission_tax_scenarios(load_data(), end=PHASE1_TAX_END), "commission_tax_default")


def test_sp500_risk_default_matches_r_fixture():
    assert_matches_fixture(sp500_risk(load_data(), end=PHASE1_MONTHLY_END), "sp500_risk_default")


def test_portfolio_summary_default_matches_r_fixture():
    assert_matches_fixture(portfolio_summary(load_data(), year_end=PHASE1_YEAR_END), "portfolio_summary_default")


def test_kupat_gemel_default_matches_r_fixture():
    actual = kupat_gemel(load_data()).loc[lambda df: df["date"] <= pd.Timestamp(PHASE1_MONTHLY_END)]
    assert_matches_fixture(actual, "kupat_gemel_default")


def test_kupat_gemel_pension_default_matches_r_fixture():
    actual = kupat_gemel(load_data(), with_pension=True).loc[lambda df: df["date"] <= pd.Timestamp(PHASE1_MONTHLY_END)]
    assert_matches_fixture(actual, "kupat_gemel_pension_default")


def test_kupat_gemel_rejects_post_60_without_age_60_anchor():
    with pytest.raises(CalculationInputError, match="age-60 CPI anchor"):
        kupat_gemel(load_data(), age=61)


def test_independent_commissions_default_matches_r_fixture():
    assert_matches_fixture(independent_commissions(load_data(), end=PHASE1_TAX_END), "independent_commissions_default")


def test_tax_us_vs_il_default_matches_r_fixture():
    assert_matches_fixture(independent_commissions(load_data(), tax_mode="us_vs_il", end=PHASE1_TAX_END), "tax_us_vs_il_default")


def test_portfolio_over_time_default_matches_r_fixture():
    assert_matches_fixture(portfolio_over_time(load_data(), year_end=PHASE1_YEAR_END), "portfolio_over_time_default")


def test_us_world_rolling_default_matches_r_fixture():
    assert_matches_fixture(us_world_rolling(load_data(), year_end=PHASE1_YEAR_END), "us_world_rolling_default")


def test_us_global_rolling_default_matches_r_fixture():
    assert_matches_fixture(us_global_rolling(load_data(), global_mix=True, year_end=PHASE1_YEAR_END), "us_global_rolling_default")


def test_sp500_scv_rolling_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_rolling(load_data(), year_end=PHASE1_YEAR_END), "sp500_scv_rolling_default")


def test_sp500_scv_heatmap_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_heatmap(load_data(), year_end=PHASE1_YEAR_END), "sp500_scv_heatmap_default")


def test_sp500_scv_after_tax_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_rolling(load_data(), after_tax=True, year_end=PHASE1_YEAR_END), "sp500_scv_after_tax_default")


def test_trinity_default_matches_r_fixture():
    assert_matches_fixture(trinity(load_data(), year_end=PHASE1_YEAR_END), "trinity_default")
