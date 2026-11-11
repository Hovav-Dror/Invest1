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


def test_underwater_years_count_a_single_stretch_below_the_previous_peak():
    # 100 -> 80 -> 90 -> 120 (new peak) -> 95 -> 130.
    # Stretches: 2000-2003 (3 years) and 2003-2005 (2 years). A buyer at 2000 was
    # below cost again in 2004, but that is after a new peak, so it is a new stretch.
    data = annual_data({"A": [0, -20, 12.5, 33.333333333, -20.833333333, 36.842105263]})
    summary = calc.portfolio_summary(data, portfolios=["A"], year_start=2001, year_end=2005)
    assert summary["MaxShefelYears"].iloc[0] == 3


def test_unrecovered_underwater_stretch_runs_to_the_last_year():
    data = annual_data({"A": [0, -10, 5, 2]})
    summary = calc.portfolio_summary(data, portfolios=["A"], year_start=2001, year_end=2003)
    assert summary["MaxShefelYears"].iloc[0] == 3


# --- Young couples: affordability ---------------------------------------------


def test_affordability_ltv_limit_multiplies_a_drop():
    # Plenty of income: the 75% limit binds, so the price is equity / (25% + costs).
    result = calc.affordability(equity=400_000, income=100_000, rate=0.05, years=30, costs=0.0, drop=0.3)
    points = result.set_index("point")
    assert points.loc["now", "max_price"] == pytest.approx(1_600_000)
    assert points.loc["after_drop", "max_price"] == pytest.approx(1_120_000)
    assert points.loc["now", "binding"] == "ltv"


def test_affordability_income_limit_costs_about_one_for_one():
    # Zero rate: the income limit is a loan of pti * income * months.
    result = calc.affordability(equity=400_000, income=5_000, rate=0.0, years=10, pti=0.3, costs=0.0, drop=0.3)
    points = result.set_index("point")
    loan = 0.3 * 5_000 * 120
    assert points.loc["now", "binding"] == "income"
    assert points.loc["now", "max_price"] == pytest.approx(400_000 + loan)
    assert points.loc["now", "max_price"] - points.loc["after_drop", "max_price"] == pytest.approx(120_000)
    assert points.loc["now", "payment"] == pytest.approx(1_500)


def housing_frame(index, rate, start="1999-12-01"):
    """Monthly dwelling index and Bank of Israel rate; boundary d uses the index of month d-1."""

    months = pd.date_range(start, periods=len(index), freq="MS")
    return pd.DataFrame({"month": months, "housing_index": index, "boi_rate": rate})


def test_down_payment_cash_earns_the_rate_less_tax():
    n = 13
    data = monthly_data([100.0] * n)
    housing = housing_frame([100.0] * (n + 1), [12.0] * (n + 1))
    result = calc.down_payment(data, housing, years=1, stock_share=0.0, cash_spread=0.0)
    gain = 1.01 ** 12 - 1
    assert result["apartment"].iloc[0] == pytest.approx(1 + 0.75 * gain)
    assert result["cash"].iloc[0] == pytest.approx(result["apartment"].iloc[0])


def test_down_payment_divides_by_dwelling_prices_after_tax():
    # Stocks and dwelling prices both double in a year; tax takes 25% of the gain.
    n = 13
    prices = list(np.geomspace(100, 200, n))
    data = monthly_data(prices)
    housing = housing_frame(list(np.geomspace(100, 200, n)) + [200.0], [0.0] * (n + 1))
    result = calc.down_payment(data, housing, years=1, stock_share=1.0, stock_fee=0.0, cash_spread=0.0)
    assert result["apartment"].iloc[0] == pytest.approx((2 - 0.25) / 2)
    assert result["homes_change"].iloc[0] == pytest.approx(1.0)


