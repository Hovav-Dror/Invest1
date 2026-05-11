# Invest Python Migration

The Python backend migration keeps the source investment data server-only and
ports Shiny calculation logic into reusable Python modules. Converted Parquet
files live under `data/`; they are backend inputs, not frontend/static assets.

Regenerate converted data:

```sh
Rscript scripts/export_r_data.R
```

Load data in Python:

```python
from invest_core.data import load_data

data = load_data()
print(data.SP500DIV.head())
```

Run the ported calculations:

```python
from invest_core.calculations import portfolio_summary, tax_events
from invest_core.data import load_data

data = load_data()
print(tax_events(data).tail())
print(portfolio_summary(data))
```

Validate the converted files and calculation parity fixtures:

```sh
python -m pytest
```

Run the Flask backend locally:

```sh
flask --app invest_api.app run
```

Open the lightweight static frontend at the Flask root:

```text
http://127.0.0.1:5000/
```

The frontend is plain HTML/CSS/JavaScript served from `invest_api/static/`.
It uses relative `static/...` asset URLs and relative `api/...` API requests,
so it can be mounted behind an Nginx subpath that proxies the same subpath to
Flask. The browser renders API-returned JSON tables and simple SVG line charts;
it does not load converted Parquet files or reimplement calculation logic.

The API is rooted at relative-friendly `/api/...` routes and keeps converted
Parquet inputs server-only. Available JSON endpoints:

- `/api/status`
- `/api/tax_events`
- `/api/commission_effect`
- `/api/commission_tax`
- `/api/sp500_risk`
- `/api/portfolio_summary`
- `/api/portfolio_structure`
- `/api/portfolio_commissions`
- `/api/kupat_gemel`
- `/api/kupat_gemel_pension`
- `/api/independent_commissions`
- `/api/tax_us_vs_il`
- `/api/portfolio_over_time`
- `/api/us_world_rolling`
- `/api/us_global_rolling`
- `/api/sp500_scv_rolling`
- `/api/sp500_scv_heatmap`
- `/api/sp500_scv_after_tax`
- `/api/trinity`

The source `/Users/hovav/Documents/R projects/Invest/Invest.rda` remains
private. No static frontend assets are generated in this phase.

Phase 3 parity tests compare Python outputs against
`tests/fixtures/r_outputs/*.csv` for the default tax-event, management-fee,
S&P 500 rolling-risk, and lazy-portfolio summary calculations. Numeric
comparisons use tight floating-point tolerances to allow normal R/Python
rounding differences while preserving fixture-level behavior.
