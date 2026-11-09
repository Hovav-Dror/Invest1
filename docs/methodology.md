# Calculation methodology (version 2.0.0)

This document records the rules the calculations follow, why version 2 changed
them, and which data limitations remain. The code is in
`invest_core/calculations.py`; hand-computed examples for each rule are in
`tests/test_calculations.py`.

The site is an educational comparison tool. The tax model is a simplified
illustration of Israeli rules, not a tax calculation for any individual.

## Dates

### Monthly data (`SP500DIV`, `SP500US`)

Each monthly row is a boundary. The S&P 500 total return level on that row was
sampled differently in two eras:

| Rows | Price on row dated `d` | FX and CPI used |
| --- | --- | --- |
| Up to 2011-01 | Shiller monthly average for month `d` | Same row (month `d`) |
| From 2011-02 | First observation of month `d`, that is, the end of month `d-1` | Previous row (month `d-1`) |

The source FX column holds the Bank of Israel rate at the **end** of month `d`
(for example 3.802 on the 2008-12 row, the rate on 31 December 2008). CPI
columns hold the index for month `d`. Version 1 used them on the same row in
every era. From 2011 that paired each month's stock move with the following
month's currency move. `monthly_market()` applies the table above.

The split comes from the data itself. From 2011 the stock/FX monthly
correlation is -0.60 with the previous-row rule and +0.05 with the same-row rule;
up to 2010 the same-row rule fits better (-0.30 vs -0.07). Monthly returns
before 2011 have an autocorrelation of 0.25, which is typical of monthly
averages; after 2011 it is -0.15.

Interior CPI gaps are filled geometrically. The only one in the data is US CPI
for 2024-01.

### Annual data (`LazyReturns1`)

`YearReturn` is the return during the calendar year. `CPI_US`, `CPI_IL` and
`USD` are year-end values. In each portfolio's first row the `index` columns
equal 1: it is the base for later years. Portfolio calculations start from
the year-end before `year_start`, or the first available year. US-versus-world
comparisons compound every `YearReturn` row from a base of 1.

## Tax model

* Rate: 25% of the real gain: the sale value minus the cost basis indexed by
  Israeli CPI.
* A loss is never refunded. Realized real losses are carried forward and offset
  later gains.
* Periodic realization ("every 1/6/12 months"): the whole position is sold
  exactly every N months, tax is paid, and the net proceeds are reinvested as
  the new cost basis.
* Every plotted point shows what would remain after selling everything at that
  date, so all lines are comparable at every point.
* Partial sales (self-managed pension withdrawals) pay tax on the sale's share
  of the gain, and reduce the cost basis proportionally.
* Dollar method (`tax_us_vs_il`, small-cap value after tax): 25% of the dollar
  gain converted at the sale exchange rate, capped at 25% of the nominal shekel
  gain.

## Fees

An annual fee of `f`% is charged monthly as `(1 - f/100)^(1/12)`, so one year
removes exactly `f`%. No fee is charged at the entry date.

## Per calculation