def test_down_payment_waits_until_the_apartment_is_back():
    # Stocks fall 20% in the first year, then recover by month 18.
    prices = list(np.linspace(100, 80, 13)) + list(np.linspace(80 + 10 / 3, 100, 6)) + [100.0] * 6
    n = len(prices)
    data = monthly_data(prices)
    housing = housing_frame([100.0] * (n + 1), [0.0] * (n + 1))
    result = calc.down_payment(data, housing, years=1, stock_share=1.0, wait_years=1, stock_fee=0.0, cash_spread=0.0)
    first = result.iloc[0]
    assert first["apartment_on_time"] == pytest.approx(0.8)
    assert first["waited_months"] == 6
    assert first["apartment"] == pytest.approx(1.0)


def test_down_payment_does_not_wait_without_a_real_drop():
    # Stocks lag cash (flat while cash earns 12%) but never fall: no reason to postpone.
    n = 25
    data = monthly_data([100.0] * n)
    housing = housing_frame([100.0] * (n + 1), [12.0] * (n + 1))
    result = calc.down_payment(data, housing, years=1, stock_share=1.0, wait_years=1, stock_fee=0.0, cash_spread=0.0)
    assert (result["waited_months"] == 0).all()
    assert len(result) == n - 12


def test_down_payment_wait_stops_at_the_end_of_the_data():
    # Stocks fall 20% and never recover: buy in the last month with data, keep every start month.
    prices = list(np.linspace(100, 80, 13)) + [80.0] * 4
    n = len(prices)
    data = monthly_data(prices)
    housing = housing_frame([100.0] * (n + 1), [0.0] * (n + 1))
    result = calc.down_payment(data, housing, years=1, stock_share=1.0, wait_years=1, stock_fee=0.0, cash_spread=0.0)
    assert len(result) == n - 12
    assert result.iloc[0]["waited_months"] == 4


def test_down_payment_israeli_shares_add_the_dividend_yield():
    # A flat price index earns only the assumed dividend: 2.5% a year, then 25% tax on the gain.
    n = 13
    data = monthly_data([100.0] * n)
    housing = housing_frame([100.0] * (n + 1), [0.0] * (n + 1)).assign(tase_index=200.0)
    result = calc.down_payment(
        data, housing, years=1, stock_share=1.0, stock_fee=0.0, cash_spread=0.0, market_index="israel"
    )
    assert result["apartment"].iloc[0] == pytest.approx(1 + 0.75 * calc.DOWN_IL_DIVIDEND)
    with pytest.raises(calc.CalculationInputError):
        calc.down_payment(data, housing, years=1, market_index="nasdaq")


def test_down_payment_glide_ends_in_cash():
    n = 25
    data = monthly_data(list(np.linspace(100, 50, n)))
    housing = housing_frame([100.0] * (n + 1), [0.0] * (n + 1))
    glide = calc.down_payment(data, housing, years=2, stock_share=1.0, glide=True, stock_fee=0.0, cash_spread=0.0)
    fixed = calc.down_payment(data, housing, years=2, stock_share=1.0, stock_fee=0.0, cash_spread=0.0)
    assert fixed["apartment"].iloc[0] == pytest.approx(0.5)
    assert 0.5 < glide["apartment"].iloc[0] < 1.0


def test_down_payment_glide_does_not_wait():
    # With the glide path the money is all cash by the planned date, so a fall cannot be waited out.
    prices = list(np.linspace(100, 80, 13)) + list(np.linspace(80 + 10 / 3, 100, 6)) + [100.0] * 6
    n = len(prices)
    data = monthly_data(prices)
    housing = housing_frame([100.0] * (n + 1), [0.0] * (n + 1))
    result = calc.down_payment(
        data, housing, years=1, stock_share=1.0, glide=True, wait_years=1, stock_fee=0.0, cash_spread=0.0
    )
    assert (result["waited_months"] == 0).all()
    assert (result["apartment"] == result["apartment_on_time"]).all()


def test_purchase_tax_brackets():
    assert calc.purchase_tax(1_900_000) == 0
    assert calc.purchase_tax(2_500_000) == pytest.approx((2_347_040 - 1_978_745) * 0.035 + (2_500_000 - 2_347_040) * 0.05)
    assert calc.purchase_tax(1_000_000, "investor") == pytest.approx(80_000)


