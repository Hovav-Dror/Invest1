"""Calculation rules checked against small hand-computed examples.

Each test builds synthetic data so the expected numbers can be worked out on
paper. See docs/methodology.md for the rules themselves.
"""

import numpy as np
import pandas as pd
import pytest

from invest_core import calculations as calc
from invest_core.data import InvestData, load_data


def monthly_data(prices, fx=None, cpi=None, cpi_us=None, start="2000-01-01") -> InvestData:
    """InvestData with only the monthly S&P 500 tables filled in."""

    n = len(prices)
    dates = pd.date_range(start, periods=n, freq="MS")
    fx = fx if fx is not None else [1.0] * n
    cpi = cpi if cpi is not None else [100.0] * n
    cpi_us = cpi_us if cpi_us is not None else [100.0] * n
    sp500div = pd.DataFrame(
        {
            "date": dates,
            "Real_Total_Return_Price": prices,
            "dollar": fx,
            "SP500wDividends": np.array(prices) * np.array(fx),
            "CPI": cpi,
        }
    )
    sp500us = pd.DataFrame({"date": dates, "Real_Total_Return_Price": prices, "CPI_US": cpi_us})
    empty = pd.DataFrame()
    return InvestData(LazyReturns1=empty, PortfoliosStructure=empty, SP500DIV=sp500div, SP500US=sp500us, US_Small_Cap_Value_Monthly=empty)


def annual_data(series: dict[str, list[float]], first_year=2000, cpi_us=None, commission=0.0) -> InvestData:
    """InvestData with LazyReturns1 rows built from annual returns in percent.

    The first year of each series is a base row (index 1); its return is ignored.
    """

    rows = []
    for portfolio, returns in series.items():
        index = 1.0
        for pos, year_return in enumerate(returns):
            if pos:
                index *= 1 + year_return / 100
            year = first_year + pos
            row = {
                "Year": float(year),
                "Portfolio": portfolio,
                "commission": commission,
                "Inflation": 0.0,
                "CPI_US": (cpi_us[pos] if cpi_us else 1.0),
                "CPI_IL": 1.0,
                "USD": 1.0,
                "YearReturn": year_return,
                "index": index,
                "Index_CPI_US": index,
                "Index_CPI_IL": index,
                "BadYears": 0.0,
                "Drop": 0.0,
                "BadYears_CPI_US": 0.0,
                "Drop_CPI_US": 0.0,
                "BadYears_CPI_IL": 0.0,
                "Drop_CPI_IL": 0.0,
            }
            rows.append({**row, "CommissionUse": False})
            rows.append({**row, "CommissionUse": True})
    empty = pd.DataFrame()
    return InvestData(LazyReturns1=pd.DataFrame(rows), PortfoliosStructure=empty, SP500DIV=empty, SP500US=empty, US_Small_Cap_Value_Monthly=empty)


# --- Date alignment ---------------------------------------------------------


def test_fx_and_cpi_use_same_row_for_monthly_averages_and_previous_row_for_point_prices():
    data = monthly_data([1, 1, 1, 1], fx=[3.0, 3.1, 3.2, 3.3], cpi=[10, 11, 12, 13], start="2010-12-01")
    market = calc.monthly_market(data)

    # 2010-12 and 2011-01 are monthly averages: month-d observations.
    assert market["fx"].tolist()[:2] == [3.0, 3.1]
    # From 2011-02 the price is the start of the month: use the previous month's values.
    assert market["fx"].tolist()[2:] == [3.1, 3.2]
    assert market["cpi_il"].tolist() == pytest.approx([10, 11, 11, 12])


def test_interior_cpi_gap_is_filled_geometrically():
    data = monthly_data([1, 1, 1], cpi_us=[100.0, np.nan, 121.0])
    assert calc.monthly_market(data)["cpi_us"].iloc[1] == pytest.approx(110.0)


def test_real_data_has_no_gaps_in_default_ranges():
    data = load_data()
    for start, end in [(calc.DEFAULT_TAX_START, calc.DEFAULT_TAX_END), ("1871-01-01", "2026-01-01")]:
        frame = calc._monthly_window(data, start, end, ["price", "cpi_us"])
        months = frame["date"].dt.to_period("M").astype("int64")
        assert (months.diff().dropna() == 1).all()