| Endpoint | What it computes | Version 2 changes |
| --- | --- | --- |
| `tax_events` | S&P 500 in shekels: tax once at the end vs. selling every 1, 6, 12 months | FX/CPI alignment; no refund on losses; loss carry-forward; sales exactly every N months; final tax included in every line |
| `commission_tax`, `commission_effect` | Same, with an annual management fee | As above; fee no longer charged twice in sale months; `SP500_in_NIS` is now the index normalized to the initial amount |
| `sp500_risk` | Annualized return of every N-year window | Now real (divided by US CPI). The source column `Real_Total_Return_Price` is nominal despite its name |
| `portfolio_summary` | CAGR, volatility, worst drop, longest underwater period | Volatility and drawdown include the first year after the base. Underwater period: the longest run of years below a previous peak, until the year it is regained (an unrecovered run ends at the last year); it used to count from each purchase date to the last year below cost, which overstated it after interim recoveries |
| `portfolio_over_time` | Value, annual return, CAGR since start, rolling CAGR | CAGR uses each row's elapsed years (it used one constant); rolling windows include the first year |
| `us_world_rolling`, `us_global_rolling` | S&P 500 minus ex-US (or 60/40) in rolling 5/10/15-year growth | Windows without enough history are empty instead of 0 |
| `global_vs_sp500_heatmap`, `sp500_scv_heatmap` | Every start/end pair up to N years | `year_end` works for the global heatmap; pairs need both series |
| `sp500_scv_after_tax` | Rolling real CAGR after tax at the end | S&P 500 tax is computed in nominal shekels (it subtracted a real amount from a nominal value) |
| `kupat_gemel` | Provident fund vs savings policy vs self-managed | FX/CPI alignment; no entry-date fee. At 60 the fund converts to a tax-exempt annuity, so from then on it is the untaxed age-60 balance, CPI-linked |
| `kupat_gemel_pension` | Annuity from 60 vs equal withdrawals from a self-managed portfolio | Proportional cost basis on each sale; stops at zero and reports `IIbShortfall`; the annuity can start immediately for ages over 60 |
| `independent_commissions`, `tax_us_vs_il` | Self-managed costs: conversion spread, broker commission, custody fee | Share count fixed at purchase; dollar-method tax uses the sale exchange rate |
| `trinity` | Fixed real withdrawal by start year | Balances stop at zero (they went negative); `depleted_year` added; the start year's own return is applied |
| `affordability` | Highest apartment price by down payment. Renovation comes out of the equity first; the rest pays the part of the price above the mortgage, transaction costs (`costs` of the price) and purchase tax (2026 brackets, sole or additional apartment). The price is the highest that meets both an LTV limit (`price * (1 - ltv + costs) + tax <= cash`, LTV by buyer: 75% first, 70% upgrade, 50% investor) and an income limit (`price * (1 + costs) + tax <= cash + max_loan`, where `max_loan` is a Shpitzer loan whose payment is `pti` of net income), found by bisection. Marks today, after a portfolio drop, and the kink where the limits meet. Used by two pages: how much apartment you can buy, and what a drop just before buying does | New. No historical data |
| `down_payment`, `down_payment_ladder` | For every start month from 1986-02: a lump sum split between stocks (0.1% fee) and cash, rebalanced monthly, optionally gliding to all cash. Stocks: the S&P 500 in shekels with dividends (`market_index=sp500`), or Israeli shares (`israel`: the TASE general index to 2016-08, then TA-125, both price indices, plus a constant 2.5% dividend yield). Cash: a money-market fund at the cash rate less 0.3% (`cash_kind=fund`), or CPI-linked with no real interest (`linked`). At purchase: 25% tax on the real gain (no tax on rebalancing), divided by the growth of dwelling prices. Optional waiting: only if at the planned date the portfolio (shekels, before tax) is 10% or more below its peak since the start; buy when it is back at that peak, up to N years, or in the last month with data, so every setting covers the same start months. The ladder summarizes several stock shares | New. Monthly data in `data/young_couples_monthly.parquet`, built by `scripts/build_young_couples_data.py` (sources in `data/raw/README.md`). Dwelling prices: CBS dwelling index from 1994, before that the CPI component "owner-occupied housing services", which until 1998 followed dwelling prices. Cash rate: Bank of Israel rate from 1994-02, one-month makam yield before (Bank of Israel annual reports; 1986, 1987 and 1991-04 to 1991-12 are annual averages). At boundary `d` dwelling and Israeli share indices are month `d-1`, and cash earns month `d`'s rate. The earlier wait rule (wait whenever the mix was behind all cash) also waited without any fall, for example into the 2008 crash, and dropped the last start months for longer waits |
| `homes_vs_stocks`, `homes_vs_stocks_episodes` | Dwelling prices next to the S&P 500 in shekels and Israeli shares (TASE general index, then TA-125 from 2016-09; a price index), from 1986, real by default, with 12-month changes. Episodes: every fall of 20% or more from a stock peak to the low before the peak is regained, with the dwelling price change over the same months and the 24 months after the low, and the cash rate at both ends | New. Same data and boundary convention as `down_payment` |
| `cash_vehicles`, `cash_vehicles_inflation` | A lump sum held as cash at a fixed rate and inflation, by vehicle and year: money-market fund and provident fund for investment (rate less the fee, 25% of the real gain at withdrawal, no refund), bank deposit and direct makam (rate less the spread or cost, 15% of the nominal interest every year as they roll over). The second table repeats the last year for inflation from 0% to 5% | New. No historical data. The 15% nominal tax on a directly held makam is the rule for unlinked shekel bonds (section 125C of the Income Tax Ordinance) |
| `pension_fees`, `pension_fees_steps` | Pension balance by age in today's shekels: monthly deposits of a share of a salary growing above inflation, less a fee on deposits, a real return less a fee on the balance (charged monthly so a year removes the annual rate). The return follows the investment track: age-based by default (stock share 53% under 50, 38% at 50–60, 22% from 60, with 5% a year above inflation on stocks and 2% on the rest), S&P 500 (all stocks, 5%), bonds (2%), or a fixed return. Compares your fees with a default fund (1% / 0.22%, the 2021 tender), the legal cap (6% / 0.5%) and no fees; pension = balance / conversion coefficient. Steps: the cost of 0.1% more on the balance and 1% more on deposits | New. No historical data, no insurance component, no career breaks |

