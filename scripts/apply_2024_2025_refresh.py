"""Apply a structured source-data refresh to converted parquet data.

This is intentionally small and explicit: the app currently consumes converted
server-side parquet files, while the original R `.rda` source is not part of
this repository. The script extends the migrated data with rows from
data/manual_refresh_returns.json, then records those sources in the manifest.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_REFRESH_FILE = DATA_DIR / "manual_refresh_returns.json"


def load_refresh_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    config["target_years"] = [int(year) for year in config["target_years"]]
    config["composite_years"] = [int(year) for year in config.get("composite_years", config["target_years"])]
    config["sp500_monthly_total_return"] = {
        date: float(return_pct)
        for date, return_pct in config["sp500_monthly_total_return"].items()
    }
    config["annual_returns"] = {
        portfolio: {int(year): float(return_pct) for year, return_pct in returns.items()}
        for portfolio, returns in config["annual_returns"].items()
    }
    return config


REFRESH_CONFIG = load_refresh_config(DEFAULT_REFRESH_FILE)
REFRESH_FILE = DEFAULT_REFRESH_FILE
SOURCES = REFRESH_CONFIG["sources"]


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


def _display_name(name: str) -> str:
    return name.replace("_", " ")


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
    for return_month, return_pct in REFRESH_CONFIG["sp500_monthly_total_return"].items():
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


def annual_returns_with_composites() -> dict[str, dict[int, float]]:
    returns = {portfolio: dict(years) for portfolio, years in REFRESH_CONFIG["annual_returns"].items()}
    returns["Global ex US Stock Market"] = {
        year: 0.6 * returns["S&P 500"][year] + 0.4 * returns["MSCI World ex USA index"][year]
        for year in REFRESH_CONFIG["composite_years"]
    }
    structure = _read_parquet("PortfoliosStructure")
    for portfolio, group in structure.groupby("Portfolio", sort=False):
        display_portfolio = _display_name(portfolio)
        if display_portfolio in returns:
            continue
        if len(group) == 1 and float(group["weight"].iloc[0]) == 1:
            continue

        derived: dict[int, float] = {}
        for year in REFRESH_CONFIG["composite_years"]:
            total_return = 0.0
            for _, component in group.iterrows():
                asset = _display_name(str(component["asset"]))
                asset_returns = returns.get(asset)
                if not asset_returns or year not in asset_returns:
                    break
                total_return += float(component["weight"]) * float(asset_returns[year])
            else:
                derived[year] = total_return
        if derived:
            returns[display_portfolio] = derived
    return returns


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

    def yearly_value(source: pd.DataFrame, column: str, year: int, fallback_column: str) -> float:
        values = source.loc[source["Year"] == year, column].dropna()
        if not values.empty:
            return float(values.iloc[0])
        existing = lazy.loc[lazy["Year"] == float(year), fallback_column].dropna()
        if existing.empty:
            raise RuntimeError(f"Missing {fallback_column} value for {year}")
        return float(existing.iloc[0])

    new_rows = []
    annual_returns = annual_returns_with_composites()
    annual_returns["Inflation"] = {
        year: float(inflation.loc[year])
        for year in REFRESH_CONFIG["target_years"]
        if year in inflation.index
    }
    for portfolio, returns in annual_returns.items():
        for commission_use in (False, True):
            group = lazy[(lazy["Portfolio"] == portfolio) & (lazy["CommissionUse"] == commission_use)].sort_values("Year")
            if group.empty:
                continue
            first_year = min(returns)
            prior = group[group["Year"] < first_year]
            if prior.empty:
                continue
            previous = prior.iloc[-1].copy()
            for year, return_pct in sorted(returns.items()):
                year = int(year)
                cpi_us_value = float(previous["CPI_US"]) * (1 + float(inflation.loc[year]) / 100)
                cpi_il_value = yearly_value(dec_cpi_il, "CPI", year, "CPI_IL")
                usd_value = yearly_value(dec_usd, "dollar", year, "USD")
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

    refresh_pairs = {
        (portfolio, float(year))
        for portfolio, returns in annual_returns.items()
        for year in returns
    }
    refresh_mask = lazy.apply(lambda row: (row["Portfolio"], float(row["Year"])) in refresh_pairs, axis=1)
    lazy = lazy[~refresh_mask]
    lazy = pd.concat([lazy, pd.DataFrame(new_rows)], ignore_index=True)
    lazy = _recalculate_drawdowns(lazy)
    _write_parquet("LazyReturns1", lazy)


def update_manifest() -> None:
    manifest_path = DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        refresh_data_file = str(REFRESH_FILE.relative_to(ROOT))
    except ValueError:
        refresh_data_file = str(REFRESH_FILE)
    manifest["generated_at"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest["refresh_version"] = REFRESH_CONFIG["refresh_version"]
    manifest["refresh_data_file"] = refresh_data_file
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-file",
        type=Path,
        default=DEFAULT_REFRESH_FILE,
        help="Structured annual/monthly refresh data file.",
    )
    return parser.parse_args()


def main() -> None:
    global REFRESH_CONFIG, REFRESH_FILE, SOURCES
    args = parse_args()
    refresh_file = args.refresh_file if args.refresh_file.is_absolute() else ROOT / args.refresh_file
    REFRESH_FILE = refresh_file
    REFRESH_CONFIG = load_refresh_config(refresh_file)
    SOURCES = REFRESH_CONFIG["sources"]
    extend_sp500_monthly()
    extend_lazy_returns()
    update_manifest()


if __name__ == "__main__":
    main()
