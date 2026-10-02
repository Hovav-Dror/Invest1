# Data audit findings (LazyReturns1, SP500DIV/SP500US)

Audit date: 2026-10-02. Research only: no data or code was changed.

Notation: "data" is the current value in `data/*.parquet`. "pp" means
percentage points. **[uncertain]** marks values that need a second check
before you apply them.

## 0. Where each base series comes from (provenance)

Reconstructed from the original R project at
`/Users/hovav/Documents/R projects/Invest`, specifically `prep rda.R` and
`upmyinterest.R`. This matters because the sources mix gross index returns and
net-of-fee fund returns.

| Series in `LazyReturns1` | Source through 2023 | Type | 2024–2025 refresh source |
| --- | --- | --- | --- |
| S&P 500 | upmyinterest.com/sp500 (= Damodaran through 2015, official S&P TR from 2016) | gross index | official TR (correct) |
| MSCI World ex USA index | upmyinterest.com/msci-world-ex-us (matches the MSCI **gross** factsheet) | gross index | VEA ETF (wrong index, net of fee) |
| NASDAQ100 | upmyinterest.com/nasdaq100 | gross index | QQQ ETF (net) |
| US Small Cap Value | upmyinterest.com/small-cap-value (Paul Merriman / Fama-French-style research series, 1928+) | gross research index | MSCI USA SCV **Weighted, net** |
| REIT | upmyinterest.com/us-real-estate (Dow Jones Select RESI) | gross index | VNQ ETF (different index, net) |
| Gold | upmyinterest.com/gold (price) | price | GLD ETF (net 0.40%) |
| Bitcoin | upmyinterest.com/bitcoin | price | Slickcharts (consistent) |
| 10-Year US Treasury | upmyinterest.com/treasury-10-year: the **mean annual yield**, not a return | yield | IEF total return (wrong concept) |
| Inflation | Shiller CPI (CPI-U NSA), Dec/Dec; 2023 hard-coded 3.35 | CPI | FRED CPIAUCSL (SA), Dec/Dec |
| All other asset classes (US Large Cap, value/growth/mid/small, bonds, PV REIT/Gold columns not used, Precious Metals, Commodities, …) | portfoliovisualizer.com historical asset-class table, transcribed in `prep rda.R` (`Asset_Class_Returns` tribble); every value matches exactly | **mutual-fund/ETF returns, net of expense ratios** (see the PV FAQ) | FinanceCharts ETF proxies, some of them different funds or indexes from PV's |
| Global ex US Stock Market | **0.6 × S&P 500 + 0.4 × MSCI World ex USA** (overwrites PV's real "Global ex-US" column) | composite | same formula |

Sources:
- PV proxy funds: https://www.portfoliovisualizer.com/faq. For example, US Large Cap is VFINX from 1977, Precious Metals is GDX from 2018, Commodities is GSG, and Global ex-US is VGTSX from 1997.
- Original R code: `prep rda.R`, lines that build `Asset_Class_Returns`, `CommissionsTable`, `LazyReturns1a`/`1b`, and `SP500US_CSPX`.

---

## 1. Annual `YearReturn` errors in base assets

### 1a. S&P 500

I compared every year from 1928 to 2025 against Damodaran
(https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html)
and the official S&P 500 total return (Slickcharts
https://www.slickcharts.com/sp500/returns; I confirmed 2019–2021 by search
because the page returned 403 to the fetcher).

| Year | Data | Correct | Diff | Source |
| --- | ---: | ---: | ---: | --- |
| **2021** | **30.92** | **28.71** | +2.21 | Official S&P 500 TR (Slickcharts). Damodaran gives 28.47. The error comes from upmyinterest.com/sp500, which still shows 30.92. |

Other notes:
- 1928–2014 match Damodaran exactly. Damodaran's figures are estimates, not the official S&P TR. For 2011–2014 the official TR is 2.11 / 16.00 / 32.39 / 13.69, while the data has 2.10 / 15.89 / 32.15 / 13.52. All gaps are under 0.3 pp, so this is optional.
- 2015: 1.36 in the data vs. 1.38 official. Negligible.
- 2016–2025 match the official TR, except 2021.

### 1b. MSCI World ex USA index

The 2012–2023 data matches the MSCI **gross** factsheet (USD) to 0.1 pp:
https://www.msci.com/documents/10199/255599/msci-world-ex-usa-index.pdf
(annual performance table, "GROSS RETURNS", Aug 31 2026 edition). The
2024–2025 refresh used VEA, which tracks the FTSE Developed All Cap ex US
index: a different index, including Korea, Canada and small caps.

| Year | Data (VEA) | Correct (MSCI World ex USA gross) | Diff |
| --- | ---: | ---: | ---: |
| 2024 | 3.15 | **5.26** | −2.11 |
| 2025 | 35.17 | **32.55** | +2.62 |

The net variants on upmyinterest are 4.7 and 31.9. Use gross so the series
matches its own history.

### 1c. "Global ex US Stock Market" is not ex-US (structural bug)

In `prep rda.R`:
`Asset_Class_Returns %>% mutate(Global_ex_US_Stock_Market = 0.6*`S&P 500` + 0.4*MSCI_World_ex_USA_index)`.
This line overwrites PV's real Global ex-US column (AQR factor 1986–1996, then
VGTSX). The asset is therefore 60% US. `apply_2024_2025_refresh.py`
(`annual_returns_with_composites`) repeats the same formula. It has the same
values as the "Global" portfolio in every year.

