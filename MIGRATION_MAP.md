# Invest Shiny Migration Phase Plan

Source app inspected read-only:

- `/Users/hovav/Documents/R projects/Invest/app.R`
- `/Users/hovav/Documents/R projects/Invest/HelperFunctions.R`
- `/Users/hovav/Documents/R projects/Invest/Invest.rda`

Target architecture:

- Flask + Gunicorn backend
- Lightweight static frontend with HTML/CSS/JS
- Deploy under `/srv/nonshiny/app_name`
- Serve publicly under an Nginx subpath such as `/app-url/`
- Backend bound locally on `127.0.0.1:800X`
- Include `./api/status`
- Cache expensive computations
- Keep private/server-only data on the server
- Use relative frontend paths, not absolute `/static/...` paths
- Do not use Shiny, Dash, or Streamlit

## 1. UI Inputs

### Tax Event / Management Fees

- `date_range_input_tax_event`
- `TaxCPIadjust`
- `InitialInvest2`
- `commission1`
- `commission2`
- `InitialInvest3`
- Mirrored controls: `date_range_input_tax_event2`, `TaxCPIadjust2`

### Kupat Gemel / Pension Comparison

- `KHAge`
- `KHyear`
- `InitialInvest4`
- `TaxCPIadjust3`
- `KHKHcommission1`
- `KHKHcommission2`
- `KHPcommission1`
- `KHPcommission2`
- `KHIcommission1`
- `KHIcommission2`
- `PensionMonths`
- Mirrored controls: `KHAgeb`, `KHyearb`, `InitialInvest4b`, `TaxCPIadjust3b`, `KHKHcommission1b`, `KHKHcommission2b`, `KHIcommission1b`, `KHIcommission2b`, `PensionMonthsb`

### S&P 500 Long-Term Risk

- `SP500dates`
- `SP500years`
- `SP500thresh2`

### Independent Investment Fees / Taxation

- `IndiIndexSource`
- `IndexDates`
- `SharePrice`
- `IndexInitialInvestment`
- `DollarCommission`
- `CommissionPerShare`
- `MinDollarCommission`
- `YearlyCommission`
- `Use25Tax`
- `AdjustCPIindex`
- Second comparison set: `IndiIndexSource2`, `IndexDates2`, `SharePrice2`, `IndexInitialInvestment2`, `DollarCommission2`, `CommissionPerShare2`, `MinDollarCommission2`, `YearlyCommission2`, `AdjustCPIindex2`

### Lazy Portfolio Comparison

- `PortfolioCPI`
- `PortfolioSelect`
- `PortfolioHighlight`
- `Portfolio15years`
- `PortfolioYears`
- `PortfolioCommision`
- Mirrored controls: `PortfolioCPI2`, `PortfolioSelect2`, `PortfolioHighlight2`, `Portfolio15years2`, `PortfolioYears2`, `PortfolioCommision2`
- Time-series controls: `PortfolioTIMEtype`, `ProtfolioMovingWindows`

### America / Global / Small-Cap-Value Sections

- `PortfolioCPI3`
- `PortfolioSelect3`
- `ProtfolioMovingWindows3`
- `PortfolioYears3`
- `PortfolioCPI4`
- `PortfolioSelect4`
- `ProtfolioMovingWindows4`
- `PortfolioYears4`
- `Acc_or_CAGR`
- `ProtfolioMovingWindows5`
- `PortfolioYears5`

### Trinity

- `TrinityPortfolio`
- `TrinityDrawP`
- `TrinityYears`
- `TrinityBase`

## 2. Reactive Expressions

Important Shiny reactives:

- `is_mobile_device`: frontend-provided mobile flag.
- `TaxEventDate`: builds tax-event return series from `SP500DIV`.
- `dbCombined`: combines multiple fee/tax scenarios.
- `CombineTaxCommissionDB`: related combined tax/commission table.
- `PortfolioTable`: normalized lazy-portfolio data based on selected CPI mode, year range, selected portfolios, and commission toggle.

Many `renderUI` outputs also define nested `renderPlotly` outputs, effectively acting as reactive plot builders.

## 3. Observers / Events

Main observer behavior:

- Sync mirrored controls:
  - Tax date sliders.
  - Tax CPI checkboxes.
  - Kupat Gemel input groups.
  - Portfolio comparison input groups.
  - Independent-investment date controls.
