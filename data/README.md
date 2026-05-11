# Server Data

This directory contains Python-friendly, server-only exports of the source
Shiny data in `/Users/hovav/Documents/R projects/Invest/Invest.rda`.

Regenerate the Parquet files from the repo root:

```sh
Rscript scripts/export_r_data.R
```

Optional arguments:

```sh
Rscript scripts/export_r_data.R "/path/to/source/Invest" "data" "tests/fixtures/r_outputs/metadata.json"
```

The exporter validates object names, shapes, columns, and date bounds against
the Phase 1 fixture metadata before writing:

- `LazyReturns1.parquet`
- `PortfoliosStructure.parquet`
- `SP500DIV.parquet`
- `SP500US.parquet`
- `US_Small_Cap_Value_Monthly.parquet`
- `manifest.json`

The original `.rda` file is not copied into this repo and should not be served
as a frontend/static asset.

## 2024/2025 Refresh

The migrated parquet data has an explicit post-export refresh for completed
2024 and 2025 data:

```sh
python scripts/apply_manual_data_refresh.py
python scripts/validate_data_refresh.py --through-year 2025
```

The refresh values live in `data/manual_refresh_returns.json`. For the next
annual update, add the completed year to `target_years`, add 12 monthly S&P 500
total-return values, add each direct asset-class annual return under
`annual_returns`, update the source coverage text, and rerun the two commands
above with the new `--through-year`.

The refresh extends:

- `SP500DIV` and `SP500US` through `2026-01-01`, so monthly calculations cover
  the full 2024 and 2025 calendar years.
- `LazyReturns1` through year-end 2025 for all 62 migrated portfolios/assets.
  Direct asset-class series use sourced annual returns or ETF/crypto proxies,
  and composite portfolios are recalculated from the original
  `PortfoliosStructure` weights when every component has a refreshed return.

Source details are recorded in `data/sources.json` and referenced from
`data/manifest.json`. Monthly CPI and FX sources are read from source CSVs
directly unless cached copies already exist in `/private/tmp`; annual return
values are recorded explicitly in `data/manual_refresh_returns.json`. The SCV
annual values use the MSCI USA Small Cap Value Weighted net USD index
factsheet; the remaining refreshed
asset classes use documented ETF/crypto proxies, including FinanceCharts
total-return pages, BlackRock MEAR calendar-year returns for short municipal
bonds, and Slickcharts Bitcoin yearly returns. The S&P monthly series uses
public monthly total-return values and is cross-checked against annual S&P 500
total returns.
