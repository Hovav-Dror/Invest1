"""Build data/young_couples_monthly.parquet from the raw files in data/raw.

Columns (one row per calendar month, ``month`` is the first day of the month):

* ``housing_index``: CBS dwelling price index (id 40010, 1993 average = 100).
  The index for a month is based on transactions over that month and the one
  before it, so it lags by about a month.
* ``boi_rate``: Bank of Israel policy rate, average over the month's days, in
  percent per year.
* ``tase_index``: TASE general share index, nominal, a price index without
  dividends, 1993-12 to 2016-08 (empty after). From the 2016 workbook, via
  ``scripts/tase_xlsx_to_csv.R``.

Run from the repo root:

    python scripts/build_young_couples_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "young_couples_monthly.parquet"


def housing_index() -> pd.Series:
    payload = json.loads((RAW / "cbs_housing_price_index_40010.json").read_text(encoding="utf-8"))
    rows = payload["month"][0]["date"]
    bases = {row["currBase"]["baseDesc"] for row in rows}
    if len(bases) != 1:
        raise ValueError(f"Expected one index base, got {bases}")
    series = pd.Series(
        {pd.Timestamp(year=row["year"], month=row["month"], day=1): float(row["currBase"]["value"]) for row in rows}
    ).sort_index()
    expected = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    missing = expected.difference(series.index)
    if len(missing):
        raise ValueError(f"Missing housing index months: {list(missing)}")
    return series.rename("housing_index")


def boi_rate() -> pd.Series:
    frame = pd.read_csv(RAW / "boi_policy_rate_daily.csv", usecols=["TIME_PERIOD", "OBS_VALUE"])
    frame["TIME_PERIOD"] = pd.to_datetime(frame["TIME_PERIOD"])
    daily = frame.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float).sort_index()
    # Calendar-day average: carry each rate forward over weekends and holidays.
    daily = daily.resample("D").ffill()
    monthly = daily.resample("MS").mean()
    # Drop the first (partial) and the current month.
    return monthly.iloc[1:-1].rename("boi_rate")


def tase_index() -> pd.Series:
    frame = pd.read_csv(RAW / "tase_general_index_1993_2016.csv")
    frame["month"] = pd.to_datetime(frame["month"] + "-01")
    return frame.set_index("month")["tase_index"].astype(float)


def main() -> None:
    frame = pd.concat([housing_index(), boi_rate()], axis=1).dropna()
    frame = frame.join(tase_index(), how="left")
    frame.index.name = "month"
    frame = frame.reset_index()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT, index=False)
    print(f"Wrote {len(frame)} months, {frame['month'].min():%Y-%m} to {frame['month'].max():%Y-%m}, to {OUT}")


if __name__ == "__main__":
    main()