# --- Tax events -------------------------------------------------------------


def test_tax_at_end_taxes_real_gain_only():
    # Price +20% while CPI +10%: tax 25% of the 0.1 real gain -> 1.175 nominal.
    data = monthly_data([100, 120], cpi=[100, 110])
    nominal = calc.tax_events(data, start="2000-01-01", end="2000-02-01", adjust_cpi=False)
    assert nominal["End25"].iloc[-1] == pytest.approx(1.175)
    real = calc.tax_events(data, start="2000-01-01", end="2000-02-01")
    assert real["End25"].iloc[-1] == pytest.approx(1.175 / 1.1)


def test_tax_never_refunds_a_loss():
    data = monthly_data([100, 80])
    result = calc.tax_events(data, start="2000-01-01", end="2000-02-01")
    assert result["End25"].iloc[-1] == pytest.approx(0.8)


def test_realized_losses_offset_later_gains():
    # Sell every month: -20% (loss 0.2 carried), then +25% back to 1.0 (gain 0.2 offset).
    data = monthly_data([100, 80, 100])
    result = calc.tax_events(data, start="2000-01-01", end="2000-03-01")
    assert result["EveryMonth"].tolist() == pytest.approx([1.0, 0.8, 1.0])


def test_periodic_sales_happen_exactly_every_n_months():
    # +1% per month for 10 years. The 5-year schedule sells at month 60 and 120.
    prices = 100 * 1.01 ** np.arange(121)
    data = monthly_data(list(prices))
    result = calc.tax_events(data, start="2000-01-01", end="2010-01-01")
    # Selling every 10 years pays exactly once, at the end: same as tax at the end.
    assert result["Every120Months"].tolist() == pytest.approx(result["End25"].tolist())
    five_years = 1 + 0.75 * (1.01**60 - 1)
    assert result["Every60Months"].iloc[60] == pytest.approx(five_years)
    assert result["Every60Months"].iloc[120] == pytest.approx(five_years**2)
    one_year = 1 + 0.75 * (1.01**12 - 1)
    assert result["Every12Months"].iloc[24] == pytest.approx(one_year**2)
    # More frequent realization leaves less.
    last = result.iloc[-1]
    assert last["EveryMonth"] < last["Every12Months"] < last["Every60Months"] < last["End25"]


def test_annual_fee_removes_exactly_that_percentage_per_year():
    data = monthly_data([100] * 13)
    result = calc.commission_tax(data, commission=1.0, start="2000-01-01", end="2001-01-01")
    assert result["tax_at_end"].iloc[-1] == pytest.approx(0.99)
    assert result["tax_at_end"].iloc[0] == pytest.approx(1.0)
    # The gross column is the index itself, without fees or tax.
    assert result["SP500_in_NIS"].iloc[-1] == pytest.approx(1.0)


# --- S&P 500 risk -----------------------------------------------------------


def test_sp500_risk_is_real():
    # 12 months: price +21%, US CPI +10% -> 10% real annual return.
    prices = list(100 * 1.21 ** (np.arange(13) / 12))
    cpi_us = list(100 * 1.10 ** (np.arange(13) / 12))
    result = calc.sp500_risk(monthly_data(prices, cpi_us=cpi_us), years=1)
    assert result["TotalReturnP"].tolist() == pytest.approx([0.10])


# --- Lazy portfolios --------------------------------------------------------


def test_cagr_over_time_uses_elapsed_years_per_row():
    data = annual_data({"A": [0, 10, 10, 10]})
    result = calc.portfolio_over_time(data, portfolios=["A"], year_start=2001, year_end=2003)
    assert result["N"].tolist() == [1, 2, 3]
    assert result["CAGR"].tolist() == pytest.approx([0.10, 0.10, 0.10])


