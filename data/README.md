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