- Update portfolio highlight choices based on selected portfolios.
- Toggle portfolio label controls depending on static vs interactive mode.

Migration note: these should become ordinary frontend state synchronization in JavaScript, not backend observers.

## 4. Server-Side Calculations

Core calculations now embedded inside `server`:

- Tax drag from repeated taxable events on S&P 500 with dividends.
- Annual management fee drag.
- Tax plus management fee scenarios.
- Kupat Gemel vs policy vs independent investment, including before/after age 60 tax treatment and pension conversion.
- Long-term S&P rolling return risk.
- Independent investment fees:
  - FX conversion.
  - Buy/sell commissions.
  - Minimum commissions.
  - Annual fees.
  - Optional 25% tax.
  - CPI adjustment.
- Israeli-CPI vs dollar-based tax comparison.
- Lazy portfolio metrics:
  - CAGR.
  - Standard deviation.
  - Max drawdown.
  - Bad years.
  - Factor over N years.
- Rolling portfolio returns over time.
- US vs ex-US/global rolling comparisons.
- S&P 500 vs US Small Cap Value rolling comparisons, before and after tax.
- Trinity withdrawal simulation.

## 5. Data Loading

At startup:

- `app.R` loads `Invest.rda`.
- `app.R` sources `HelperFunctions.R`.

`Invest.rda` contains:

| Object | Shape | Notes |
| --- | ---: | --- |
| `LazyReturns1` | `5542 x 18` | Largest object; portfolio/year returns and derived fields |
| `PortfoliosStructure` | `118 x 5` | Portfolio component weights and commission assumptions |
| `SP500DIV` | `1837 x 5` | Monthly S&P/dividend/CPI/USD-style data |
| `SP500US` | `1837 x 3` | S&P US CPI/real return data |
| `US_Small_Cap_Value_Monthly` | `624 x 3` | Monthly US small-cap-value data |

The `.rda` file is small, about `284K`, but should remain server-side unless a sanitized subset is intentionally exposed.

## 6. Plots / Tables / Downloads

### Static ggplot Outputs

- `plotTaxEvents`
- `plotCommissionEffect`
- `plotCommissionAndTaxToghther`
- `SP500overyear`
- `KHplot`
- `KHplot2`
- `IndiCommissions`

### Interactive Plotly Outputs

- Portfolio scatter plots: `p1i`, `p2i`
- Portfolio time-series: `p3i`
- US/world plots: `pworldi`, `pworldiglobal`
- All-years heatmaps:
  - `p3iGlobalVsSP500allYears`
  - `p3i4B`
- Other rolling comparison charts:
  - `p3i3`
  - `p3i4`
  - `p3i5`
- Trinity: `TrinityPlot1`

### Tables

- `TablePortfoliosStructure`
- `TablePortfoliosCommission`

### Image

- `USvsWorld` serves `www/US vs world 1.jpeg`.

### Downloads

No active `downloadHandler` usage found.

## 7. Expensive Operations

Likely expensive enough to cache:

- Rolling portfolio calculations over many portfolios and year ranges.
- Plotly JSON generation for portfolio, time-series, and heatmap outputs.
- Trinity simulation loops across all possible starting years.
- Tax/commission simulations with monthly loops.
- Repeated `group_by`, `mutate`, and `pivot` pipelines over `LazyReturns1`.

The data is small, so the cost is mostly repeated computation and Plotly payload generation, not I/O.

## 8. Private / Server-Only Data

Keep server-only:

- `Invest.rda`.
- Source CSV/XLS files used to prepare `Invest.rda`.
- Calculation methodology if the raw datasets should not be trivially scrapeable.
- Any future credentials/API keys for data refreshes.
- Google Analytics config if it includes identifiers that should be controlled.

## 9. Things That Can Move To The Browser

Good frontend candidates:

- Static Hebrew article content and tab navigation.
- Form controls and mirrored-control synchronization.
- Simple formatting: currency, percent, labels.
- Rendering Plotly/Vega/ECharts from JSON returned by Flask.
- Static image `US vs world 1.jpeg`.
- Client-side filtering/sorting for small portfolio structure tables once sanitized JSON is provided.

## 10. Things That Must Remain In Flask/Python

Keep in Flask/Python:

- Loading private data.
- All investment/tax/portfolio calculations.
- Cache key generation and cache storage.
- Returning precomputed chart-ready JSON.
- Validation of input ranges and selected portfolio names.
- Any future refresh pipeline from Yahoo/BOI/source files.

