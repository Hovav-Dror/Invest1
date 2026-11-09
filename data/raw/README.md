# Raw inputs for the young-couples section

Downloaded or copied as-is on 2026-11-09. `scripts/build_young_couples_data.py` turns the files marked "used" into `data/young_couples_monthly.parquet` (monthly, from 1986-01), which the API uses; its docstring describes each column and how the series are spliced. `scripts/tase_xlsx_to_csv.R` makes `tase_general_index_1979_2016.csv` from the TASE workbook.

To rebuild:

```bash
Rscript scripts/tase_xlsx_to_csv.R
python scripts/build_young_couples_data.py
```

| File | Used | What | Source | Coverage | Notes |
| --- | --- | --- | --- | --- | --- |
| `cbs_housing_price_index_40010.json` | yes | Dwelling price index (מחירי דירות), monthly | CBS API: `https://api.cbs.gov.il/index/data/price?id=40010&format=json&startPeriod=01-1990&endPeriod=12-2026&PageSize=1000` | 1994-01 to 2026-07 | Base: 1993 average = 100. Each month is based on transactions over two months, so it lags. Not part of the CPI since 1999. |
| `cbs_owner_housing_120490_1983_1998.json` | yes | CPI component "owner-occupied housing services" (שירותי דיור בבעלות הדיירים), monthly | CBS API, same URL with `id=120490&startPeriod=01-1983&endPeriod=12-1998` | 1983-01 to 1998-12 | Used for dwelling prices before 1994, chained from the monthly `percent`. Until 1998 the CBS measured it as the dwelling price times a fixed yield, so it followed dwelling prices; from 1999 it follows rents. Bank of Israel: [on the owner-occupied housing component](https://boi.org.il/roles/research-and-publications/all-researches/sekerboi/על-סעיף-הדיור-בבעלות-הדיירים-במדד-המחירים-לצרכן/). Over 1995–1998 its 12-month changes have a correlation of 0.91 with the dwelling price index. |
| `cbs_cpi_120010_1983_1993.json` | yes | Consumer price index, general, monthly | CBS API, same URL with `id=120010&startPeriod=01-1983&endPeriod=12-1993` | 1983-01 to 1993-12 | Turns the workbook's real TASE index into a nominal one before 1993-12. Chained from the monthly `percent` (the base changes). |
| `cbs_cpi_120010.json` | no | Consumer price index, general, monthly | CBS API, same URL with `id=120010` | 1990-01 to 2026-09 | The calculations take Israeli CPI from the main market data. |
| `boi_policy_rate_daily.csv` | yes | Bank of Israel policy rate, daily | BOI SDMX: `https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/BR/1.0/MNT_RIB_BOI_D?format=csv` | 1994-01-27 to 2026-11-09 | Percent. The return on cash from 1994-02 (a money-market fund earns about this rate). |
| `boi_makam_yield_1986_1994.csv` | yes | Average yield to maturity on one-month makam (מק"ם), percent a year | Copied by hand from tables in the Bank of Israel annual reports, chapter 7 (money and capital markets): 1989 report table 7-7 ([PDF](https://boi.org.il/media/2fqpqc3e/p7.pdf)), 1990 report table 7-6 ([PDF](https://boi.org.il/media/jdtnfzrg/p7.pdf)), 1993 report table 7-4 ([PDF](https://boi.org.il/media/elep2lrx/p7.pdf)) | 1986-01 to 1994-01 | The return on cash before 1994-02. Each row names its table in `source`; the latest report is used where they overlap. 1986, 1987 and 1991-04 to 1991-12 have no monthly figures in these reports, so the annual average repeats (`note`). The 1989 monthly values equal the one-month column of the separate makam table in the 1989 report, chapter 8, table 8-4 ([PDF](https://boi.org.il/media/evdn3ack/p8.pdf)). That table gives lower averages for 1987 (15–17%) than the 20.0% used here, from the 1990 report. Neither BOI's SDMX service nor FRED has a short rate before 1992. |
| `tase_general_index_1979_2016.xlsx` | via CSV | TASE general share index (מדד המניות והמירים), monthly | Received from the TASE research department in 2016 for the quantitatively.club post on housing vs stocks | 1979-12 to 2016-08 | Column 6 is the real index (1979-12 = 100), complete. Column 5 is the nominal index from 1993-12; before that it holds monthly changes (×1000), not levels. |
| `tase_general_index_1979_2016.csv` | yes | The workbook as CSV: `tase_index` (nominal, from 1993-12) and `tase_real` | `scripts/tase_xlsx_to_csv.R` | 1979-12 to 2016-08 | A price index, without dividends. |
| `ta125_yahoo_monthly_1992_2026.csv` | yes | TA-125 index, month-end close | Yahoo Finance chart API, `^TA125.TA`, monthly ([history page](https://finance.yahoo.com/quote/%5ETA125.TA/history/)) | 1992-11 to 2026-10 | A price index, without dividends. Chained onto the TASE general index after 2016-08; over 1994–2016 the monthly changes of the two have a correlation of 0.97. |
| `boi_mortgage_rates_bir_mrtg_99.csv` | no | Interest rates and volumes on new housing loans, by track | BOI SDMX dataflow `BIR_MRTG_99`, `startperiod=2000-01` | 2000s to 2026 | Series meaning is in the dimension columns (indexation, rate type, rate-change period, LTV, PTI). Still to be decoded. |

Still missing:

- Dividends on Israeli shares. The calculations add a constant 2.5% a year to the price indices (TASE reported an average dividend yield of 2.8% in 2022 and 2.9% in 2023 for listed companies). A TA-125 total return series would replace this.
- Monthly makam yields for 1986–1987 and April–December 1991 (Bank of Israel annual reports for 1987, 1988 and 1991).
