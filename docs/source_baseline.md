# Source Baseline

Phase 1 freezes representative outputs from the current Shiny/R implementation before the Python migration begins.

## Source App

- Source directory: `/Users/hovav/Documents/R projects/Invest`
- Source files inspected:
  - `app.R`
  - `HelperFunctions.R`
  - `Invest.rda`
- Source Git HEAD at fixture export: `e2907dd`
- Source working tree at fixture export was dirty. This matches the migration map instruction to treat the current original repo working tree as source of truth unless explicitly changed.

Dirty source entries captured in `tests/fixtures/r_outputs/metadata.json`:

```text
 M .DS_Store
 M Invest.Rproj
 M app.R
 M triniti.R
?? "Copy Invest 2024-01-27.rda"
?? "Invest before 2023-07-21.rda"
?? "MSCI USA Small Cap Value Weighted Index.R"
?? "Madad up to 2023-03-01.csv"
?? "ZPRV USSC.csv"
?? appdelete.R
?? deleteme.R
?? deleteme2.R
```

## Data Objects

The fixture export loads `Invest.rda` once and records object metadata in `tests/fixtures/r_outputs/metadata.json`.

| Object | Shape | Date range | Notes |
| --- | ---: | --- | --- |
| `LazyReturns1` | `5542 x 18` | yearly | Portfolio annual returns and derived metrics |
| `PortfoliosStructure` | `118 x 5` | n/a | Portfolio asset weights and assumed commissions |
| `SP500DIV` | `1837 x 5` | `1871-01-01` to `2024-01-01` | Monthly S&P/dividend/CPI/USD-style data |
| `SP500US` | `1837 x 3` | `1871-01-01` to `2024-01-01` | Monthly S&P US CPI/real return data |
| `US_Small_Cap_Value_Monthly` | `624 x 3` | `1972-02-01` to `2024-01-01` | Monthly US small-cap-value data |

## Fixture Script

Run from the target repo root:

```sh
Rscript scripts/export_r_fixtures.R
```

Optional arguments:

```sh
Rscript scripts/export_r_fixtures.R "/path/to/source/Invest" "tests/fixtures/r_outputs"
```

The script writes deterministic CSV fixtures plus `metadata.json`. Dates are serialized as `YYYY-MM-DD`; missing CSV values are empty. The script intentionally does not start Shiny and does not write into the original R repo.

## Defaults Captured

The exported defaults mirror the visible Shiny UI defaults where practical:

| Area | Default inputs |
| --- | --- |
| Tax events | `1993-01-01` to `2023-01-01`, CPI-adjusted, initial investment `100000` |
| Commission effect / commission plus tax | Same date range and CPI mode, commissions `0`, `0.2`, `0.7` |
| S&P rolling risk | Full `SP500US` date range, `15` years, threshold `4%` |
| Kupat Gemel | Age `40`, start year `1995`, initial investment `70000`, CPI-adjusted, pension conversion months `250` |
| Independent commissions | S&P 500, `2000-01-01` to `2023-01-01`, initial investment `100000`, share price `$50`, FX commission `0.5%`, buy/sell `1` cent/share, min commission `$7.5`, annual fee `0.3%`, CPI-adjusted |
| Portfolio summary / over time | CPI mode `המרה לשקלים ומדד ישראל`, years `1955` to `2023`, commission-adjusted portfolio table, highlighted portfolio `S&P 500` |
| US/global comparisons | S&P 500 vs world ex-US and S&P 500 vs 60/40 US/world mix |
| S&P 500 vs SCV | Israeli-CPI/shekel adjusted, rolling window `15` years, heatmap windows `1` to `20` years |
| Trinity | `US Small Cap Value`, `4%` annual draw, `30` years, base `4000000` |

## Fixture Files

| File | Purpose |
| --- | --- |
| `metadata.json` | Source path, source Git state, data object shapes, column names, date bounds, selected defaults |
| `tax_events_default.csv` | Tax-event scenarios with CPI adjustment |
| `tax_events_no_cpi.csv` | Tax-event scenarios without CPI adjustment |
| `commission_effect_default.csv` | Annual management fee drag for default commissions |
| `commission_tax_default.csv` | Combined tax-event frequency and management-fee scenarios |
| `sp500_risk_default.csv` | Rolling S&P 500 real return risk for the default 15-year window |
| `kupat_gemel_default.csv` | Kupat Gemel / policy / independent investment baseline |
| `kupat_gemel_pension_default.csv` | Kupat Gemel pension-conversion baseline |
| `independent_commissions_default.csv` | Independent-investment fee baseline |
| `tax_us_vs_il_default.csv` | Israeli CPI tax vs dollar/nominal tax comparison baseline |
| `portfolio_summary_default.csv` | Portfolio CAGR, standard deviation, drawdown, bad-years, and 15-year factor |
| `portfolio_over_time_default.csv` | Portfolio accumulated and rolling return series |
| `us_world_rolling_default.csv` | S&P 500 vs MSCI World ex USA rolling differences |
| `us_global_rolling_default.csv` | S&P 500 vs 60/40 US/world mix rolling differences |
| `sp500_scv_rolling_default.csv` | S&P 500 vs US Small Cap Value rolling comparison before tax |
| `sp500_scv_heatmap_default.csv` | All-start/all-end S&P 500 vs SCV comparison fixture |
| `sp500_scv_after_tax_default.csv` | S&P 500 vs SCV after-tax rolling comparison |
| `trinity_default.csv` | Trinity withdrawal simulation by starting year |

## Validation

Validation run on 2026-05-09:

```sh
Rscript scripts/export_r_fixtures.R
```

Result:

```text
Exported R fixtures to /Users/hovav/Documents/Personal Projects/Invest1/tests/fixtures/r_outputs
```

Fixture CSV row counts were checked with:

```sh
wc -l tests/fixtures/r_outputs/*.csv
```

Total CSV lines, including headers: `8247`.

## Notes For Phase 2

- The fixtures are parity targets for Python calculation tests, not a public data contract.
- `Invest.rda` remains in the source R repo for this phase and should remain server-only during later phases.
- The original Shiny code contains UI/observer behavior and plot formatting that is not represented here. These fixtures focus on calculation outputs.
- Orphaned/unclear `LIFO` logic is intentionally excluded because the migration map notes missing active UI inputs for it.