Affected composites:
- Bogleheads Three Funds (30%)
- Bill Bernstein No Brainer (25%)
- Growth (28%), Moderate (21%), Conservative (14%) and Income (7%) portfolios
- Bill Schultheis Coffee house (10%)

Bogleheads Three Funds is therefore about 68% S&P 500.

Correct values: the PV Global ex-US column (1986–2023, below), plus VGTSX for
2024 and 2025 (https://totalrealreturns.com/n/VGTSX).

| Year | Data | PV Global ex-US | | Year | Data | PV Global ex-US |
|---|---:|---:|---|---|---:|---:|
| 1986 | 37.41 | 63.38 | | 2006 | 19.85 | 26.64 |
| 1987 | 13.33 | 30.48 | | 2007 | 8.45 | 15.52 |
| 1988 | 21.04 | 25.66 | | 2008 | −39.21 | −44.10 |
| 1989 | 23.45 | 12.85 | | 2009 | 29.32 | 36.73 |
| 1990 | −10.96 | −24.79 | | 2010 | 12.65 | 11.12 |
| 1991 | 23.10 | 9.48 | | 2011 | −3.46 | −14.56 |
| 1992 | −0.27 | −14.79 | | 2012 | 16.33 | 18.14 |
| 1993 | 19.02 | 29.92 | | 2013 | 27.93 | 15.04 |
| 1994 | 3.84 | 9.76 | | 2014 | 6.55 | −4.24 |
| 1995 | 27.04 | 3.98 | | 2015 | −0.22 | −4.38 |
| 1996 | 16.49 | 4.68 | | 2016 | 8.50 | 4.65 |
| 1997 | 20.90 | −0.77 | | 2017 | 23.02 | 27.40 |
| 1998 | 24.64 | 15.60 | | 2018 | −8.07 | −14.44 |
| 1999 | 23.85 | 29.92 | | 2019 | 28.17 | 21.43 |
| 2000 | −10.70 | −15.61 | | 2020 | 14.28 | 11.16 |
| 2001 | −15.59 | −20.15 | | 2021 | 23.83 | 8.61 |
| 2002 | −19.38 | −15.08 | | 2022 | −16.39 | −16.05 |
| 2003 | 33.02 | 40.34 | | 2023 | 23.21 | 15.38 |
| 2004 | 14.76 | 20.84 | | 2024 | 16.27 | **5.13** (VGTSX) |
| 2005 | 8.90 | 15.57 | | 2025 | 24.80 | **32.06** (VGTSX) |

For 1970–1985, PV has no data. Either drop those rows, or use MSCI World ex
USA for them. No composite that uses this asset starts before 1987, so the
choice does not affect any portfolio. **Decision needed:** this may have been
a deliberate stand-in, but the name and the lazy-portfolio definitions say
ex-US. If you keep the formula, rename the asset.

Estimated impact (all fixes in this report except SCV and the commission fix):

| Portfolio | Starts | CAGR now | CAGR fixed | 2024 now → fixed | 2025 now → fixed |
|---|---|---:|---:|---|---|
| Bogleheads Three Funds | 1987 | 9.82 | 8.86 | 17.67 → 14.32 | 17.79 → 19.97 |
| Bill Bernstein No Brainer | 1987 | 9.38 | 8.59 | 14.27 → 11.38 | 14.71 → 16.43 |
| Growth Portfolio | 1992 | 9.31 | 8.42 | 17.55 → 14.57 | 17.68 → 19.75 |
| Moderate Portfolio | 1992 | 8.28 | 7.62 | 13.14 → 11.08 | 15.06 → 16.65 |
| Conservative Portfolio | 1992 | 7.14 | 6.71 | 8.73 → 7.59 | 12.44 → 13.56 |
| Bill Schultheis Coffee house | 1987 | 8.80 | 8.50 | 9.17 → 8.33 | 11.23 → 12.04 |
| Income | 1992 | 5.90 | 5.69 | 4.33 → 4.10 | 9.82 → 10.46 |
| Ray Dalio All Seasons | 2007 | 6.36 | 6.43 | 6.35 → 7.83 | 13.61 → 14.01 |
| David Swensen Yale Endowment | 2001 | 7.55 | 7.58 | 8.51 → 9.41 | 14.22 → 14.60 |
| Global (60/40) | 1970 | 10.61 | 10.59 | 16.27 → 17.12 | 24.80 → 23.75 |
| ~Ben Felix five-factor | 1995 | 10.12 | 10.09 | 13.95 → 14.61 | 23.01 → 22.12 |

CAGR here is the geometric mean of all `YearReturn` rows (including the first
year), without commission.

### 1d. 2024–2025 values that do not match the series' own source

Rule used: each 2024–2025 value should come from the same source or fund as
that series' history. For PV-sourced assets, that is the PV proxy fund listed
in the PV FAQ. I fetched returns from https://totalrealreturns.com/n/{TICKER}
and checked the method against PV's own 2023 values. Equity funds matched to
0.03 pp (VFINX 26.12 vs PV 26.11, VTSMX 25.87 = 25.87, GSG −5.51 = −5.51,
LSGBX 5.48 = 5.48, GDX 9.98 vs 9.96).

Vanguard bond funds read about 0.3–0.4 pp higher than PV for 2023 (VFISX 3.54
vs 3.15, VFITX 4.07 vs 3.75, VUSTX 3.33 vs 2.99). This is probably the timing
of the December income accrual. **[uncertain ±0.4 for bond funds]**

Rows with a gap above 0.3 pp:

| Asset (in a default portfolio?) | Source of history | Current proxy | 2024 data → correct | 2025 data → correct | Source |
|---|---|---|---|---|---|
| **Precious Metals** (default) | PV: VGPMX, then **GDX** from 2018 | GLTR (physical metals basket) | 20.63 → **10.64** | 87.25 → **154.77** | https://totalrealreturns.com/n/GDX |
| **Commodities** (Dalio) | PV: **GSG** | DBC | 2.18 → **8.52** | 8.10 → **5.93** | https://totalrealreturns.com/n/GSG |
| **MSCI World ex USA index** (default) | MSCI gross | VEA | 3.15 → **5.26** | 35.17 → **32.55** | MSCI factsheet (1b) |
| **REIT** (Coffeehouse, Swensen) | upmyinterest DJ Select RESI | VNQ | 4.81 → **8.0** | 3.25 → **4.4** | https://www.upmyinterest.com/us-real-estate/ |
| **Gold** (Dalio) | upmyinterest gold price | GLD | 26.66 → **27.20** | 63.68 → **64.6** | https://www.upmyinterest.com/gold/ |
| NASDAQ100 | upmyinterest NDX TR | QQQ | 25.58 → **25.88** | 20.77 → **21.0** | https://www.upmyinterest.com/nasdaq100/ |
| **US Large Cap** (Bernstein, Coffeehouse) | PV: **VFINX** | VV | 25.25 → **24.84** | 18.11 → **17.72** | https://totalrealreturns.com/n/VFINX |
| **Emerging Markets** (default) | PV: VEIEX | VWO | 10.59 → **10.81** | 25.61 → **24.59** | https://totalrealreturns.com/n/VEIEX |
| **European Stocks** (default) | PV: VEURX | VGK | 1.87 → 1.88 | 35.84 → **35.23** | https://totalrealreturns.com/n/VEURX |
| Pacific Stocks | PV: VPACX | VPL | 1.68 → **1.14** | 32.66 → **32.92** | https://totalrealreturns.com/n/VPACX |
| **Short Term Treasury** (default) | PV: VFISX | SHY | 3.92 → **3.74** | 4.63 → **5.35** | https://totalrealreturns.com/n/VFISX |
| **Intermediate Term Treasury** (Dalio) | PV: VFITX (5-yr-ish) | IEF (7–10 yr) | −0.64 → **1.39** | 7.72 → **7.57** | https://totalrealreturns.com/n/VFITX |
| **Long Term Treasury** (Dalio, Yale) | PV: VUSTX | TLT | −8.05 → **−6.40** | 4.25 → **5.55** | https://totalrealreturns.com/n/VUSTX |
| **Global Bonds Unhedged** (Growth/Mod/Cons/Income) | PV: LSGBX | BWX | −5.93 → **−2.46** | 7.67 → **8.52** | https://totalrealreturns.com/n/LSGBX |
| Global Bonds USD Hedged | PV: PGBIX | BNDX | 3.56 → **4.86** | 2.87 → **9.32** | https://totalrealreturns.com/n/PGBIX |
| Long Term Corporate Bonds (Vanguard 2045, High Tech) | PV: VWESX | VCLT | −1.89 → **−2.75** | 7.18 → 7.22 | https://totalrealreturns.com/n/VWESX |
| High Yield Corporate Bonds | PV: VWEHX | HYG | 7.97 → **6.35** | 8.60 → **9.37** | https://totalrealreturns.com/n/VWEHX |
| Intermediate Term Tax Exempt | PV: VWITX | MUB | 1.27 → **1.70** | 3.78 → **5.05** | https://totalrealreturns.com/n/VWITX |
| Long Term Tax Exempt | PV: VWLTX | TFI | −0.01 → **1.84** | 3.62 → **3.86** | https://totalrealreturns.com/n/VWLTX |
| US Micro Cap | PV: BRSIX through 2025 | IWC | 13.45 → 14.92 **[uncertain, from search snippet]** | 22.80 → ? **[not found]** | PV FAQ; Yahoo BRSIX |
| 10-Year US Treasury | upmyinterest **mean yield** | IEF return | −0.64 → **4.21** | 7.72 → **4.29** | FRED GS10 annual average: https://fred.stlouisfed.org/series/GS10. 2020–2023 match the data exactly. Upmyinterest shows 4.41 for 2024, which does not match FRED. |

Within 0.3 pp, so no change needed (proxy shown as data / PV fund):
- US Stock Market: 23.81 / 23.61 and 17.10 / 17.01
- US Large Cap Value: 15.96 / 15.85 and 15.27 / 15.13
- US Large Cap Growth: 32.69 / 32.51 and 19.41 / 19.29
- US Mid Cap: 15.31 / 15.10 and 11.62 / 11.53
- US Mid Cap Value: 14.00 / 13.90 and 12.08 / 11.91
- US Mid Cap Growth: 16.38 / 16.28 and 10.72 / 10.56
- US Small Cap: 14.17 / 14.10 and 8.87 / 8.71
- US Small Cap Growth: 16.50 / 16.36 and 8.50 / 8.30
- Intl Developed: 3.15 / 3.03 and 35.17 / 35.19
- Intl Small Cap: VSS, same fund
- Intl Value: EFV, same fund
- Total US Bond: 1.38 / 1.14 and 7.08 / 7.04
- TIPS: 1.65 / 1.75 and 6.77 / 6.78
- Short-Term Investment Grade: 4.91 / 4.98 and 6.77 / 6.75
- Corporate Bonds: LQD, same fund
- Short Term Tax Exempt: 3.36 / 3.13 and 3.67 / 3.96 (borderline)
- Cash: BIL vs 3-month T-bills, under 0.1
- Bitcoin: matches upmyinterest
- S&P 500

Two cases need a second check:
- **"X10 year Treasury"** is PV's synthetic 10-year series built from FRED
  constant-maturity yields. The data uses IEF −0.64 / 7.72, but totalrealreturns
  shows IEF 2025 at **8.04**. Damodaran's synthetic 10-year bond gives −1.64 /
  7.80, but his method differs from PV's (2022: −17.83 vs PV −15.19).
  **[uncertain]**
- **"10-Year US Treasury" is a yield series.** Its 1879–2023 values are average
  yields (for example, 13.91 in 1981). It is not a usable return. Two options:
  (a) keep it as a yield and use 4.21 / 4.29 for 2024–2025, and relabel it in
  the UI; or (b) replace the whole series with Damodaran's T-Bond total returns
  for 1928–2025 (the URL in 1a; 2024 −1.64, 2025 7.80) and drop 1879–1927. No
  composite uses this asset.

Also not verified: **European Small Cap Value**. Its history is the MSCI Europe
Small Cap Value Weighted index (EUR→USD, `European_Small_Cap_Value.R`), but
the 2023–2025 values (14.94 / −0.61 / 32.85) come from DFE, a WisdomTree
dividend-weighted fund and a different index. The consistent proxy is ZPRX
(SPDR MSCI Europe SCV Weighted UCITS) in EUR, converted at the Bank of Israel
EUR/USD cross. I could not fetch it. **[open]**

### 1e. Outlier and consistency checks

- I computed z-scores of `YearReturn` per asset. Every |z| > 3 is a real event: 1979 gold, 1982 bonds, 2008, 2022 bonds, 1933 small-cap value, 2013 Bitcoin (4500%). The exceptions are the yield-series values in 10-Year US Treasury, which are an artifact of using yields.
- There are no duplicate `(Year, Portfolio, CommissionUse)` rows and no year gaps.
- Stored composites equal `sum(weight × asset YearReturn)` exactly in every year.
- `index`, `Index_CPI_US`, `Index_CPI_IL`, `BadYears*` and `Drop*` are internally consistent: a full recompute (section 7) reproduces them to 1e-15.
- **Inflation 2023** is 3.35 for 61 portfolios but **3.3159** for European Small Cap Value. That row came from the refresh's FRED SA Dec/Dec value. Set it to 3.35 and recompute that asset's `CPI_US`/`Index_CPI_US`.
- **Inflation 2024/2025** uses SA CPI (2.8707 / 2.6533). The history is CPI-U NSA Dec/Dec. NSA gives **2.8881 / 2.6771** (CPIAUCNS Dec 2023 306.746, Dec 2024 315.605, Dec 2025 324.054; https://fred.stlouisfed.org/series/CPIAUCNS).
- MSCI World ex USA, Intl Developed, and all three Treasury series have identical 2024–2025 values because they share one proxy. Fixing 1b and 1d removes this.

---

## 2. Monthly S&P 500 series (`SP500US`/`SP500DIV.Real_Total_Return_Price`)

**What the legacy series is.** `prep rda.R`, section "SP500 with Dividends":
- **Up to 2011-01:** Shiller `ie_data` "Price_10", the total-return price (monthly average, 100% dividends). It is converted to nominal with `/first(CPI)*CPI`, so the column is nominal despite its name.
- **From 2011-02:** Yahoo `CSPX.L`, the iShares Core S&P 500 UCITS ETF (accumulating, Irish-domiciled). It is sampled as the **open of the first trading day of each month** and chained onto Shiller at 2011-01-01. CSPX pays 15% US withholding on dividends under the US–Ireland treaty and has a 0.07% TER. That explains the "85% dividends" behaviour. **[TER and withholding from issuer knowledge; not re-fetched]**

**Measured drag.** From the 2012-01 row to the 2024-01 row, the series grows
×4.489. The official S&P TR for 2012–2023 grows ×4.784. That is **−0.53% a
year**. The expected CSPX drag is about 0.15 × ~1.9% yield + 0.07% TER ≈ 0.36%
a year. The remaining ~0.17% is probably open-price sampling or Yahoo data
noise. **[uncertain]** Year-by-year gaps are noisy (−2.3 to +1.7 pp) because
of the first-open sampling.

**2024–2025 rows.** These come from `manual_refresh_returns.json`
(`sp500_monthly_total_return`, YCharts). They are the full official TR:
annual 25.05 / 17.89, which matches the official 25.02 / 17.88.

**Option A (minimal, consistent with the legacy CSPX behaviour).** Subtract
15% of the monthly dividend yield plus the TER:
`r_adj = r − 0.15 × DY/12 − 0.07/12`. DY is the S&P 500 dividend yield at the
start of the month, from multpl
(https://www.multpl.com/s-p-500-dividend-yield/table/by-month, month-end
values; the prior month-end is used).

| Month | Official TR % | DY at start % | Adjusted % |
|---|---:|---:|---:|
| 2024-01 | 1.68 | 1.50 | 1.655 |
| 2024-02 | 5.34 | 1.47 | 5.316 |
| 2024-03 | 3.22 | 1.41 | 3.197 |
| 2024-04 | −4.08 | 1.37 | −4.103 |
| 2024-05 | 4.96 | 1.40 | 4.937 |
| 2024-06 | 3.59 | 1.37 | 3.567 |
| 2024-07 | 1.22 | 1.33 | 1.198 |
| 2024-08 | 2.43 | 1.31 | 2.408 |
| 2024-09 | 2.14 | 1.33 | 2.118 |
| 2024-10 | −0.91 | 1.30 | −0.932 |
| 2024-11 | 5.87 | 1.28 | 5.848 |
| 2024-12 | −2.38 | 1.25 | −2.401 |
| 2025-01 | 2.78 | 1.24 | 2.759 |
| 2025-02 | −1.30 | 1.26 | −1.322 |
| 2025-03 | −5.63 | 1.25 | −5.651 |
| 2025-04 | −0.68 | 1.34 | −0.703 |
| 2025-05 | 6.29 | 1.43 | 6.266 |
| 2025-06 | 5.09 | 1.32 | 5.068 |
| 2025-07 | 2.24 | 1.28 | 2.218 |
| 2025-08 | 2.03 | 1.23 | 2.009 |
| 2025-09 | 3.65 | 1.22 | 3.629 |
| 2025-10 | 2.34 | 1.19 | 2.319 |
| 2025-11 | 0.25 | 1.17 | 0.230 |
| 2025-12 | 0.06 | 1.17 | 0.040 |

The adjusted annual returns are 24.71 (2024) and 17.58 (2025), about 0.3 pp a
year below the official TR.

**Option A′ (most faithful).** Re-pull `CSPX.L` from Yahoo for 2024-01 to
2026-01, using the first-trading-day open, as in `prep rda.R`, and chain from
the 2024-01-01 row. Downloading needs explicit approval.

**Option B (cleaner for teaching).** Replace 2011-02 to 2024-01 with the
official S&P 500 TR, and model withholding explicitly in `invest_core`. This
is a bigger change and breaks parity with the R fixtures.

How to apply option A:
1. Either edit the 24 values in `data/manual_refresh_returns.json`, or add a `dividend_withholding` / `ter` adjustment inside `extend_sp500_monthly()` in `scripts/apply_2024_2025_refresh.py`. The second keeps the sourced values intact.
2. Rerun `python scripts/apply_manual_data_refresh.py`. It rewrites rows after 2024-01-01 in both monthly files. This is idempotent because the base row is 2024-01-01.
3. Update `docs/methodology.md` limitation 1.

---

## 3. Double fee charge under `CommissionUse=True`

`CommissionUse=True` applies `growth = (1+r)·(1−c)`, where `c` is the
per-asset `commission` from `CommissionsTable` (0.07–1.22%). This is correct
only when `r` is gross. It double-charges whenever `r` is already net of a
fund expense ratio. This is broader than 2024–2025:

- **PV-sourced assets are fund returns in every year** (per the PV FAQ). For example, US Large Cap is VFINX from 1977, Total US Bond is VBMFX, and Short/Intermediate/Long Treasury are VFISX/VFITX/VUSTX from 1992/1992/1987. Their whole history is already net of the funds' fees. The 2024–2025 ETF proxies are **consistent** with that history. Adding back the ER only for 2024–2025 would create a break.
- **Gross-index assets** are S&P 500, MSCI World ex USA, NASDAQ100, US SCV, REIT (DJ), Gold price and Bitcoin. Here the problem exists only where 2024–2025 used an ETF: VEA, QQQ (0.20%), VNQ (0.13%) and GLD (0.40%), plus the net SCV index. Applying the section 1 fixes (index values) solves this for those assets.

Size of the double charge: about the fund ER each year. The values below are
approximate expense ratios for the fund in use. **[uncertain: from issuer
knowledge, not re-fetched]**

- VFINX 0.14
- VTSMX 0.14
- VIVAX/VIGRX 0.17
- VIMSX/VMVIX/VMGIX 0.17–0.19
- NAESX 0.17
- VISGX 0.19
- VGTSX 0.17
- VTMGX 0.07
- VEURX/VPACX 0.10
- VEIEX 0.29
- VFISX/VFITX/VUSTX 0.20
- VBMFX 0.15
- VIPSX 0.20
- LSGBX ~0.70
- PGBIX ~0.50
- VFSTX 0.20
- LQD 0.14
- VWESX 0.21
- VWEHX 0.23
- VWSTX/VWITX/VWLTX 0.17
- GDX 0.51
- GSG 0.75
- GLD 0.40

Two cases are worse. `commission` for Gold is 1.22, an Israeli fund fee,
applied on top of GLD's 0.40 from 2005. For Global Bonds Unhedged, LSGBX's
fee is already larger than the 0.30 assumed.

Proposed fix, in order of preference:
1. Add an `embedded_fee` per asset and year range to a new config, for example `data/fee_basis.json`, using the PV FAQ periods. In the CommissionUse branch, use `c_eff = max(c − embedded_fee, 0)`. The UI meaning becomes "total cost = c".
2. Simpler alternative: document that `CommissionUse=False` already includes fund fees for PV assets, and set `commission` to `max(c − typical ER, 0)` per asset in `PortfoliosStructure`. Composite `commission` is the weighted sum, so recompute it too.

Either way, recompute `index` and everything downstream for `CommissionUse=True` (section 7).

---

## 4. US Small Cap Value: mixed index types

- 1928–2023: upmyinterest.com/small-cap-value (https://www.upmyinterest.com/small-cap-value/). This is Paul Merriman's research series (Fama/French-style, gross, no costs; source description per upmyinterest's article and search results). **[uncertain about the exact underlying index]**
- 2024–2025: MSCI USA Small Cap Value **Weighted, net** (9.70 / 13.71). I confirmed these against the MSCI factsheet: https://www.msci.com/documents/10199/83700218-af0a-4993-b962-00de11158106. Upmyinterest itself switched to the **MSCI US Small Cap Value** index from 2024, at **8.8 / 10.7**.
- `US_Small_Cap_Value_Monthly` is a third series: PV, Fama-French until 1998 and then VISVX, net of fees. Its annual returns match PV exactly, and differ from the annual SCV by up to 30 pp. For example, 2021 is 27.96 vs 42.8 and 2003 is 37.19 vs 67.1. `invest_core` does not use it at present.

Net vs gross impact: MSCI USA indexes use 30% withholding in the net
variant. With a dividend yield of about 1.9–2.0% (factsheet 1.93%), gross ≈
net + ~0.6 pp. The estimated gross values are **~10.3 (2024) and ~14.3
(2025)**. **[estimate; fetch the MSCI gross factsheet to confirm]**

Proposal, decision needed:
- (a) Keep the upmyinterest continuation (8.8 / 10.7). This is the same provider that supplies 1928–2023, which gives the simplest provenance.
- (b) Use the MSCI SCV Weighted **gross** values, which match the user's USSC/ZPRV ETF. Document the splice in `sources.json`.

Do not mix net and gross. The current 9.70 / 13.71 is net, so it understates
the gross convention by about 0.6 pp a year. Affected: Coffeehouse (10%), SF1
(20%), Merriman (25%), Ben Felix (20%), and the S&P-vs-SCV heatmap and
after-tax views.

---

## 5. CPI issues

### 5a. Israeli CPI 2025: the repeated values are genuine

The CBS series 120010 values (Average 2024 = 100, cached at
`/private/tmp/cpi_il.csv` from
https://api.cbs.gov.il/index/data/price?id=120010&format=csv&...) show real
repeats:

| Month | Base 2024 | Monthly % (CBS) | Data (old base) |
|---|---:|---:|---:|
| 2025-01 | 101.5 | +0.6 | 109.027917 |
| 2025-02 | 101.5 | 0.0 | 109.027917 |
| 2025-03 | 102.0 | +0.5 | 109.565000 |
| 2025-04 | 103.1 | +1.1 | 110.746583 |
| 2025-05 | 102.8 | −0.3 | 110.424333 |
| 2025-06 | 103.1 | +0.3 | 110.746583 |
| 2025-07 | 103.5 | +0.4 | 111.176250 |
| 2025-08 | 104.2 | +0.7 | 111.928167 |
| 2025-09 | 103.6 | −0.6 | 111.283667 |
| 2025-10 | 104.1 | +0.5 | 111.820750 |
| 2025-11 | 103.6 | −0.5 | 111.283667 |
| 2025-12 | 103.6 | 0.0 | 111.283667 |
| 2026-01 | 103.3 | −0.3 | 110.961417 |

The conversion is old = new × 107.41667 / 100. 107.41667 is the mean of the
twelve published 2024 values in base Average 2022. The data equals this
exactly. **No correction is required.**

Minor: the official CBS linking coefficient may differ in the 3rd–4th digit
because it is computed from unrounded indexes. The effect is under 0.02%.
**[I could not retrieve the official coefficient]** Chaining by CBS monthly
percent changes instead gives Jan 2025 = 108.4 × 1.006 = 109.050, which is
within rounding of the published values.

### 5b. US CPI (`SP500US.CPI_US`)

The legacy column is CPI-U **NSA** (Shiller). Compared with FRED CPIAUCNS, it
equals the official value exactly through 2023-07, except 2023-03. Those rows
and 2023-08 to 2023-12 are Shiller's preliminary estimates, or are chained
with SA changes. The refresh then appended **SA** CPIAUCSL from 2024-02 and
left 2024-01 missing. The result mixes SA and NSA and inserts a level jump at
the splice. The legacy 2023-12 value is 0.78% too high.

Proposed values: official CPIAUCNS from
https://fred.stlouisfed.org/series/CPIAUCNS. Replace these rows:

| Date | Data | Correct (CPIAUCNS) |
|---|---:|---:|
| 2023-03 | 301.675 | 301.836 |
| 2023-08 | 305.982 | 307.026 |
| 2023-09 | 306.1275 | 307.789 |
| 2023-10 | 307.905424 | 307.671 |
| 2023-11 | 308.203701 | 307.051 |
| 2023-12 | 309.137570 | 306.746 |
| **2024-01** | **NaN** | **308.417** |
| 2024-02 … 2026-01 | SA values | NSA: 310.326, 312.332, 313.548, 314.069, 314.175, 314.540, 314.796, 315.301, 315.664, 315.493, 315.605, 317.671, 319.082, 319.799, 320.795, 321.465, 322.561, 323.048, 323.976, 324.800, **324.461**\*, 324.122, 324.054, 325.252 |

\*BLS did not publish October 2025 CPI because of the federal shutdown. The
value shown is the geometric interpolation √(324.800 × 324.122). The current
SA value, 324.654, was linearly interpolated by the script.

How to apply:
1. In `load_cpi_us()`, switch `us_cpi` in `manual_refresh_returns.json` and `sources.json` to `CPIAUCNS`. Use geometric interpolation.
2. In `extend_sp500_monthly()`, also overwrite `CPI_US` for SP500US rows from 2023-03 through 2024-01.
3. In `extend_lazy_returns()`, Inflation then becomes NSA Dec/Dec: 2.8881 / 2.6771.
4. Remove the "interior gap 2024-01" note in `docs/methodology.md`.

---

## 6. Other observations

- In `manual_refresh_returns.json`, three Treasury series and two "developed ex-US" series point to one proxy each. See 1d.
- The UpMyInterest 2019-2021 High Tech Portfolio starts in 2011 with 5% Bitcoin (+4500% in 2013, giving a composite +246%). It is a valid computation but dominates any chart that includes it.
- `Inflation` is listed as a "portfolio" with commission 0.01. That is harmless, but it means CommissionUse rows show inflation minus 0.01%.
- `docs/source_baseline.md` and `data/README.md` say the S&P 500 monthly data is total return. It is CSPX-like (85% dividends) from 2011-02 to 2024-01. Update the docs.

---

## 7. How to apply the annual corrections (scripts and recompute)

**Can `apply_2024_2025_refresh.py` be reused for older years? No, not as is.**
`extend_lazy_returns()` takes `previous = last row before min(returns)` and
then iterates **only over the years listed** for that portfolio. It replaces
only `(portfolio, year)` pairs in the config. Suppose you added
`"S&P 500": {"2021": 28.71, "2024": …}`. It would chain 2024 straight from
2021, and leave the old 2022 and 2023 rows with stale `index` values. It also
recomputes Inflation from FRED SA for the listed years, and hard-codes Global
ex US as 0.6/0.4.

Its `_recalculate_drawdowns()` is correct and reusable. It reproduces the R
`BadYears`/`Drop` logic exactly.

**Validated full recompute.** I tested this against the current parquet. It
reproduces `index`, `Index_CPI_US`, `Index_CPI_IL`, `BadYears*` and `Drop*`
for all 5,792 rows to under 1e-15 relative error. It mirrors `prep rda.R`:
`contains("index")` normalisation to the first non-NA value, and `CPI_US` as
an un-normalised cumulative product.

```python
from apply_2024_2025_refresh import _recalculate_drawdowns

def recompute_lazy(lazy):
    out = []
    for (p, c), g in lazy.groupby(["Portfolio", "CommissionUse"], sort=False):
        g = g.sort_values("Year").copy()
        growth = (1 + g.YearReturn / 100) * ((1 - g.commission / 100) if c else 1)
        idx = growth.cumprod()
        cpi_us = (1 + g.Inflation / 100).cumprod()
        g["CPI_US"] = cpi_us                      # stored un-normalised
        g["index"] = idx / idx.iloc[0]            # first row = 1 (base)
        ius = idx / cpi_us
        g["Index_CPI_US"] = ius / ius.iloc[0]
        iil = idx / g.CPI_IL * g.USD
        g["Index_CPI_IL"] = iil / iil.dropna().iloc[0]
        out.append(g)
    return _recalculate_drawdowns(pd.concat(out, ignore_index=True))
```

Suggested pipeline. It would be a new script, for example
`scripts/apply_historical_corrections.py`, run after the 2024–2025 refresh, or
folded into it.

1. Load a new `data/historical_corrections.json` with `{asset: {year: value}}` overrides and source URLs:
   - S&P 500 2021
   - Global ex US 1986–2025 (and the 1970–1985 decision)
   - All of the 2024/2025 changes above
   - Inflation 2023 for European SCV, and NSA 2024/2025
   - The SCV choice
2. Set `YearReturn` for those base rows. This applies to both `CommissionUse` values.
3. Recompute every composite `YearReturn = Σ weight × asset YearReturn` for every year where all components exist. Use `PortfoliosStructure`, with `_` replaced by a space. Remove the hard-coded 0.6/0.4 "Global ex US" in `annual_returns_with_composites()`. "Global" (60/40) remains a structure composite and is recomputed automatically.
4. If you adopt the fee fix in section 3, update `commission` per asset and composite (weighted).
5. Run `recompute_lazy()` over the whole table. This updates `index`, `Index_CPI_US`, `Index_CPI_IL`, `CPI_US`, `BadYears*` and `Drop*` for every row, not only changed years. Every later index value depends on the changed year.
6. Record the new sources in `sources.json` and the manifest. Rerun `scripts/validate_data_refresh.py --through-year 2025`. Re-baseline any tests in `tests/` that pin portfolio numbers. R-parity fixtures for S&P 500 2021 and Global ex US composites will change on purpose.

Monthly fixes (sections 2 and 5b) go through `extend_sp500_monthly()` as
described. Nothing in `LazyReturns1` depends on the monthly files.