def test_rolling_cagr_window_includes_the_first_year():
    data = annual_data({"A": [0, 10, 10]})
    result = calc.portfolio_over_time(data, portfolios=["A"], year_start=2001, year_end=2002, rolling_window=2)
    assert result["RollingCAGR"].tolist()[-1] == pytest.approx(0.10)


def test_summary_volatility_and_drawdown_include_the_first_year():
    data = annual_data({"A": [0, -50, 100]})
    summary = calc.portfolio_summary(data, portfolios=["A"], year_start=2001, year_end=2002)
    assert summary["N"].iloc[0] == 2
    assert summary["CAGR"].iloc[0] == pytest.approx(0.0)
    assert summary["SD"].iloc[0] == pytest.approx(np.std([-0.5, 1.0], ddof=1))
    assert summary["MaxDrop"].iloc[0] == pytest.approx(-0.5)
    assert summary["MaxShefelYears"].iloc[0] == 2


# --- Trinity ----------------------------------------------------------------


def test_trinity_stops_at_zero_and_reports_depletion_year():
    # No growth, no inflation, withdraw 40% of the base each year.
    data = annual_data({"S&P 500": [0, 0, 0, 0, 0]})
    result = calc.trinity(data, portfolio="S&P 500", yearly_draw=0.4, years=3, base=100)
    first = result.iloc[0]
    assert first["start_year"] == 2001
    assert first["end_year"] == 2003
    assert first["Investment_remained"] == 0
    assert first["depleted_year"] == 2003
    assert (result["Investment_remained"] >= 0).all()


def test_trinity_applies_the_start_years_return():
    data = annual_data({"S&P 500": [0, 10, 0]}, cpi_us=[1.0, 1.0, 1.0])
    result = calc.trinity(data, portfolio="S&P 500", yearly_draw=0.0, years=1, base=100)
    assert result.set_index("start_year").loc[2001, "Investment_remained"] == pytest.approx(110)


def test_trinity_is_in_real_terms():
    data = annual_data({"S&P 500": [0, 10]}, cpi_us=[1.0, 1.1])
    result = calc.trinity(data, portfolio="S&P 500", yearly_draw=0.0, years=1, base=100)
    assert result["Investment_remained"].iloc[0] == pytest.approx(100)


# --- Heatmaps and US vs world -----------------------------------------------


def test_us_world_rolling_leaves_missing_windows_empty():
    # Annual comparisons use every YearReturn, so the first full 5-year window ends in 2004.
    data = annual_data({"S&P 500": [10] * 6, "MSCI World ex USA index": [0] * 6})
    result = calc.us_world_rolling(data)
    first = result.iloc[0]
    assert first["Year"] == 2004
    assert first["Diff5"] == pytest.approx(0.10)
    assert np.isnan(first["Diff10"])


def test_heatmap_start_and_end_years():
    data = annual_data({"S&P 500": [10, 0, 0], "MSCI World ex USA index": [0, 0, 0]})
    result = calc.global_vs_sp500_heatmap(data, max_years=2)
    two_year = result[result["InvYears"] == 2].iloc[0]
    assert (two_year["StartYear"], two_year["EndYear"]) == (2000, 2001)
    assert two_year["val1"] == pytest.approx(0.10)
    assert two_year["val2"] == pytest.approx(0.06)


# --- Provident fund ---------------------------------------------------------


def test_kupat_gemel_converts_to_annuity_at_60():
    prices = list(100 * 1.01 ** np.arange(36))
    data = monthly_data(prices)
    result = calc.kupat_gemel(data, age=59, start_year=2000, initial=1, kh_annual_fee=0, ph_annual_fee=0, ii_annual_fee=0, ii_buy_sell=0)
    after = result[result["age"] >= 60]
    # From 60 the balance is the untaxed age-60 amount (CPI flat here), not the market.
    assert after["KH"].tolist() == pytest.approx([1.01 ** 12] * len(after))
    assert after["II"].iloc[-1] > after["II"].iloc[0]
    # Before 60 the fund is shown after lump-sum tax, like the self-managed portfolio.
    before = result[result["age"] < 60]
    assert before["KH"].tolist() == pytest.approx(before["II"].tolist())


