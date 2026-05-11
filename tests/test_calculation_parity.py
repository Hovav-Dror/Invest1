from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from invest_core.calculations import (
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
    assert_matches_fixture(tax_events(load_data()), "tax_events_default")


def test_tax_events_no_cpi_matches_r_fixture():
    assert_matches_fixture(tax_events(load_data(), adjust_cpi=False), "tax_events_no_cpi")


def test_commission_effect_default_matches_r_fixture():
    assert_matches_fixture(commission_effect(load_data()), "commission_effect_default")


def test_commission_tax_default_matches_r_fixture():
    assert_matches_fixture(commission_tax_scenarios(load_data()), "commission_tax_default")


def test_sp500_risk_default_matches_r_fixture():
    assert_matches_fixture(sp500_risk(load_data()), "sp500_risk_default")


def test_portfolio_summary_default_matches_r_fixture():
    assert_matches_fixture(portfolio_summary(load_data()), "portfolio_summary_default")


def test_kupat_gemel_default_matches_r_fixture():
    assert_matches_fixture(kupat_gemel(load_data()), "kupat_gemel_default")


def test_kupat_gemel_pension_default_matches_r_fixture():
    assert_matches_fixture(kupat_gemel(load_data(), with_pension=True), "kupat_gemel_pension_default")


def test_independent_commissions_default_matches_r_fixture():
    assert_matches_fixture(independent_commissions(load_data()), "independent_commissions_default")


def test_tax_us_vs_il_default_matches_r_fixture():
    assert_matches_fixture(independent_commissions(load_data(), tax_mode="us_vs_il"), "tax_us_vs_il_default")


def test_portfolio_over_time_default_matches_r_fixture():
    assert_matches_fixture(portfolio_over_time(load_data()), "portfolio_over_time_default")


def test_us_world_rolling_default_matches_r_fixture():
    assert_matches_fixture(us_world_rolling(load_data()), "us_world_rolling_default")


def test_us_global_rolling_default_matches_r_fixture():
    assert_matches_fixture(us_global_rolling(load_data(), global_mix=True), "us_global_rolling_default")


def test_sp500_scv_rolling_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_rolling(load_data()), "sp500_scv_rolling_default")


def test_sp500_scv_heatmap_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_heatmap(load_data()), "sp500_scv_heatmap_default")


def test_sp500_scv_after_tax_default_matches_r_fixture():
    assert_matches_fixture(sp500_scv_rolling(load_data(), after_tax=True), "sp500_scv_after_tax_default")


def test_trinity_default_matches_r_fixture():
    assert_matches_fixture(trinity(load_data()), "trinity_default")