## 11. Proposed Flask API Endpoints

Use relative frontend calls such as `fetch("api/status")`, not `/api/status`, so Nginx subpath deployment works.

### Core

- `GET ./api/status`
- `GET ./api/config`

`./api/config` should return available portfolio names, date bounds, defaults, CPI modes, and frontend option metadata.

### Tax / Fees

- `POST ./api/tax-events`
- `POST ./api/commission-effect`
- `POST ./api/commission-tax`
- `POST ./api/sp500-risk`

### Kupat Gemel

- `POST ./api/kupat-gemel`
- `POST ./api/kupat-gemel-pension`

### Independent Investment

- `POST ./api/independent-commissions`
- `POST ./api/tax-us-vs-il`

### Lazy Portfolios

- `POST ./api/portfolio/summary`
- `POST ./api/portfolio/risk-return`
- `POST ./api/portfolio/over-time`
- `GET ./api/portfolio/structure`
- `GET ./api/portfolio/commissions`

### US / Global / Small-Cap Value

- `POST ./api/us-world/rolling`
- `POST ./api/us-global/rolling`
- `POST ./api/global-vs-sp500/heatmap`
- `POST ./api/sp500-vs-scv/rolling`
- `POST ./api/sp500-vs-scv/heatmap`
- `POST ./api/sp500-vs-scv/after-tax`

### Trinity

- `POST ./api/trinity`

## 12. Proposed Cache Strategy

Use two levels:

### Startup Data Cache

Load converted data once at process startup from Parquet, CSV, JSON, or Pickle.

Do not load the source `.rda` on every request.

### Computation Cache

Use `Flask-Caching` with filesystem cache or `diskcache`, keyed by:

- Endpoint name.
- Normalized JSON request parameters.
- Data-version string or source-data hash.

Suggested policy:

- Long or indefinite TTL for historical data.
- Explicit cache busting when source data changes.
- Filesystem/disk cache preferred over Redis for the cheap Ubuntu target.

## 13. Risks / Unclear Parts

- The original repo has uncommitted changes, including `app.R`; migration should treat the current working tree as source of truth unless decided otherwise.
- Some UI/output code looks partially orphaned:
  - `LIFO` references inputs like `LIFODates`, `MonthlyInvest`, `Withdrawls`, and `WithdrawFreq`, but these were not found in active UI.
- There is a likely bug around `input$input$PortfolioSelect` in one observer.
- Duplicated mirrored controls can be simplified in the new frontend.
- Python parity needs care:
  - R `cumprod`.
  - Date/month handling.
  - `lag`.
  - CPI normalization.
  - Tax edge cases.
- Plot labels mix Hebrew/English/RTL handling; browser rendering may be better than the current R helper, but needs visual QA.
- `google-analytics.html` should be checked before reuse under the new subpath.

## 14. Files That Will Likely Need To Be Created

In `/Users/hovav/Documents/Personal Projects/Invest1`:

- `app.py`
- `wsgi.py`
- `requirements.txt`
- `gunicorn.conf.py`
- `README.md`
- `data/`
- `scripts/convert_rda.py` or `scripts/export_r_data.R`
- `invest_core/__init__.py`
- `invest_core/data.py`
- `invest_core/schemas.py`
- `invest_core/calculations.py`
- `invest_core/cache.py`
- `invest_core/charts.py`
- `static/index.html`
- `static/styles.css`
- `static/app.js`
- `static/assets/US vs world 1.jpeg`
- `deploy/invest.service`
- `deploy/nginx-subpath.conf`

## 15. Phase Plan

Use this as a thread-by-thread plan. Start the next phase only after the previous phase is implemented, tested, and summarized in the repo.

Each phase should end with:

- A short completion note in the thread.
- Any relevant docs updated.
- Tests or verification commands run and recorded.
- A clear list of changed files.
- No unresolved work hidden inside the phase.

### Phase 1: Source Baseline And Parity Fixtures

Goal: freeze the current Shiny behavior before porting logic.

Scope:

- Treat the current original repo working tree as source of truth unless explicitly changed.
- Export representative calculation outputs from the Shiny/R code for default inputs.
- Capture enough cases to compare Python calculations later.
- Do not build Flask yet.

Deliverables:

- `docs/source_baseline.md`
- `tests/fixtures/r_outputs/` with exported JSON/CSV fixtures.
- A small script to produce/reproduce the fixtures, likely `scripts/export_r_fixtures.R`.

Suggested fixture coverage:

- Tax events default period and CPI toggle.
- Commission effect with default `commission1` and `commission2`.
- Commission plus tax.
- S&P rolling risk defaults.
- Kupat Gemel default scenario.
- Independent commissions defaults.
- Tax US vs IL defaults.
- Portfolio summary defaults.
- Portfolio over-time defaults.
- US/global and SP500/SCV comparison defaults.
- Trinity defaults.

Validation:

- Fixture export script runs from a clean shell.
- Fixture files are deterministic enough for later tests.
- Document source data object names and dimensions.

Start next thread with:

> Phase 2: convert the Shiny app data into Python-friendly server-only files using the fixtures and migration plan in `MIGRATION_MAP.md`. Do not build the frontend yet.

### Phase 2: Data Conversion And Python Data Layer

Goal: make the R data usable from Python without loading `.rda` during requests.

Scope:

- Convert `Invest.rda` into server-only Python-friendly data files.
- Build a small Python data-loading layer.
- Preserve date types, numeric precision, and column names clearly.
- Keep raw/source data private and out of static assets.

Deliverables:

- `data/` with converted files, preferably Parquet if dependencies are acceptable, otherwise CSV/Pickle.
- `scripts/convert_rda.py` or `scripts/export_r_data.R`.
- `invest_core/data.py`
- `tests/test_data_loading.py`

Validation:

- Python loads all five data objects.
- Shapes match the R baseline:
  - `LazyReturns1`: `5542 x 18`
  - `PortfoliosStructure`: `118 x 5`
  - `SP500DIV`: `1837 x 5`
  - `SP500US`: `1837 x 3`
  - `US_Small_Cap_Value_Monthly`: `624 x 3`
- Min/max dates and portfolio lists match the baseline.

Start next thread with:

> Phase 3: port the core calculations from Shiny/R to Python and validate against the Phase 1 fixtures. Keep the app backend/frontend minimal or absent.

### Phase 3: Core Calculation Port

Goal: port server-side calculations into testable Python functions.

Scope:

- Implement calculation functions without Flask route concerns.
- Match R behavior against Phase 1 fixtures.
- Prefer pandas/numpy functions over ad hoc loops where clear, but preserve R semantics where needed.

Deliverables:

- `invest_core/calculations.py`
- `invest_core/schemas.py` or equivalent validation helpers.
- Focused tests for each calculation group.

Calculation groups:

- Tax event scenarios.
- Commission effect.
- Commission plus tax.
- S&P long-term rolling risk.
- Kupat Gemel and pension comparison.
- Independent investment fees.
- Tax US vs IL.
- Portfolio summary and risk/return.
- Portfolio over-time.
- US/world/global rolling comparisons.
- SP500 vs SCV comparisons and heatmaps.
- Trinity withdrawal simulation.

Validation:

- Tests compare Python outputs to Phase 1 fixtures within explicit tolerances.
- Edge cases are covered for empty or invalid year ranges.
- Known orphaned/unclear `LIFO` functionality is either excluded with a note or clarified before implementation.

Start next thread with:

> Phase 4: create the Flask/Gunicorn backend skeleton and expose the calculation functions through relative-path-safe JSON API endpoints. Keep frontend minimal.

### Phase 4: Flask Backend And API

Goal: create the lightweight backend shell and API contract.

Scope:

- Add Flask app factory.
- Add `./api/status`.
- Add `./api/config`.
- Add JSON endpoints over the calculation functions.
- Keep all frontend paths subpath-safe.
- Bind locally in development and prepare for Gunicorn.

Deliverables:

- `app.py`
- `wsgi.py`
- `requirements.txt`
- `gunicorn.conf.py`
- API tests.
- Backend README notes.

Endpoint groups:

- `GET ./api/status`
- `GET ./api/config`
- Tax/fees endpoints.
- Kupat Gemel endpoints.
- Independent investment endpoints.
- Portfolio endpoints.
- US/global/SCV endpoints.
- Trinity endpoint.

Validation:

- Flask test client passes all endpoint tests.
- Invalid inputs return clear `400` responses.
- API responses are JSON-serializable and chart-ready.
- No static file URLs start with `/static/`.

Start next thread with:

> Phase 5: add disk caching to the Flask backend with versioned cache keys and verify that repeated expensive API calls are served from cache.