def test_affordability_renovation_and_tax_come_out_of_equity():
    # Plenty of income, no costs: renovation leaves less cash, and above the exemption tax eats into it.
    base = dict(income=1_000_000, rate=0.05, years=30, costs=0.0, drop=0.3)
    plain = calc.affordability(equity=400_000, **base).set_index("point").loc["now"]
    renovated = calc.affordability(equity=400_000, renovation=100_000, **base).set_index("point").loc["now"]
    assert plain["max_price"] == pytest.approx(1_600_000, rel=1e-9)
    assert renovated["max_price"] == pytest.approx(1_200_000, rel=1e-9)
    rich = calc.affordability(equity=1_000_000, **base).set_index("point").loc["now"]
    # 25% of the price plus tax equals the cash.
    assert rich["max_price"] * 0.25 + calc.purchase_tax(rich["max_price"]) == pytest.approx(1_000_000, rel=1e-9)
    assert rich["purchase_tax"] > 0


def test_affordability_kink_is_where_the_limits_meet():
    result = calc.affordability(equity=400_000, income=10_000, rate=0.05, years=30, costs=0.02)
    kink = result.set_index("point").loc["kink"]
    assert kink["price_ltv"] == pytest.approx(kink["price_income"])
    assert result["equity"].is_monotonic_increasing


def test_homes_vs_stocks_real_and_aligned():
    # CPI doubles over 12 months; stocks triple, dwelling prices double, TASE flat.
    n = 13
    data = monthly_data(list(np.geomspace(100, 300, n)), cpi=list(np.geomspace(100, 200, n)))
    housing = housing_frame(list(np.geomspace(100, 200, n)) + [200.0], [1.0] * (n + 1))
    housing["tase_index"] = 50.0
    real = calc.homes_vs_stocks(data, housing)
    assert real["homes"].iloc[-1] == pytest.approx(1.0)
    assert real["sp500"].iloc[-1] == pytest.approx(1.5)
    assert real["tase"].iloc[-1] == pytest.approx(0.5)
    assert real["sp500_12m"].iloc[-1] == pytest.approx(0.5)
    nominal = calc.homes_vs_stocks(data, housing, real=False)
    assert nominal["homes"].iloc[-1] == pytest.approx(2.0)


def test_homes_vs_stocks_episodes_find_falls_and_homes_meanwhile():
    # Stocks fall 30% in 6 months, then recover; dwelling prices rise 10% meanwhile.
    prices = list(np.linspace(100, 70, 7)) + [80.0, 90.0, 100.0, 110.0] + [110.0] * 26
    n = len(prices)
    homes = list(np.linspace(100, 110, 7)) + [110.0] * (n - 7)
    housing = housing_frame(homes + [110.0], [2.0] * (n + 1))
    episodes = calc.homes_vs_stocks_episodes(monthly_data(prices), housing, real=False)
    assert len(episodes) == 1
    row = episodes.iloc[0]
    assert row["market"] == "sp500"
    assert row["stocks_change"] == pytest.approx(-0.3)
    assert row["homes_change"] == pytest.approx(0.1)
    assert row["homes_after"] == pytest.approx(0.0)
    assert (row["low"] - row["peak"]).days > 150


def test_cash_vehicles_tax_rules():
    # 5% rate, 3% inflation, no costs, 2 years.
    result = calc.cash_vehicles(
        amount=100.0, years=2, rate=0.05, inflation=0.03, fund_fee=0, deposit_spread=0, makam_cost=0, gemel_fee=0
    ).set_index(["vehicle", "year"])
    real_tax = 1.05**2 - 0.25 * (1.05**2 - 1.03**2)
    assert result.loc[("fund", 2), "value"] == pytest.approx(100 * real_tax)
    assert result.loc[("gemel", 2), "value"] == pytest.approx(100 * real_tax)
    # 15% of the interest, paid every year.
    assert result.loc[("deposit", 2), "value"] == pytest.approx(100 * (1 + 0.05 * 0.85) ** 2)
    assert result.loc[("fund", 2), "real_value"] == pytest.approx(100 * real_tax / 1.03**2)
    assert result.loc[("fund", 2), "gap"] == pytest.approx(0.0)
    assert result.loc[("fund", 0), "value"] == pytest.approx(100.0)


