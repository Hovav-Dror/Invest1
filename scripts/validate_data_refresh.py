"""Validate that a manual annual data refresh reached the intended year."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_REFRESH_FILE = DATA_DIR / "manual_refresh_returns.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _failures_for_year(target_year: int, refresh_file: Path) -> list[str]:
    failures: list[str] = []
    refresh = _read_json(refresh_file)
    manifest = _read_json(DATA_DIR / "manifest.json")
    sources = _read_json(DATA_DIR / "sources.json")

    lazy = pd.read_parquet(DATA_DIR / "LazyReturns1.parquet")
    max_year = lazy.groupby("Portfolio")["Year"].max().sort_values()
    stale = max_year[max_year < float(target_year)]
    if not stale.empty:
        failures.append(
            "Portfolios/assets ending before "
            f"{target_year}: {', '.join(f'{name} ({year:g})' for name, year in stale.items())}"
        )

    expected_portfolios = lazy["Portfolio"].nunique()
    for year in range(min(refresh["target_years"]), target_year + 1):
        count = lazy.loc[lazy["Year"] == float(year), "Portfolio"].nunique()
        if count != expected_portfolios:
            failures.append(f"Year {year} has {count} portfolios/assets; expected {expected_portfolios}")
        row_count = len(lazy[lazy["Year"] == float(year)])
        if row_count != expected_portfolios * 2:
            failures.append(f"Year {year} has {row_count} LazyReturns1 rows; expected {expected_portfolios * 2}")

    expected_source_keys = set(refresh["sources"])
    actual_source_keys = set(sources)
    missing_sources = sorted(expected_source_keys - actual_source_keys)
    extra_sources = sorted(actual_source_keys - expected_source_keys)
    if missing_sources:
        failures.append(f"sources.json is missing keys from refresh file: {', '.join(missing_sources)}")
    if extra_sources:
        failures.append(f"sources.json has keys not present in refresh file: {', '.join(extra_sources)}")

    expected_tickers = refresh["sources"].get("etf_proxy_annual_returns", {}).get("tickers", [])
    actual_tickers = sources.get("etf_proxy_annual_returns", {}).get("tickers", [])
    if sorted(expected_tickers) != sorted(actual_tickers):
        failures.append("ETF proxy ticker list in sources.json does not match the refresh file")

    manifest_rows = manifest["objects"]["LazyReturns1"]["rows"]
    if manifest_rows != len(lazy):
        failures.append(f"manifest LazyReturns1 rows={manifest_rows}; actual rows={len(lazy)}")
    if manifest.get("refresh_data_file") != str(refresh_file.relative_to(ROOT)):
        failures.append("manifest refresh_data_file does not point at the active refresh file")
    if manifest.get("refresh_sources_file") != "sources.json":
        failures.append("manifest refresh_sources_file should be sources.json")

    sp500_us = pd.read_parquet(DATA_DIR / "SP500US.parquet")
    sp500_div = pd.read_parquet(DATA_DIR / "SP500DIV.parquet")
    expected_month_end = pd.Timestamp(f"{target_year + 1}-01-01")
    for name, frame in (("SP500US", sp500_us), ("SP500DIV", sp500_div)):
        max_date = pd.to_datetime(frame["date"]).max()
        if max_date < expected_month_end:
            failures.append(f"{name} ends at {max_date:%Y-%m-%d}; expected at least {expected_month_end:%Y-%m-%d}")

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-year", type=int, default=None, help="Final calendar year expected in LazyReturns1.")
    parser.add_argument(
        "--refresh-file",
        type=Path,
        default=DEFAULT_REFRESH_FILE,
        help="Structured refresh file used by apply_2024_2025_refresh.py.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    refresh_file = args.refresh_file if args.refresh_file.is_absolute() else ROOT / args.refresh_file
    refresh = _read_json(refresh_file)
    target_year = args.through_year or max(int(year) for year in refresh["target_years"])
    failures = _failures_for_year(target_year, refresh_file)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)
    print(f"OK: manual refresh reaches {target_year} for all portfolios/assets.")


if __name__ == "__main__":
    main()