def test_self_managed_pension_runs_out_and_reports_shortfall():
    # Flat market, no costs: the age-60 balance of 1 is paid over 10 months,
    # so the self-managed portfolio is empty after 10 payments.
    data = monthly_data([100] * 24)
    result = calc.kupat_gemel(
        data, with_pension=True, age=60, start_year=2000, initial=1, pension_months=10,
        kh_annual_fee=0, ii_annual_fee=0, ii_buy_sell=0,
    )
    assert result["Kitzba"].iloc[1] == pytest.approx(0.1)
    assert result["IIb"].iloc[10] == pytest.approx(0.0)
    assert result["IIbShortfall"].iloc[10] == pytest.approx(0.0)
    assert result["IIbShortfall"].iloc[-1] == pytest.approx(0.1 * 13)


def test_self_managed_pension_reduces_cost_basis_on_each_sale():
    # Price doubles at once. The first payment needs a gross sale with half of it
    # gain: payment / (1 - 0.25 * 0.5).
    data = monthly_data([100, 200, 200, 200])
    result = calc.kupat_gemel(
        data, with_pension=True, age=60, start_year=2000, initial=1, pension_months=20,
        kh_annual_fee=0, ii_annual_fee=0, ii_buy_sell=0,
    )
    payment = result["Kitzba"].iloc[1]
    sold = payment / (1 - 0.25 * 0.5)
    remaining = 2 - sold
    # Remaining basis is half the remaining value, so liquidation tax is 25% of half.
    assert result["IIb"].iloc[1] == pytest.approx(remaining * (1 - 0.125))


# --- Self-managed account ---------------------------------------------------


def test_independent_dollar_tax_uses_sale_exchange_rate():
    # Stock +10% in dollars, shekel weakens 3.0 -> 3.3. No costs.
    data = monthly_data([100, 110], fx=[3.0, 3.3])
    result = calc.independent_commissions(
        data, tax_mode="us_vs_il", start="2000-01-01", end="2000-02-01", initial=300,
        dollar_commission=0, commission_per_share=0, min_dollar_commission=0, yearly_commission=0,
    )
    proceeds = 110 * 3.3  # 363
    dollar_tax = 0.25 * 10 * 3.3
    israeli_tax = 0.25 * (proceeds - 300)
    assert result["v_final_dollar"].iloc[-1] == pytest.approx(proceeds - dollar_tax)
    assert result["v_final_il"].iloc[-1] == pytest.approx(proceeds - israeli_tax)


def test_independent_sale_commission_uses_shares_bought():
    # 100 USD buys 2 shares at $50. Price doubles: still 2 shares, so the
    # per-share commission is unchanged.
    data = monthly_data([100, 200])
    result = calc.independent_commissions(
        data, start="2000-01-01", end="2000-02-01", initial=100, share_price=50,
        dollar_commission=0, commission_per_share=1, min_dollar_commission=0, yearly_commission=0,
    )
    after_buy = 100 - 2
    assert result["v_final"].iloc[-1] == pytest.approx(after_buy * 2 - after_buy / 50)


# --- Real data sanity -------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint_call",
    [
        lambda d: calc.tax_events(d),
        lambda d: calc.commission_tax_scenarios(d),
        lambda d: calc.kupat_gemel(d),
        lambda d: calc.kupat_gemel(d, with_pension=True),
        lambda d: calc.independent_commissions(d, tax_mode="us_vs_il"),
        lambda d: calc.trinity(d, yearly_draw=0.08),
    ],
)
def test_no_negative_money_on_real_data(endpoint_call):
    frame = endpoint_call(load_data())
    numeric = frame.select_dtypes("number").drop(columns=["age", "year3", "start_year", "end_year", "depleted_year"], errors="ignore")
    assert (numeric.fillna(0) >= 0).all().all()


def test_after_tax_never_exceeds_before_tax_on_real_data():
    result = calc.tax_events(load_data())
    for column in ("End25", "EveryMonth", "Every12Months", "Every60Months", "Every120Months"):
        assert (result[column] <= result["v"] + 1e-9).all()
