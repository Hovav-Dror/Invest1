"""Apply data/data_corrections.json to the converted parquet data.

Run after scripts/apply_manual_data_refresh.py. The script is idempotent: it
sets corrected base values, recomputes every composite portfolio from
PortfoliosStructure, and recomputes all derived annual columns (index,
CPI-adjusted indexes, drawdowns) from YearReturn and Inflation, so a changed
year propagates to every later year.

    python scripts/apply_data_corrections.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from apply_2024_2025_refresh import _recalculate_drawdowns

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CORRECTIONS = json.loads((DATA_DIR / "data_corrections.json").read_text(encoding="utf-8"))
REFRESH = json.loads((DATA_DIR / "manual_refresh_returns.json").read_text(encoding="utf-8"))


def _values(mapping: dict) -> dict:
    """Drop documentation keys such as "_source"."""
    return {key: value for key, value in mapping.items() if not key.startswith("_")}


def _display(name: str) -> str:
    return name.replace("_", " ")


def recompute_lazy(lazy: pd.DataFrame) -> pd.DataFrame:
    """Derived annual columns from YearReturn, Inflation, commission, CPI_IL and USD."""

    out = []
    for (_, commission_use), group in lazy.groupby(["Portfolio", "CommissionUse"], sort=False):
        group = group.sort_values("Year").copy()
        growth = (1 + group["YearReturn"] / 100) * ((1 - group["commission"] / 100) if commission_use else 1)
        index = growth.cumprod()
        cpi_us = (1 + group["Inflation"] / 100).cumprod()
        group["CPI_US"] = cpi_us
        group["index"] = index / index.iloc[0]
        real_us = index / cpi_us
        group["Index_CPI_US"] = real_us / real_us.iloc[0]
        real_il = index / group["CPI_IL"] * group["USD"]
        group["Index_CPI_IL"] = real_il / real_il.dropna().iloc[0] if real_il.notna().any() else real_il
        out.append(group)
    return _recalculate_drawdowns(pd.concat(out, ignore_index=True))


def correct_annual() -> None:
    path = DATA_DIR / "LazyReturns1.parquet"
    lazy = pd.read_parquet(path)

    for asset, years in CORRECTIONS["annual_returns"].items():
        for year, value in _values(years).items():
            mask = (lazy["Portfolio"] == asset) & (lazy["Year"] == float(year))
            if not mask.any():
                raise RuntimeError(f"No rows for {asset} {year}")
            lazy.loc[mask, "YearReturn"] = float(value)

    inflation = _values(CORRECTIONS["inflation"])
    for year, value in inflation.pop("all", {}).items():
        lazy.loc[lazy["Year"] == float(year), "Inflation"] = float(value)
        lazy.loc[(lazy["Portfolio"] == "Inflation") & (lazy["Year"] == float(year)), "YearReturn"] = float(value)
    for asset, years in inflation.items():
        for year, value in years.items():
            lazy.loc[(lazy["Portfolio"] == asset) & (lazy["Year"] == float(year)), "Inflation"] = float(value)

    returns = lazy[~lazy["CommissionUse"]].pivot(index="Year", columns="Portfolio", values="YearReturn")

    for target, rule in _values(CORRECTIONS.get("copy_series", {})).items():
        for year in rule["years"]:
            if year in returns.index and pd.notna(returns.at[year, rule["from"]]):
                value = returns.at[year, rule["from"]]
                lazy.loc[(lazy["Portfolio"] == target) & (lazy["Year"] == float(year)), "YearReturn"] = value
                returns.at[year, target] = value

    structure = pd.read_parquet(DATA_DIR / "PortfoliosStructure.parquet")
    for portfolio, group in structure.groupby("Portfolio"):
        if len(group) == 1 and float(group["weight"].iloc[0]) == 1:
            continue
        name = _display(portfolio)
        assets = [_display(asset) for asset in group["asset"]]
        missing = [asset for asset in assets if asset not in returns]
        if missing:
            raise RuntimeError(f"{name}: missing components {missing}")
        composite = sum(float(weight) * returns[asset] for weight, asset in zip(group["weight"], assets))
        rows = lazy["Portfolio"] == name
        new_values = lazy.loc[rows, "Year"].map(composite)
        keep = new_values.notna()
        lazy.loc[rows & keep.reindex(lazy.index, fill_value=False), "YearReturn"] = new_values[keep]

    apply_fee_basis(lazy, structure)
    lazy = recompute_lazy(lazy)
    lazy.to_parquet(path, index=False)


def apply_fee_basis(lazy: pd.DataFrame, structure: pd.DataFrame) -> None:
    """Set ``commission`` to the fee charged on top of the source return.

    The assumed annual fee for each asset (PortfoliosStructure.commission_i)
    is a total cost. Where the source return is already a fund return, the
    fund's own expense ratio is inside it, so only the remainder is charged:
    max(assumed - embedded, 0). Composites use the weighted sum per year.
    """

    path = DATA_DIR / "fee_basis.json"
    if not path.exists():
        return
    basis = _values(json.loads(path.read_text(encoding="utf-8")))["assets"]

    def embedded(asset: str, year: float) -> float:
        for period in basis.get(asset, {}).get("periods", []):
            if period["from"] <= year <= period["to"]:
                return float(period["expense_ratio_percent"])
        return 0.0

    assumed = (
        structure.assign(asset=structure["asset"].map(_display))
        .groupby("asset")["commission_i"].first()
    )
    lazy["commission"] = lazy["commission"].astype(float)
    for portfolio, group in structure.groupby("Portfolio"):
        name = _display(portfolio)
        rows = lazy["Portfolio"] == name
        components = [(float(w), _display(a)) for w, a in zip(group["weight"], group["asset"])]
        lazy.loc[rows, "commission"] = lazy.loc[rows, "Year"].map(
            lambda year: sum(
                weight * max(float(assumed.get(asset, 0.0)) - embedded(asset, year), 0.0)
                for weight, asset in components
            )
        )


def correct_monthly() -> None:
    settings = _values(CORRECTIONS["sp500_monthly"])
    yields = settings["dividend_yield_percent"]
    cpi_us = {pd.Timestamp(date): value for date, value in _values(CORRECTIONS["us_cpi_monthly"])["values"].items()}

    us = pd.read_parquet(DATA_DIR / "SP500US.parquet")
    div = pd.read_parquet(DATA_DIR / "SP500DIV.parquet")
    for frame in (us, div):
        frame["date"] = pd.to_datetime(frame["date"])

    base_date = pd.Timestamp("2024-01-01")
    value = float(us.loc[us["date"] == base_date, "Real_Total_Return_Price"].iloc[0])
    prices = {}
    for month, official in REFRESH["sp500_monthly_total_return"].items():
        adjusted = float(official) - settings["withholding"] * yields[month] / 12 - settings["fund_fee_percent"] / 12
        value *= 1 + adjusted / 100
        prices[pd.Timestamp(month) + pd.DateOffset(months=1)] = value

    for frame in (us, div):
        mask = frame["date"].isin(prices)
        frame.loc[mask, "Real_Total_Return_Price"] = frame.loc[mask, "date"].map(prices)
    mask = us["date"].isin(cpi_us)
    us.loc[mask, "CPI_US"] = us.loc[mask, "date"].map(cpi_us)
    div["SP500wDividends"] = div["Real_Total_Return_Price"] * div["dollar"]

    if us["CPI_US"].loc[us["date"] >= pd.Timestamp("1871-01-01")].isna().any():
        missing = us.loc[us["CPI_US"].isna(), "date"].dt.strftime("%Y-%m").tolist()
        raise RuntimeError(f"US CPI still missing for {missing}")
    us.to_parquet(DATA_DIR / "SP500US.parquet", index=False)
    div.to_parquet(DATA_DIR / "SP500DIV.parquet", index=False)


def main() -> None:
    correct_annual()
    correct_monthly()
    manifest_path = DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corrections_file"] = "data_corrections.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Applied data/data_corrections.json")


if __name__ == "__main__":
    main()
