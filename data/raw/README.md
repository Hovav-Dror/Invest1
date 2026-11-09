# Raw inputs for the young-couples section

Downloaded or copied as-is on 2026-11-09. `scripts/build_young_couples_data.py` turns the CBS dwelling index, the Bank of Israel rate and the TASE general index into `data/young_couples_monthly.parquet`, which the API uses; the other files are not used yet. `scripts/tase_xlsx_to_csv.R` makes `tase_general_index_1993_2016.csv` (month, nominal index from 1993-12) from the TASE workbook.

| File | What | Source | Coverage | Notes |
| --- | --- | --- | --- | --- |
| `cbs_housing_price_index_40010.json` | Dwelling price index (מחירי דירות), monthly | CBS API: `https://api.cbs.gov.il/index/data/price?id=40010&format=json&startPeriod=01-1990&endPeriod=12-2026&PageSize=1000` | 1994-01 to 2026-07 | Base: 1993 average = 100. Each month is based on transactions over two months, so it lags. Not part of the CPI since 1999. |
| `cbs_cpi_120010.json` | Consumer price index, general, monthly | CBS API, same URL with `id=120010` | 1990-01 to 2026-09 | The base changes over time (`currBase`); chain with the monthly `percent`, or rebase per period. |
| `boi_policy_rate_daily.csv` | Bank of Israel policy rate, daily | BOI SDMX: `https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/BR/1.0/MNT_RIB_BOI_D?format=csv` | 1994-01-27 to 2026-11-09 | Percent. A proxy for the return on cash (money-market fund, deposit, makam). |
| `boi_mortgage_rates_bir_mrtg_99.csv` | Interest rates and volumes on new housing loans, by track | BOI SDMX dataflow `BIR_MRTG_99`, `startperiod=2000-01` | 2000s to 2026 | Series meaning is in the dimension columns (indexation, rate type, rate-change period, LTV, PTI). Still to be decoded. |
| `tase_general_index_1979_2016.xlsx` | TASE general share index (מדד המניות והמירים), monthly, nominal and real | Received from the TASE research department in 2016 for the quantitatively.club post on housing vs stocks | 1979-12 to 2016-08 | Columns: year, month, real index, CPI (base 1993), nominal index, real index (1979-12 = 100). Does not cover 2016 onward. |

Still missing:

- A long housing price series before 1994 (the 2016 post used a Bank of Israel series from 1961; check whether it was the dwelling price index or the CPI housing component).
- Israeli stocks after 2016 (TA-125 total return), subject to the TASE terms of use.