### Phase 5: Cache Strategy

Goal: reduce CPU work for cheap Ubuntu deployment.

Scope:

- Add filesystem/disk cache.
- Cache expensive endpoint results by normalized request params.
- Include source-data version/hash in cache keys.
- Avoid caching invalid responses.

Deliverables:

- `invest_core/cache.py`
- Cache configuration in Flask app setup.
- Tests for cache hits, misses, and cache-key stability.

Validation:

- Repeated expensive requests hit cache.
- Changing a parameter changes the cache key.
- Changing the data version invalidates old entries.
- Cache directory is configurable for `/srv/nonshiny/app_name`.

Start next thread with:

> Phase 6: build the static frontend shell with RTL Hebrew content, tab navigation, controls, and relative API calls. Do not attempt every chart at once.

### Phase 6: Static Frontend Shell

Goal: replace Shiny UI structure with lightweight static HTML/CSS/JS.

Scope:

- Build the first usable static app screen.
- Include tab navigation and Hebrew RTL content structure.
- Add shared control components.
- Fetch `api/status` and `api/config` with relative paths.
- Keep the UI lightweight; use React only if plain JS becomes clearly painful.

Deliverables:

- `static/index.html`
- `static/styles.css`
- `static/app.js`
- `static/assets/US vs world 1.jpeg`

Validation:

- App loads under root and under a simulated subpath.
- `fetch("api/status")` and `fetch("api/config")` work.
- No absolute `/static/...` asset paths.
- Layout is usable on desktop and mobile.

Start next thread with:

> Phase 7: connect the frontend to the Flask APIs section by section, starting with tax events and commission charts.

### Phase 7: Chart And Table Integration

Goal: make the frontend functionally match the Shiny app section by section.

Scope:

- Render charts from API JSON.
- Render tables from API JSON.
- Implement frontend state synchronization previously handled by Shiny observers.
- Prefer Plotly.js, ECharts, or another lightweight browser chart renderer over server-rendered images.

Recommended order:

1. Tax event chart.
2. Commission effect chart.
3. Commission plus tax chart.
4. S&P risk chart.
5. Kupat Gemel charts.
6. Independent investment charts.
7. Portfolio summary and time-series charts.
8. US/global/SCV comparison charts.
9. Trinity chart.
10. Portfolio structure and commission tables.

Validation:

- Each section calls only relative API paths.
- Controls update the intended chart without full page reloads.
- Tables sort/filter acceptably for the small data sizes.
- Browser console has no errors.

Start next thread with:

> Phase 8: add deployment files for Gunicorn/systemd/Nginx subpath hosting and verify the app locally in a subpath-like configuration.

### Phase 8: Deployment Packaging

Goal: make the app ready for the cheap Ubuntu server.

Scope:

- Add Gunicorn config.
- Add systemd service example.
- Add Nginx subpath config example.
- Document `/srv/nonshiny/app_name` deployment.
- Keep backend bound to `127.0.0.1:800X`.

Deliverables:

- `deploy/invest.service`
- `deploy/nginx-subpath.conf`
- Deployment section in `README.md`

Validation:

- Gunicorn can serve the Flask app locally.
- Static frontend still uses relative paths.
- Nginx example preserves the subpath and proxies API correctly.
- `./api/status` works through the configured subpath.

Start next thread with:

> Phase 9: run final parity, performance, and visual QA for the migrated app, then produce a release checklist.

### Phase 9: Final QA And Release Checklist

Goal: verify parity, usability, and low-resource behavior before deployment.

Scope:

- Compare migrated outputs to Phase 1 fixtures.
- Run endpoint tests.
- Run frontend smoke tests.
- Check mobile and desktop rendering.
- Check cache behavior under repeated requests.
- Record any intentional differences from Shiny.

Deliverables:

- `docs/release_checklist.md`
- Updated `README.md`
- Any final bug fixes found during QA.

Validation:

- All tests pass.
- Key charts match R baseline within documented tolerances.
- Browser QA under a subpath passes.
- No private data is exposed from static assets.
- App remains responsive on repeated expensive requests.

Completion criteria:

- The app can be deployed under `/srv/nonshiny/app_name`.
- Gunicorn runs locally on `127.0.0.1:800X`.
- Nginx can serve it under `/app-url/`.
- `./api/status` returns healthy status through the public subpath.
