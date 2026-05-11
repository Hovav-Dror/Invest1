"""Apply the 2024/2025 source-data refresh to converted parquet data.

This is intentionally small and explicit: the app currently consumes converted
server-side parquet files, while the original R `.rda` source is not part of
this repository. The script extends the migrated data with sourced 2024 and
2025 rows, then records those sources in the manifest.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

SP500_MONTHLY_TOTAL_RETURN = {
    "2024-01-01": 1.68,
    "2024-02-01": 5.34,
    "2024-03-01": 3.22,
    "2024-04-01": -4.08,
    "2024-05-01": 4.96,
    "2024-06-01": 3.59,
    "2024-07-01": 1.22,
    "2024-08-01": 2.43,
    "2024-09-01": 2.14,
    "2024-10-01": -0.91,
    "2024-11-01": 5.87,
    "2024-12-01": -2.38,
    "2025-01-01": 2.78,
    "2025-02-01": -1.30,
    "2025-03-01": -5.63,
    "2025-04-01": -0.68,
    "2025-05-01": 6.29,
    "2025-06-01": 5.09,
    "2025-07-01": 2.24,
    "2025-08-01": 2.03,
    "2025-09-01": 3.65,
    "2025-10-01": 2.34,
    "2025-11-01": 0.25,
    "2025-12-01": 0.06,
}

ANNUAL_RETURNS = {
    "S&P 500": {
        2024: 25.02,
        2025: 17.88,
    },
    "US Small Cap Value": {
        2024: 9.70,
        2025: 13.71,
    },
}

SOURCES = {
    "sp500_monthly_total_return": {
        "name": "YCharts S&P 500 Monthly Total Return",
        "url": "https://ycharts.com/indicators/sp_500_monthly_total_return",
        "coverage_applied": "2024-01 through 2025-12 monthly returns",
    },
    "sp500_annual_total_return_cross_check": {
        "name": "Slickcharts S&P 500 Total Returns by Year",
        "url": "https://www.slickcharts.com/sp500/returns",
        "coverage_applied": "2024 and 2025 annual S&P 500 total-return cross-check",
    },
    "scv_annual_return": {
        "name": "MSCI USA Small Cap Value Weighted Index factsheet, net USD returns",
        "url": "https://www.msci.com/documents/10199/83700218-af0a-4993-b962-00de11158106",
        "coverage_applied": "2024 and 2025 US Small Cap Value annual returns",
    },
    "usd_ils": {
        "name": "Bank of Israel daily representative USD/ILS exchange rates",
        "url": "https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/EXR/1.0/RER_USD_ILS?c%5BDATA_TYPE%5D=OF00&startperiod=2023-12-01&format=csv",
        "coverage_applied": "monthly last available daily rate through 2026-01",
    },
    "israel_cpi": {
        "name": "Israel Central Bureau of Statistics CPI, series 120010",
        "url": "https://api.cbs.gov.il/index/data/price?id=120010&format=csv&download=false&startPeriod=01-2024&lang=en",
        "coverage_applied": "monthly CPI through 2026-01, chained across the Average 2024 rebasing",
    },
    "us_cpi": {
        "name": "FRED CPIAUCSL",
        "url": "https://fred.stlouisfed.org/series/CPIAUCSL",
        "download_url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",
        "coverage_applied": "monthly CPI-U through 2026-01; one blank interior FRED CSV value is linearly interpolated",
    },
}


def _read_parquet(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


def _write_parquet(name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(DATA_DIR / f"{name}.parquet", index=False)


def _read_csv_source(source_key: str, local_path: str, **kwargs) -> pd.DataFrame:
    path = Path(local_path)
    source = SOURCES[source_key]
    csv_source = path if path.exists() else source.get("download_url", source["url"])
    return pd.read_csv(csv_source, **kwargs)


def _month_start(dates: pd.Series) -> pd.Series:
    return dates.dt.to_period("M").dt.to_timestamp()


def load_usd_ils() -> pd.DataFrame:
    usd = _read_csv_source("usd_ils", "/private/tmp/usd_ils.csv", parse_dates=["TIME_PERIOD"])
    usd = usd.sort_values("TIME_PERIOD")
    usd["month"] = _month_start(usd["TIME_PERIOD"])
    return (
        usd.groupby("month", as_index=False)
        .tail(1)
        .rename(columns={"month": "date", "OBS_VALUE": "dollar"})[["date", "dollar"]]
        .reset_index(drop=True)
    )


def load_cpi_us() -> pd.DataFrame:
    cpi = _read_csv_source("us_cpi", "/private/tmp/cpi_us.csv", parse_dates=["observation_date"])
    cpi = cpi.rename(columns={"observation_date": "date", "CPIAUCSL": "CPI_US"})
    cpi["CPI_US"] = pd.to_numeric(cpi["CPI_US"], errors="coerce")
    cpi["CPI_US"] = cpi["CPI_US"].interpolate(limit_area="inside")
    return cpi.dropna(subset=["CPI_US"])


def load_cpi_il() -> pd.DataFrame:
    cpi = _read_csv_source("israel_cpi", "/private/tmp/cpi_il.csv")
    cpi["date"] = pd.to_datetime(
        cpi["year"].astype(str) + "-" + cpi["period"].astype(str).str.zfill(2) + "-01"
    )
    cpi = cpi[["date", "currBase_baseDesc", "currBase_value"]].copy()
    old_base = cpi[cpi["currBase_baseDesc"] == "Average 2022"].copy()
    avg_2024_old_base = old_base[old_base["date"].dt.year == 2024]["currBase_value"].mean()
    cpi["CPI"] = np.where(
        cpi["currBase_baseDesc"] == "Average 2024",
        cpi["currBase_value"] * avg_2024_old_base / 100,
        cpi["currBase_value"],
    )
    return cpi[["date", "CPI"]].sort_values("date").reset_index(drop=True)


def extend_sp500_monthly() -> None:
    sp500_us = _read_parquet("SP500US")
    sp500_div = _read_parquet("SP500DIV")
    sp500_us["date"] = pd.to_datetime(sp500_us["date"])
    sp500_div["date"] = pd.to_datetime(sp500_div["date"])

    cpi_us = load_cpi_us()
    cpi_il = load_cpi_il()
    usd = load_usd_ils()

    base_date = pd.Timestamp("2024-01-01")
    last = sp500_us.loc[sp500_us["date"] == base_date].iloc[-1].copy()
    rows = []
    value = float(last["Real_Total_Return_Price"])
    for return_month, return_pct in SP500_MONTHLY_TOTAL_RETURN.items():
        # Existing data already contains 2024-01-01. The January 2024 return
        # moves the series to 2024-02-01, and so on through 2026-01-01.
        target_date = pd.Timestamp(return_month) + pd.DateOffset(months=1)
        value *= 1 + return_pct / 100
        rows.append({"date": target_date, "Real_Total_Return_Price": value})

    appended = pd.DataFrame(rows)
    appended = appended.merge(cpi_us, on="date", how="left")
    appended = appended.merge(usd, on="date", how="left")
    appended = appended.merge(cpi_il, on="date", how="left")

    missing = appended[appended[["CPI_US", "dollar", "CPI"]].isna().any(axis=1)]
    if not missing.empty:
        raise RuntimeError(f"Missing monthly source data for: {missing['date'].dt.strftime('%Y-%m-%d').tolist()}")

    sp500_us = pd.concat(
        [sp500_us[sp500_us["date"] <= base_date], appended[["date", "Real_Total_Return_Price", "CPI_US"]]],
        ignore_index=True,
    )
    appended["SP500wDividends"] = appended["Real_Total_Return_Price"] * appended["dollar"]
    sp500_div = pd.concat(
        [
            sp500_div[sp500_div["date"] <= base_date],
            appended[["date", "Real_Total_Return_Price", "dollar", "SP500wDividends", "CPI"]],
        ],
        ignore_index=True,
    )

    _write_parquet("SP500US", sp500_us.sort_values("date"))
    _write_parquet("SP500DIV", sp500_div.sort_values("date"))


def _recalculate_drawdowns(frame: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, group in frame.groupby(["Portfolio", "CommissionUse"], sort=False):
        group = group.sort_values("Year").copy()
        for value_col, years_col, drop_col in (
            ("index", "BadYears", "Drop"),
            ("Index_CPI_US", "BadYears_CPI_US", "Drop_CPI_US"),
            ("Index_CPI_IL", "BadYears_CPI_IL", "Drop_CPI_IL"),
        ):
            values = group[value_col].to_numpy(dtype=float)
            years = group["Year"].to_numpy(dtype=float)
            bad_years = []
            drops = []
            for pos, value in enumerate(values):
                future = values[pos:]
                future_years = years[pos:]
                valid = ~np.isnan(future)
                if np.isnan(value) or not valid.any():
                    bad_years.append(np.nan)
                    drops.append(np.nan)
                    continue
                recoverable = future_years[valid & (future <= value)]
                bad_years.append((recoverable.max() - years[pos]) if len(recoverable) else 0)
                drops.append(np.nanmin(future) / value - 1)
            group[years_col] = bad_years
            group[drop_col] = drops
        frames.append(group)
    return pd.concat(frames, ignore_index=True).sort_values(["Year", "Portfolio", "CommissionUse"]).reset_index(drop=True)


def extend_lazy_returns() -> None:
    lazy = _read_parquet("LazyReturns1")
    lazy["Year"] = lazy["Year"].astype(float)
    cpi_il = load_cpi_il()
    usd = load_usd_ils()
    cpi_us = load_cpi_us()

    dec_cpi_il = cpi_il[cpi_il["date"].dt.month == 12].assign(Year=lambda df: df["date"].dt.year)
    dec_usd = usd[usd["date"].dt.month == 12].assign(Year=lambda df: df["date"].dt.year)
    dec_cpi_us = cpi_us[cpi_us["date"].dt.month == 12].assign(Year=lambda df: df["date"].dt.year)
    inflation = (
        dec_cpi_us[["Year", "CPI_US"]]
        .assign(Inflation=lambda df: df["CPI_US"].pct_change() * 100)
        .set_index("Year")["Inflation"]
    )

    new_rows = []
    for portfolio, returns in ANNUAL_RETURNS.items():
        for commission_use in (False, True):
            group = lazy[(lazy["Portfolio"] == portfolio) & (lazy["CommissionUse"] == commission_use)].sort_values("Year")
            previous = group[group["Year"] == 2023].iloc[-1].copy()
            for year, return_pct in returns.items():
                year = int(year)
                cpi_us_value = float(previous["CPI_US"]) * (1 + float(inflation.loc[year]) / 100)
                cpi_il_value = float(dec_cpi_il.loc[dec_cpi_il["Year"] == year, "CPI"].iloc[0])
                usd_value = float(dec_usd.loc[dec_usd["Year"] == year, "dollar"].iloc[0])
                growth = 1 + return_pct / 100
                if commission_use:
                    growth *= 1 - float(previous["commission"]) / 100

                row = previous.copy()
                row["Year"] = float(year)
                row["Inflation"] = float(inflation.loc[year])
                row["CPI_US"] = cpi_us_value
                row["CPI_IL"] = cpi_il_value
                row["USD"] = usd_value
                row["YearReturn"] = return_pct
                row["index"] = float(previous["index"]) * growth
                row["Index_CPI_US"] = float(previous["Index_CPI_US"]) * growth * float(previous["CPI_US"]) / cpi_us_value
                row["Index_CPI_IL"] = (
                    float(previous["Index_CPI_IL"])
                    * growth
                    * usd_value
                    / float(previous["USD"])
                    * float(previous["CPI_IL"])
                    / cpi_il_value
                )
                row["CommissionUse"] = commission_use
                new_rows.append(row)
                previous = row

    lazy = lazy[~((lazy["Portfolio"].isin(ANNUAL_RETURNS)) & (lazy["Year"].isin([2024.0, 2025.0])))]
    lazy = pd.concat([lazy, pd.DataFrame(new_rows)], ignore_index=True)
    lazy = _recalculate_drawdowns(lazy)
    _write_parquet("LazyReturns1", lazy)


def update_manifest() -> None:
    manifest_path = DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generated_at"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest["refresh_version"] = "2024-2025"
    manifest["refresh_sources_file"] = "sources.json"
    for name, obj in manifest["objects"].items():
        frame = _read_parquet(name)
        obj["rows"] = int(len(frame))
        obj["columns"] = int(len(frame.columns))
        obj["names"] = frame.columns.tolist()
        if "date" in frame.columns:
            dates = pd.to_datetime(frame["date"])
            obj["date_range"] = [dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_DIR / "sources.json").write_text(json.dumps(SOURCES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    extend_sp500_monthly()
    extend_lazy_returns()
    update_manifest()


if __name__ == "__main__":
    main()