def test_cash_vehicles_real_tax_never_refunds():
    # Inflation above the rate: a real loss, so no tax at all.
    result = calc.cash_vehicles(amount=100.0, years=1, rate=0.02, inflation=0.05, fund_fee=0).set_index(["vehicle", "year"])
    assert result.loc[("fund", 1), "value"] == pytest.approx(102.0)


def test_pension_fees_one_year_by_hand():
    # One year, flat salary, no return: 12 deposits of 1,000 less 2%, then 1% of the balance a year.
    result = calc.pension_fees(
        age=30, retire_age=31, salary=10_000, contribution=0.1, salary_growth=0, real_return=0, track="fixed",
        fee_deposit=0.02, fee_balance=0.0, coefficient=200,
    )
    yours = result[result["scenario"] == "yours"].set_index("age")
    assert yours.loc[30, "balance"] == 0
    assert yours.loc[31, "balance"] == pytest.approx(12 * 980)
    assert yours.loc[31, "pension"] == pytest.approx(12 * 980 / 200)
    none = result[result["scenario"] == "none"].set_index("age")
    assert none.loc[31, "balance"] == pytest.approx(12_000)


def test_pension_fees_balance_fee_compounds():
    # A single deposit kept for many years loses about the balance fee every year.
    flat = dict(age=30, retire_age=50, salary=1000, contribution=0.1, salary_growth=0, real_return=0, track="fixed", fee_deposit=0)
    cheap = calc.pension_fees(fee_balance=0.0, **flat)
    dear = calc.pension_fees(fee_balance=0.01, **flat)
    assert dear["balance"].iloc[20] < cheap["balance"].iloc[20]
    steps = calc.pension_fees_steps(**flat, fee_balance=0.0).set_index("step")
    assert steps.loc["deposit_1", "share"] == pytest.approx(0.01)
    assert steps.loc["balance_01", "balance_loss"] > 0


def test_pension_age_track_steps_down_with_age():
    stocks, other = calc.PENSION_STOCK_RETURN, calc.PENSION_OTHER_RETURN
    assert calc.pension_track_return("age", 30) == pytest.approx(0.53 * stocks + 0.47 * other)
    assert calc.pension_track_return("age", 55) == pytest.approx(0.38 * stocks + 0.62 * other)
    assert calc.pension_track_return("age", 62) == pytest.approx(0.22 * stocks + 0.78 * other)
    assert calc.pension_track_return("sp500", 62) == pytest.approx(stocks)
    assert calc.pension_track_return("fixed", 62, 0.04) == pytest.approx(0.04)
    # One year at 49 and one at 50: the two yearly returns differ.
    flat = dict(age=49, retire_age=51, salary=10_000, contribution=0.1, salary_growth=0, fee_deposit=0, fee_balance=0)
    age = calc.pension_fees(track="age", **flat)
    fixed = calc.pension_fees(track="fixed", real_return=calc.pension_track_return("age", 49), **flat)
    assert age["balance"].iloc[1] == pytest.approx(fixed["balance"].iloc[1])
    assert age["balance"].iloc[2] < fixed["balance"].iloc[2]
    with pytest.raises(calc.CalculationInputError):
        calc.pension_fees(track="crypto")


def test_cash_vehicles_inflation_changes_the_ranking():
    table = calc.cash_vehicles_inflation(years=4, rate=0.04, fund_fee=0.002, makam_cost=0.001)
    assert table["best"].iloc[0] == "makam"
    assert table["best"].iloc[-1] == "fund"


# --- Young couples: stage B ----------------------------------------------------


