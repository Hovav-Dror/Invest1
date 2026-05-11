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
python scripts/apply_2024_2025_refresh.py
```

The refresh extends:

- `SP500DIV` and `SP500US` through `2026-01-01`, so monthly calculations cover
  the full 2024 and 2025 calendar years.
- `LazyReturns1` for `S&P 500` and `US Small Cap Value` through year-end 2025.

Source details are recorded in `data/sources.json` and referenced from
`data/manifest.json`. The script downloads source CSVs directly unless cached
copies already exist in `/private/tmp`. The SCV annual values use the MSCI USA
Small Cap Value Weighted net USD index factsheet; the S&P monthly series uses
public monthly total-return values and is cross-checked against annual S&P 500
total returns.
