"""Build data/young_couples_monthly.parquet from the raw files in data/raw.

Columns (one row per calendar month, ``month`` is the first day of the month,
from 1986-01):

* ``housing_index``: dwelling prices, on the base of the CBS dwelling price
  index (id 40010, 1993 average = 100). From 1994-01 it is that index; the
  index for a month is based on transactions over that month and the one
  before it, so it lags by about a month. Before 1994 it is the CBS CPI
  component "owner-occupied housing services" (id 120490), chained back from
  1994-01. Until 1998 the CBS measured that component as the dwelling price
  times a fixed yield, so it moved with dwelling prices; from 1999 it follows
  rents and is not used. Over 1995-1998 the two moved together (correlation of
  12-month changes 0.91).
* ``boi_rate``: the return on cash before costs, percent per year. From
  1994-02 the Bank of Israel policy rate, averaged over the month's days.
  Before that, the average yield to maturity on one-month makam (Bank of Israel
  annual reports, see ``boi_makam_yield_1986_1994.csv``; 1986, 1987 and
  April-December 1991 are annual averages). The reports give an effective
  annual yield, so it is converted to the nominal annual rate with the same
  monthly return, ``12 * ((1 + y) ** (1 / 12) - 1)``, to match the policy rate,
  which the calculations divide by 12.
* ``rate_source``: ``boi_rate`` or ``makam``.
* ``tase_index``: Israeli shares, nominal, a price index without dividends.
  TASE general share index to 2016-08 (from 1993-12 the workbook's nominal
  index; before that the workbook's real index times the CBS CPI, scaled to
  meet it at 1993-12), then TA-125 month-end closes from Yahoo Finance,
  chained at 2016-08. Over 1994-2016 the monthly changes of the two indices
  have a correlation of 0.97.

Run from the repo root (after ``Rscript scripts/tase_xlsx_to_csv.R``):

    python scripts/build_young_couples_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "young_couples_monthly.parquet"
START = pd.Timestamp("1986-01-01")
SPLICE = pd.Timestamp("1994-01-01")


def _cbs_rows(name: str) -> list[dict]:
    payload = json.loads((RAW / name).read_text(encoding="utf-8"))
    return payload["month"][0]["date"]


def _cbs_chained(name: str) -> pd.Series:
    """A CBS index chained from its monthly percent changes (the base changes over time), first month = 1."""

    rows = sorted(_cbs_rows(name), key=lambda row: (row["year"], row["month"]))
    months = [pd.Timestamp(year=row["year"], month=row["month"], day=1) for row in rows]
    change = pd.Series([1 + (row["percent"] or 0.0) / 100 for row in rows], index=months)
    change.iloc[0] = 1.0
    _require_complete(change, name)
    return change.cumprod()


def _require_complete(series: pd.Series, name: str) -> None:
    expected = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    missing = expected.difference(series.index)
    if len(missing):
        raise ValueError(f"Missing months in {name}: {list(missing)}")


def housing_index() -> pd.Series:
    rows = _cbs_rows("cbs_housing_price_index_40010.json")
    bases = {row["currBase"]["baseDesc"] for row in rows}
    if len(bases) != 1:
        raise ValueError(f"Expected one index base, got {bases}")
    series = pd.Series(
        {pd.Timestamp(year=row["year"], month=row["month"], day=1): float(row["currBase"]["value"]) for row in rows}
    ).sort_index()
    _require_complete(series, "dwelling price index")
    owner = _cbs_chained("cbs_owner_housing_120490_1983_1998.json")
    before = owner[owner.index < SPLICE] / owner[SPLICE] * series[SPLICE]
    return pd.concat([before, series]).rename("housing_index")


def policy_rate() -> pd.Series:
    frame = pd.read_csv(RAW / "boi_policy_rate_daily.csv", usecols=["TIME_PERIOD", "OBS_VALUE"])
    frame["TIME_PERIOD"] = pd.to_datetime(frame["TIME_PERIOD"])
    daily = frame.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float).sort_index()
    # Calendar-day average: carry each rate forward over weekends and holidays.
    daily = daily.resample("D").ffill()
    monthly = daily.resample("MS").mean()
    # Drop the first (partial) and the current month.
    return monthly.iloc[1:-1]


def cash_rate() -> pd.DataFrame:
    boi = policy_rate()
    makam = pd.read_csv(RAW / "boi_makam_yield_1986_1994.csv")
    makam = pd.Series(makam["makam_yield"].to_numpy(float), index=pd.to_datetime(makam["month"] + "-01"))
    # Effective annual yield -> nominal annual rate compounded monthly (percent).
    makam = 1200 * ((1 + makam / 100) ** (1 / 12) - 1)
    _require_complete(makam, "makam yields")
    makam = makam[makam.index < boi.index.min()]
    if makam.index.max() + pd.DateOffset(months=1) != boi.index.min():
        raise ValueError("The makam yields must end the month before the policy rate starts.")
    rate = pd.concat([makam, boi])
    source = pd.Series(["makam"] * len(makam) + ["boi_rate"] * len(boi), index=rate.index)
    return pd.DataFrame({"boi_rate": rate, "rate_source": source})


def tase_index() -> pd.Series:
    frame = pd.read_csv(RAW / "tase_general_index_1979_2016.csv")
    frame.index = pd.to_datetime(frame["month"] + "-01")
    nominal = frame["tase_index"].astype(float)
    anchor = nominal.first_valid_index()
    cpi = _cbs_chained("cbs_cpi_120010_1983_1993.json")
    early = frame.index[(frame.index >= START - pd.DateOffset(months=1)) & (frame.index < anchor)]
    # Nominal = real x CPI; the CPI file ends 1993-12, which is the anchor month.
    rebuilt = frame.loc[early, "tase_real"] * cpi[early] / (frame.loc[anchor, "tase_real"] * cpi[anchor]) * nominal[anchor]
    general = pd.concat([rebuilt, nominal.loc[anchor:].dropna()])
    # After the workbook ends, continue with TA-125 (month-end close), chained at the last common month.
    ta125 = pd.read_csv(RAW / "ta125_yahoo_monthly_1992_2026.csv")
    ta125 = pd.Series(ta125["ta125_close"].to_numpy(float), index=pd.to_datetime(ta125["month"] + "-01"))
    _require_complete(ta125, "TA-125")
    last = general.index.max()
    later = ta125[ta125.index > last] / ta125[last] * general[last]
    return pd.concat([general, later]).rename("tase_index")


def main() -> None:
    frame = pd.concat([housing_index(), cash_rate()], axis=1).dropna()
    frame = frame[frame.index >= START].join(tase_index(), how="left")
    frame.index.name = "month"
    frame = frame.reset_index()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT, index=False)
    print(f"Wrote {len(frame)} months, {frame['month'].min():%Y-%m} to {frame['month'].max():%Y-%m}, to {OUT}")


if __name__ == "__main__":
    main()