def test_buy_vs_rent_flat_world_differs_by_the_rent():
    # No interest, returns, inflation, fees or growth: owning for a year leaves exactly the rent paid.
    result = calc._buy_rent_wealth(
        0.0, price=1_000_000, rent=1_000, years=1, rate=0.0, term=30, inflation=0.0, rent_growth=0.0,
        invest_return=0.0, upkeep=0.0, buy_costs=0.0, sell_costs=0.0, ltv=0.5, buyer="first",
    )
    assert result["upfront"] == pytest.approx(500_000)
    assert result["buy"] - result["rent"] == pytest.approx(12 * 1_000)


def test_buy_vs_rent_breakeven_and_horizons():
    frame = calc.buy_vs_rent()
    assert frame["buy_advantage"].is_monotonic_increasing
    breakeven = frame[frame["point"] == "breakeven"].iloc[0]
    assert abs(breakeven["buy_advantage"]) < 50
    assert 0 <= breakeven["history_share"] <= 1
    horizons = calc.buy_vs_rent_horizons()
    # Transaction costs spread over more years: a longer stay needs less growth.
    assert horizons["breakeven_real"].iloc[0] > horizons["breakeven_real"].iloc[-1]
    with pytest.raises(calc.CalculationInputError):
        calc.buy_vs_rent(years=0)


def test_prepay_without_interest_or_returns_is_a_wash():
    frame = calc.prepay_vs_invest(rate=0.0, inflation=0.0, horizon=5)
    flat = frame[frame["return_real"].abs() < 1e-12].iloc[0]
    assert flat["invest_advantage"] == pytest.approx(0, abs=1e-6)
    # A fee on prepaying helps investing.
    with_fee = calc.prepay_vs_invest(rate=0.0, inflation=0.0, horizon=5, fee=0.05)
    assert with_fee[with_fee["return_real"].abs() < 1e-12].iloc[0]["invest_advantage"] > 0
    history = calc.prepay_history(horizon=10)
    assert {"invest_advantage", "breakeven_real", "saving"} <= set(history.columns)
    # Tax on the gain: investing must beat the mortgage's real rate.
    assert history["breakeven_real"].iloc[0] > (1.05 / 1.02 - 1)


def test_family_gift_beats_loan():
    frame = calc.family_help(equity=400_000, income=20_000, help_amount=200_000).set_index("help")
    assert frame.loc["gift", "max_price"] > frame.loc["none", "max_price"]
    assert frame.loc["loan", "max_price"] < frame.loc["gift", "max_price"]
    assert frame.loc["loan", "family_payment"] == pytest.approx(200_000 / 120)
    same = calc.family_help(help_amount=0).set_index("help")
    assert same.loc["loan", "max_price"] == pytest.approx(same.loc["none", "max_price"])


def test_kids_savings_deposits_and_grants():
    frame = calc.kids_savings(withdraw_age=21, parent_addition=True, born_2017=True)
    last = frame[(frame["track"] == "bank") & (frame["age"] == 21)].iloc[0]
    assert last["deposits"] == pytest.approx(116 * 12 * 18 + 291 * 2 + 582)
    high = frame[(frame["track"] == "high") & (frame["age"] == 21)].iloc[0]
    assert high["after_tax_parent"] > high["after_tax_no_parent"]
    early = calc.kids_savings(withdraw_age=18, born_2017=False)
    assert early[(early["track"] == "bank") & (early["age"] == 18)].iloc[0]["deposits"] == pytest.approx(116 * 12 * 18 + 582)


def test_hishtalmut_ceiling_and_liquidity():
    frame = calc.hishtalmut(salary_a=30_000, salary_b=0, balance_a=0, opened_a=5, opened_b=0, years=2, real_return=0, fee=0)
    # Deposits stop at the salary ceiling: 10% of 15,712 a month.
    assert frame["balance_a"].iloc[1] == pytest.approx(12 * 1_571.2)
    assert not frame["liquid_a"].iloc[0] and frame["liquid_a"].iloc[1]
    assert not frame["liquid_b"].any()
    assert frame["available"].iloc[1] == pytest.approx(frame["balance_a"].iloc[1])