## Data corrections

`scripts/apply_data_corrections.py` applies `data/data_corrections.json` after
the 2024–2025 refresh. Evidence and sources for every value are in
`docs/data_audit_findings.md`. Applied:

* S&P 500 2021 annual return: 28.71% (was 30.92%).
* 2024–2025 annual returns taken from the same index or fund as each series'
  history (for example MSCI World ex USA gross instead of VEA, GDX for precious
  metals, GSG for commodities, the Vanguard funds for Treasuries).
* US inflation and monthly US CPI: CPI-U not seasonally adjusted throughout,
  including the missing January 2024 value.
* Monthly S&P 500 2024–2025: adjusted like the 2011–2023 series (15% dividend
  withholding and a 0.07% fund fee), about 0.3% a year below the index.
* "10-Year US Treasury" is an average-yield series; 2024–2025 now follow that
  definition.
* "Global ex US Stock Market" is the real ex-US series (Portfolio Visualizer:
  AQR data 1986–1996, VGTSX from 1997). The original data defined it as
  0.6 × S&P 500 + 0.4 × MSCI World ex USA, so Bogleheads, Bernstein,
  Coffeehouse and the Growth/Moderate/Conservative/Income portfolios were
  mostly US. 1970–1985 use MSCI World ex USA; no portfolio uses those years.
* Small-cap value 2024–2025: upmyinterest (the provider of the 1928–2023
  history), 8.8% and 10.7%.
* Fund fees are no longer charged twice. `commission` in `LazyReturns1` is the
  fee charged on top of the source return: the assumed total fee
  (`PortfoliosStructure.commission_i`) minus the fund expense ratio already
  inside the return in that year (`data/fee_basis.json`), never below zero;
  composites use the weighted sum. Expense ratios are current values, so early
  years slightly understate the embedded fee.

## Known data limitations

These still need a decision or more data:

1. **European Small Cap Value 2023–2025** and **US Micro Cap 2025** come from
   proxies that could not be verified.
2. **Annual resolution.** Drawdowns and underwater periods use year-end values,
   so falls within a year (such as 2008 or March 2020) look smaller.
3. **Overlapping windows.** Rolling-window percentages count heavily
   overlapping monthly windows, so they are not independent observations.
4. **Rebalancing.** Composite portfolios are weighted averages of annual
   returns: annual rebalancing at no cost or tax.
5. **Dividend tax.** The self-managed models reinvest dividends without Israeli
   tax or US withholding beyond what is in the source series.
6. **US inflation in Trinity.** Trinity uses US CPI, as in the original study,
   not Israeli CPI or shekel returns.

## Result metadata

Every API result includes a `metadata` object (`invest_core/methodology.py`):
calculation and data versions (the data version is a SHA-256 of the Parquet
files), the requested and computed periods, currency and inflation basis,
whether tax and fees are included, the model assumptions and the data warnings
that apply to that result. The site shows the assumptions and warnings under
each screen, in a collapsed "הנחות ומגבלות הנתונים" section.

`portfolio_summary` and `portfolio_over_time` accept `common_period=true`:
every selected portfolio then starts at the latest first year among them, so
all cover the same years. The default (`false`) keeps each portfolio's own
history. The portfolio screen exposes this as "אותה תקופה לכל התיקים".

An independent calculation audit from 2026-09-30 reached largely the same
corrections; its notes, tests and alternative monthly-alignment data repair
are kept on the `wip/calc-audit-2026-09-30` branch. Where the two differed
(monthly FX/CPI alignment, the provident fund at 60, the Trinity start year),
the rules above were kept.
