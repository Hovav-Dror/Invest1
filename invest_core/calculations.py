"""Server-side investment calculations.

Originally ported from the Shiny/R app. Version 2 replaces the R parity
behaviour with independently specified rules; see docs/methodology.md.

Conventions used throughout:

* Monthly rows are boundaries. A row dated ``d`` holds the S&P 500 total
  return level for that boundary. Before ``PRICE_POINT_IN_TIME_FROM`` the level
  is a Shiller monthly average for month ``d``; from then on it is the first
  observation of month ``d`` (that is, the end of month ``d-1``). Source FX and
  CPI columns hold observations for month ``d`` (FX at month end), so they are
  re-aligned per era by ``monthly_market``.
* Annual rows: ``YearReturn`` is the return during the year, and ``CPI_*``/``USD``
  are year-end observations. The first row of each series is a base row.
* Israeli tax is an educational model: 25% of the real (CPI-indexed) gain at
  realization, never a refund on losses. Realized losses are carried forward
  against later gains.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from invest_core.data import InvestData, load_data

CALCULATION_VERSION = "2.0.0"

TAX_RATE = 0.25
PRICE_POINT_IN_TIME_FROM = pd.Timestamp("2011-02-01")

DEFAULT_TAX_START = "1993-01-01"
DEFAULT_TAX_END = "2026-01-01"
DEFAULT_COMMISSIONS = (0.0, 0.2, 0.7)
DEFAULT_KUPAT_START_YEAR = 1995
DEFAULT_KUPAT_AGE = 40
DEFAULT_KUPAT_INITIAL = 70000
DEFAULT_KUPAT_PENSION_MONTHS = 250
DEFAULT_INDEPENDENT_START = "2000-01-01"
DEFAULT_INDEPENDENT_END = "2026-01-01"
DEFAULT_TRINITY_PORTFOLIO = "S&P 500"
DEFAULT_TRINITY_DRAW = 0.04
DEFAULT_TRINITY_YEARS = 30
DEFAULT_TRINITY_BASE = 4_000_000

DEFAULT_PORTFOLIOS = (
    "S&P 500",
    "MSCI World ex USA index",
    "US Large Cap Value",
    "US Large Cap Growth",
    "US Mid Cap Value",
    "US Small Cap Value",
    "Short Term Treasury",
    "Precious Metals",
    "European Stocks",
    "Bogleheads Three Funds",
    "Bill Bernstein No Brainer",
    "Growth Portfolio",
    "Conservative Portfolio",
    "Bill Schultheis Coffee house",
    "Emerging Markets",
    "David Swensen Lazy",
    "David Swensen Yale Endowment",
    "Ray Dalio All Seasons",
    "~Ben Felix five-factor model portfolio",
    "השילוש הקדוש",
)


class CalculationInputError(ValueError):
    """Raised when calculation inputs cannot produce a meaningful result."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _as_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value)


def _monthly_fee_factor(annual_percent: float) -> float:
    """Monthly multiplier that removes exactly ``annual_percent`` per year."""

    if not np.isfinite(annual_percent) or not 0 <= annual_percent < 100:
        raise CalculationInputError("דמי הניהול חייבים להיות בין 0 ל-100 אחוזים.")
    return (1 - annual_percent / 100) ** (1 / 12)


def monthly_market(data: InvestData) -> pd.DataFrame:
    """Return the monthly S&P 500 series with FX and CPI aligned to each boundary.

    Columns: date, price (USD total return level), fx (ILS per USD), cpi_il,
    cpi_us, value_ils (price * fx).
    """

    frame = (
        data.SP500DIV[["date", "Real_Total_Return_Price", "dollar", "CPI"]]
        .merge(data.SP500US[["date", "CPI_US"]], on="date", how="left")
        .sort_values("date")
        .reset_index(drop=True)
        .rename(columns={"Real_Total_Return_Price": "price", "dollar": "fx", "CPI": "cpi_il", "CPI_US": "cpi_us"})
    )
    # Fill isolated interior CPI gaps (e.g. US CPI for 2024-01) geometrically.
    for column in ("cpi_il", "cpi_us"):
        log_values = np.log(frame[column])
        frame[column] = np.exp(log_values.interpolate(limit_area="inside"))

    point_in_time = frame["date"] >= PRICE_POINT_IN_TIME_FROM
    for column in ("fx", "cpi_il", "cpi_us"):
        frame[column] = frame[column].where(~point_in_time, frame[column].shift(1))
    frame["value_ils"] = frame["price"] * frame["fx"]
    return frame


def _monthly_window(
    data: InvestData,
    start: str | pd.Timestamp | None,
    end: str | pd.Timestamp | None,
    columns: Iterable[str],
) -> pd.DataFrame:
    """Slice ``monthly_market`` to [start, end] and the rows where ``columns`` are valid."""

    columns = list(columns)
    frame = monthly_market(data)
    if start is not None:
        frame = frame[frame["date"] >= _as_timestamp(start)]
    if end is not None:
        frame = frame[frame["date"] <= _as_timestamp(end)]
    valid = frame[columns].notna().all(axis=1) & (frame[columns] > 0).all(axis=1)
    if not valid.any():
        raise CalculationInputError("אין נתונים בטווח שנבחר. נסו טווח אחר.")
    first, last = valid.idxmax(), valid[::-1].idxmax()
    frame = frame.loc[first:last].reset_index(drop=True)
    if not valid.loc[first:last].all():
        raise CalculationInputError("חסרים נתונים באמצע הטווח שנבחר.")
    if len(frame) < 2:
        raise CalculationInputError("הטווח שנבחר קצר מדי. בחרו לפחות חודשיים.")
    return frame


def _tax_ledger(
    value: np.ndarray,
    cpi: np.ndarray,
    every: int | None,
    fee_factor: float = 1.0,
) -> np.ndarray:
    """Value after hypothetical liquidation at every boundary, with periodic realizations.

    ``value`` is the nominal asset level and ``cpi`` the matching CPI.
    With ``every`` set, the whole position is sold and re-bought every
    ``every`` months: tax is paid on the real gain since the last purchase,
    the cost basis resets, and real losses are carried forward against later
    gains. Every point shows what would remain after selling everything then.
    """

    result = np.empty(len(value), dtype=float)
    holding = 1.0
    basis = 1.0
    basis_cpi = cpi[0]
    loss_carry = 0.0
    result[0] = 1.0
    for pos in range(1, len(value)):
        holding *= value[pos] / value[pos - 1] * fee_factor
        real_gain = holding - basis * cpi[pos] / basis_cpi
        if every and pos % every == 0:
            if real_gain >= 0:
                offset = min(loss_carry, real_gain)
                loss_carry -= offset
                holding -= TAX_RATE * (real_gain - offset)
            else:
                loss_carry -= real_gain
            basis, basis_cpi = holding, cpi[pos]
            result[pos] = holding
        else:
            result[pos] = holding - TAX_RATE * max(real_gain - loss_carry, 0.0)
    return result


def _real_after_tax(nominal: np.ndarray, cpi_ratio: np.ndarray, basis: float = 1.0) -> np.ndarray:
    """Nominal value after 25% tax on the CPI-indexed gain over ``basis``."""

    return nominal - TAX_RATE * np.maximum(nominal - basis * cpi_ratio, 0.0)


# ---------------------------------------------------------------------------
# Tax events and management fees (monthly, S&P 500 in shekels)
# ---------------------------------------------------------------------------


def _tax_scenarios(
    data: InvestData,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    annual_fee: float,
) -> pd.DataFrame:
    frame = _monthly_window(data, start, end, ["value_ils", "cpi_il"])
    value = frame["value_ils"].to_numpy()
    cpi = frame["cpi_il"].to_numpy()
    fee = _monthly_fee_factor(annual_fee)
    frame["gross"] = value / value[0]
    frame["cpi_ratio"] = cpi / cpi[0]
    frame["with_fee"] = frame["gross"] * fee ** np.arange(len(frame))
    frame["at_end"] = _tax_ledger(value, cpi, None, fee)
    frame["every_1"] = _tax_ledger(value, cpi, 1, fee)
    frame["every_6"] = _tax_ledger(value, cpi, 6, fee)
    frame["every_12"] = _tax_ledger(value, cpi, 12, fee)
    return frame


def tax_events(
    data: InvestData | None = None,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """S&P 500 in shekels: tax once at the end vs selling every 1, 6 or 12 months."""

    frame = _tax_scenarios(data or load_data(), start, end, 0.0)
    scale = initial / (frame["cpi_ratio"] if adjust_cpi else 1.0)
    result = pd.DataFrame(
        {
            "date": frame["date"],
            "v": frame["gross"] * scale,
            "Gain_i": frame["gross"].pct_change().fillna(0) + 1,
            "End25": frame["at_end"] * scale,
            "EveryMonth": frame["every_1"] * scale,
            "EveryNMonths": frame["every_6"] * scale,
            "Every12Months": frame["every_12"] * scale,
        }
    )
    result["Gain"] = (result["EveryMonth"].pct_change().fillna(0) + 1).to_numpy()
    return result


def commission_tax(
    data: InvestData | None = None,
    commission: float = 0.0,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Tax-event scenarios with an annual management fee (percent per year)."""

    frame = _tax_scenarios(data or load_data(), start, end, commission)
    scale = initial / (frame["cpi_ratio"] if adjust_cpi else 1.0)
    return pd.DataFrame(
        {
            "date": frame["date"],
            "SP500_in_NIS": frame["gross"] * scale,
            "tax_at_end": frame["at_end"] * scale,
            "tax_every_month": frame["every_1"] * scale,
            "tax_every_6_months": frame["every_6"] * scale,
            "tax_every_12_months": frame["every_12"] * scale,
            "commission": commission,
        }
    )


def commission_tax_scenarios(
    data: InvestData | None = None,
    commissions: Iterable[float] = DEFAULT_COMMISSIONS,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Stack ``commission_tax`` for several fee levels."""

    data = data or load_data()
    frames = [
        commission_tax(data=data, commission=commission, start=start, end=end, adjust_cpi=adjust_cpi, initial=initial)
        for commission in commissions
    ]
    return pd.concat(frames, ignore_index=True)


def commission_effect(
    data: InvestData | None = None,
    commissions: Iterable[float] = DEFAULT_COMMISSIONS,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Alias of ``commission_tax_scenarios`` kept for the API."""

    return commission_tax_scenarios(data, commissions, start, end, adjust_cpi, initial)


# ---------------------------------------------------------------------------
# S&P 500 rolling risk (monthly, real US dollars)
# ---------------------------------------------------------------------------


def sp500_risk(
    data: InvestData | None = None,
    years: int = 15,
    threshold: float = 0.04,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Rolling annualized real (US-CPI adjusted) S&P 500 return for every N-year window."""

    frame = _monthly_window(data or load_data(), start, end, ["price", "cpi_us"])
    period = years * 12
    if len(frame) <= period:
        raise CalculationInputError("הטווח שנבחר קצר מאורך החלון.")
    real = frame["price"] / frame["cpi_us"]
    frame["TotalReturn"] = real / real.shift(period)
    frame = frame.dropna(subset=["TotalReturn"]).copy()
    frame["TotalReturnP"] = frame["TotalReturn"] ** (1 / years) - 1
    frame["Median"] = frame["TotalReturnP"].median()
    frame["Above0"] = (frame["TotalReturnP"] > 0).mean()
    frame["AboveThreshold"] = (frame["TotalReturnP"] > threshold).mean()
    return frame[["date", "TotalReturn", "TotalReturnP", "Median", "Above0", "AboveThreshold"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Lazy portfolios (annual)
# ---------------------------------------------------------------------------

VALUE_COLUMNS = {
    "cpi_il": "Index_CPI_IL",
    "cpi_us": "Index_CPI_US",
    "nominal": "index",
}


def _underwater(values: np.ndarray, years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For an investor buying at each year end: worst later loss and years until last below cost."""

    drops = np.full(len(values), np.nan)
    shefel = np.full(len(values), np.nan)
    for pos, value in enumerate(values):
        if np.isnan(value):
            continue
        future = values[pos:]
        valid = ~np.isnan(future)
        drops[pos] = np.nanmin(future) / value - 1
        below = valid & (future <= value)
        shefel[pos] = years[pos:][below].max() - years[pos]
    return drops, shefel


def _portfolio_window(
    data: InvestData,
    portfolios: Iterable[str],
    year_start: int,
    year_end: int,
    commission_adjusted: bool,
    value_mode: str,
) -> pd.DataFrame:
    """Annual rows for each portfolio from its base year (year_start - 1, or first available)."""

    if value_mode not in VALUE_COLUMNS:
        raise ValueError(f"Unknown value_mode: {value_mode}")
    value_column = VALUE_COLUMNS[value_mode]
    source = data.LazyReturns1
    frame = source[
        (source["CommissionUse"] == commission_adjusted)
        & (source["Portfolio"].isin(set(portfolios)))
        & (source["Year"] >= year_start - 1)
        & (source["Year"] <= year_end)
        & source[value_column].notna()
    ].sort_values(["Portfolio", "Year"])

    groups = []
    for _, group in frame.groupby("Portfolio", sort=True):
        group = group.copy()
        years = group["Year"].to_numpy(dtype=float)
        if len(group) < 2:
            continue
        if (np.diff(years) != 1).any():
            raise CalculationInputError("חסרות שנים בסדרת הנתונים של אחד התיקים.")
        group["v"] = group[value_column] / group[value_column].iloc[0]
        group["Drop"], group["ShefelYears"] = _underwater(group["v"].to_numpy(), years)
        group["is_base"] = np.arange(len(group)) == 0
        groups.append(group)
    if not groups:
        raise CalculationInputError("אין נתונים לתיקים ולטווח שנבחרו.")
    return pd.concat(groups, ignore_index=True)


def portfolio_table(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2025,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
) -> pd.DataFrame:
    """Normalized annual rows (base row excluded) with drawdown columns."""

    frame = _portfolio_window(data or load_data(), portfolios, year_start, year_end, commission_adjusted, value_mode)
    return frame[~frame["is_base"]].drop(columns=["is_base"]).reset_index(drop=True)


def portfolio_summary(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2025,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
) -> pd.DataFrame:
    """Per-portfolio CAGR, volatility of annual returns, worst drop and longest underwater period."""

    frame = _portfolio_window(data or load_data(), portfolios, year_start, year_end, commission_adjusted, value_mode)
    rows: list[dict[str, float | str]] = []
    for portfolio, group in frame.groupby("Portfolio", sort=True):
        n = len(group) - 1
        cagr = group["v"].iloc[-1] ** (1 / n) - 1
        rows.append(
            {
                "Portfolio": portfolio,
                "FirstYear": group["Year"].iloc[1],
                "N": n,
                "SD": group["v"].pct_change().std(ddof=1),
                "CAGR": cagr,
                "MaxDrop": group["Drop"].min(),
                "MaxShefelYears": group["ShefelYears"].max(),
                "Factor15": (1 + cagr) ** 15,
            }
        )
    return pd.DataFrame(rows, columns=["Portfolio", "FirstYear", "N", "SD", "CAGR", "MaxDrop", "MaxShefelYears", "Factor15"])


def portfolio_structure(data: InvestData | None = None) -> pd.DataFrame:
    """Lazy-portfolio component weights, one column per asset."""

    data = data or load_data()
    frame = data.PortfoliosStructure.copy()
    frame = frame.loc[frame["weight"] < 1, ["Portfolio", "weight", "asset"]].copy()
    frame["asset"] = frame["asset"].str.replace("_", " ", regex=False)
    return (
        frame.pivot(index="Portfolio", columns="asset", values="weight")
        .reset_index()
        .rename_axis(None, axis=1)
    )


def portfolio_commissions(data: InvestData | None = None) -> pd.DataFrame:
    """Assumed annual management fee for each lazy portfolio."""

    data = data or load_data()
    frame = data.PortfoliosStructure.copy()
    frame = frame.groupby("Portfolio", sort=True, as_index=False).first()
    frame["Portfolio"] = frame["Portfolio"].str.replace("_", " ", regex=False)
    return frame.loc[:, ["Portfolio", "commission"]].rename(columns={"commission": "Assumed Commission"})


def _rolling_cagr(values: pd.Series, years: int) -> pd.Series:
    return (values / values.shift(years)) ** (1 / years) - 1


def portfolio_over_time(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2025,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
    rolling_window: int | None = None,
    full_history_rolling: bool = False,
) -> pd.DataFrame:
    """Accumulated value, annual return, CAGR since start and rolling CAGR per portfolio.

    With ``full_history_rolling`` the rolling windows may reach back before
    ``year_start``; values are still normalized to the selected start.
    """

    data = data or load_data()
    history_start = 1871 if full_history_rolling else year_start
    frame = _portfolio_window(data, portfolios, history_start, year_end, commission_adjusted, value_mode)
    frames = []
    for _, group in frame.groupby("Portfolio", sort=True):
        group = group.copy()
        base_year = max(group["Year"].iloc[0], year_start - 1)
        base = group.loc[group["Year"] == base_year, "v"]
        if base.empty:
            continue
        group["v"] = group["v"] / base.iloc[0]
        group["N"] = group["Year"] - base_year
        group["OneYear"] = group["v"].pct_change()
        group["CAGR"] = group["v"] ** (1 / group["N"].where(group["N"] > 0)) - 1
        group["CAGR10"] = _rolling_cagr(group["v"], 10)
        columns = ["Year", "Portfolio", "v", "ShefelYears", "Drop", "N", "OneYear", "CAGR", "CAGR10"]
        if rolling_window is not None:
            group["RollingCAGR"] = _rolling_cagr(group["v"], rolling_window)
            columns.append("RollingCAGR")
        group = group[group["Year"] > base_year]
        frames.append(group[columns])
    if not frames:
        raise CalculationInputError("אין נתונים לתיקים ולטווח שנבחרו.")
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# US vs world (annual, nominal USD)
# ---------------------------------------------------------------------------

GLOBAL_MIX_LABEL = "תיק גלובלי 60/40"


def _us_world_levels(data: InvestData, global_mix: bool, year_end: int | None) -> pd.DataFrame:
    """Cumulative nominal USD levels by year, including a base row of 1 before the first year."""

    source = data.LazyReturns1
    frame = source.loc[
        (~source["CommissionUse"])
        & (source["Portfolio"].isin(["S&P 500", "MSCI World ex USA index"])),
        ["Year", "Portfolio", "YearReturn"],
    ]
    if year_end is not None:
        frame = frame[frame["Year"] <= year_end]
    wide = frame.pivot(index="Year", columns="Portfolio", values="YearReturn").dropna().sort_index() / 100
    if global_mix:
        wide[GLOBAL_MIX_LABEL] = 0.6 * wide["S&P 500"] + 0.4 * wide["MSCI World ex USA index"]
        wide = wide[["S&P 500", GLOBAL_MIX_LABEL]]
    levels = (1 + wide).cumprod()
    base = pd.DataFrame(1.0, index=[levels.index[0] - 1], columns=levels.columns)
    return pd.concat([base, levels])


def us_global_rolling(data: InvestData | None = None, global_mix: bool = False, year_end: int | None = None) -> pd.DataFrame:
    """S&P 500 minus ex-US (or a 60/40 mix) in rolling 5/10/15-year annualized growth factors."""

    levels = _us_world_levels(data or load_data(), global_mix, year_end)
    other = GLOBAL_MIX_LABEL if global_mix else "MSCI World ex USA index"
    result = pd.DataFrame({"Year": levels.index})
    for years, column in ((5, "Diff5"), (10, "Diff10"), (15, "Diff15")):
        growth = (levels / levels.shift(years)) ** (1 / years)
        result[column] = (growth["S&P 500"] - growth[other]).to_numpy()
    return result.dropna(subset=["Diff5"]).reset_index(drop=True)


def us_world_rolling(data: InvestData | None = None, year_end: int | None = None) -> pd.DataFrame:
    """S&P 500 vs MSCI World ex USA rolling differences."""

    return us_global_rolling(data=data, global_mix=False, year_end=year_end)


def _pair_heatmap(levels: pd.DataFrame, first: str, second: str, max_years: int) -> pd.DataFrame:
    """Every start/end year pair up to ``max_years``: returns of both series and their difference."""

    levels = levels.reindex(range(int(levels.index.min()), int(levels.index.max()) + 1))
    years = levels.index.to_numpy(dtype=float)
    a = levels[first].to_numpy(dtype=float)
    b = levels[second].to_numpy(dtype=float)
    chunks = []
    for length in range(1, min(max_years, len(years) - 1) + 1):
        val1 = a[length:] / a[:-length] - 1
        val2 = b[length:] / b[:-length] - 1
        cagr1 = (val1 + 1) ** (1 / length) - 1
        cagr2 = (val2 + 1) ** (1 / length) - 1
        end_years = years[length:]
        chunks.append(
            pd.DataFrame(
                {
                    "StartYear": end_years - length + 1,
                    "EndYear": end_years,
                    "InvYears": float(length),
                    "Portfolio": first,
                    "Portfolio2": second,
                    "val1": val1,
                    "val2": val2,
                    "cagr1": cagr1,
                    "cagr2": cagr2,
                    "delta_value": val2 - val1,
                    "delta_cagr": cagr2 - cagr1,
                }
            )
        )
    result = pd.concat(chunks, ignore_index=True).dropna(subset=["val1", "val2"])
    return result.sort_values(["StartYear", "EndYear"], ignore_index=True)


def global_vs_sp500_heatmap(data: InvestData | None = None, max_years: int = 20, year_end: int | None = None) -> pd.DataFrame:
    """60/40 global mix minus S&P 500 for every start/end pair (nominal USD)."""

    levels = _us_world_levels(data or load_data(), True, year_end)
    return _pair_heatmap(levels, "S&P 500", GLOBAL_MIX_LABEL, max_years)


# ---------------------------------------------------------------------------
# S&P 500 vs US small-cap value (annual, real shekels)
# ---------------------------------------------------------------------------


def _scv_frame(data: InvestData, year_end: int | None) -> pd.DataFrame:
    source = data.LazyReturns1
    frame = source.loc[
        (~source["CommissionUse"])
        & (source["Portfolio"].isin(["S&P 500", "US Small Cap Value"]))
        & source["Index_CPI_IL"].notna(),
        ["Year", "Portfolio", "CPI_IL", "USD", "index"],
    ]
    if year_end is not None:
        frame = frame[frame["Year"] <= year_end]
    return frame


def sp500_scv_rolling(
    data: InvestData | None = None,
    window: int = 15,
    after_tax: bool = False,
    year_end: int | None = None,
) -> pd.DataFrame:
    """Rolling real-shekel CAGR of S&P 500 vs US small-cap value, optionally after tax at the end.

    After tax, the S&P 500 is taxed on its CPI-indexed shekel gain, and small-cap
    value on its dollar gain converted at the sale rate, capped at the nominal
    shekel gain (the two methods the site compares).
    """

    frame = _scv_frame(data or load_data(), year_end)
    frames = []
    for portfolio, group in frame.groupby("Portfolio", sort=True):
        group = group.sort_values("Year").copy()
        usd_growth = group["index"] / group["index"].shift(window)
        fx_growth = group["USD"] / group["USD"].shift(window)
        cpi_growth = group["CPI_IL"] / group["CPI_IL"].shift(window)
        nominal = usd_growth * fx_growth
        if not after_tax:
            group["CAGR"] = (nominal / cpi_growth) ** (1 / window) - 1
            frames.append(group.loc[group["Year"] >= 1969, ["Year", "Portfolio", "CAGR"]].dropna())
            continue
        if portfolio == "S&P 500":
            tax = TAX_RATE * np.maximum(nominal - cpi_growth, 0)
        else:
            dollar_gain_in_shekels = (usd_growth - 1) * fx_growth
            tax = TAX_RATE * np.maximum(np.minimum(dollar_gain_in_shekels, nominal - 1), 0)
        group["GainAfterTax"] = (nominal - tax) / cpi_growth - 1
        group["CAGR_after_tax"] = (group["GainAfterTax"] + 1) ** (1 / window) - 1
        frames.append(group.loc[group["Year"] >= 1969, ["Year", "Portfolio", "GainAfterTax", "CAGR_after_tax"]].dropna())
    return pd.concat(frames, ignore_index=True).sort_values(["Year", "Portfolio"]).reset_index(drop=True)


def sp500_scv_heatmap(data: InvestData | None = None, max_years: int = 20, year_end: int | None = None) -> pd.DataFrame:
    """Small-cap value minus S&P 500 for every start/end pair (real shekels)."""

    frame = _scv_frame(data or load_data(), year_end).copy()
    frame["v"] = frame["index"] * frame["USD"] / frame["CPI_IL"]
    levels = frame.pivot(index="Year", columns="Portfolio", values="v").sort_index()
    return _pair_heatmap(levels, "S&P 500", "US Small Cap Value", max_years)


# ---------------------------------------------------------------------------
# Provident fund (kupat gemel) vs savings policy vs self-managed (monthly)
# ---------------------------------------------------------------------------


def kupat_gemel(
    data: InvestData | None = None,
    with_pension: bool = False,
    age: int = DEFAULT_KUPAT_AGE,
    start_year: int = DEFAULT_KUPAT_START_YEAR,
    end: str | pd.Timestamp | None = None,
    initial: float = DEFAULT_KUPAT_INITIAL,
    pension_months: int = DEFAULT_KUPAT_PENSION_MONTHS,
    adjust_cpi: bool = True,
    kh_buy_sell: float = 0.0,
    kh_annual_fee: float = 0.65,
    ph_buy_sell: float = 0.0,
    ph_annual_fee: float = 0.75,
    ii_buy_sell: float = 0.07,
    ii_annual_fee: float = 0.07,
) -> pd.DataFrame:
    """Compare a one-time deposit in three wrappers, all tracking the S&P 500 in shekels.

    KH: investment provident fund. Before 60 the value is shown after a lump-sum
    withdrawal (25% real-gain tax). At 60 the balance is converted to a
    tax-exempt annuity (the fund's tax benefit), so from then on KH is the
    untaxed age-60 balance, CPI-linked, and no longer follows the market.
    PH: savings policy, always shown after lump-sum tax.
    II: self-managed, shown after selling and paying tax.

    With ``with_pension``, the fund pays a CPI-linked monthly annuity
    (``Kitzba``) of the age-60 balance / ``pension_months``. IIb withdraws the same net amount from the
    self-managed portfolio, paying tax on the gain share of each sale, and stops
    when it runs out (``IIbShortfall`` accumulates the unpaid amount).
    """

    data = data or load_data()
    frame = _monthly_window(data, f"{start_year}-01-01", end, ["value_ils", "cpi_il"])
    if frame["date"].iloc[0].year != start_year:
        raise CalculationInputError("אין נתונים לשנת ההתחלה שנבחרה.")
    months = np.arange(len(frame))
    frame["year3"] = frame["date"].dt.year + (frame["date"].dt.month - 1) / 12
    frame["age"] = age + months / 12
    growth = (frame["value_ils"] / frame["value_ils"].iloc[0]).to_numpy()
    cpi_ratio = (frame["cpi_il"] / frame["cpi_il"].iloc[0]).to_numpy()
    after_60 = frame["age"].to_numpy() >= 60

    def invested(buy_sell: float, annual_fee: float) -> np.ndarray:
        """Nominal value of one shekel deposited, after entry and exit costs, before tax."""
        cost = 1 - buy_sell / 100
        return cost * growth * _monthly_fee_factor(annual_fee) ** months * cost

    kh_gross = invested(kh_buy_sell, kh_annual_fee)
    frame["KH"] = _real_after_tax(kh_gross, cpi_ratio)
    frame["Kitzba"] = 0.0
    if after_60.any():
        # Conversion happens at the first row at or after age 60 (immediately
        # when the investor is already older).
        anchor = int(np.argmax(after_60))
        kh60, cpi60 = kh_gross[anchor], cpi_ratio[anchor]
        frame["KH"] = np.where(after_60, kh60 * cpi_ratio / cpi60, frame["KH"])
        frame["Kitzba"] = np.where(months > anchor, kh60 / pension_months * cpi_ratio / cpi60, 0.0)
    frame["PH"] = _real_after_tax(invested(ph_buy_sell, ph_annual_fee), cpi_ratio)
    frame["II"] = _real_after_tax(invested(ii_buy_sell, ii_annual_fee), cpi_ratio)

    if with_pension:
        frame["IIb"], frame["IIbShortfall"] = _self_managed_pension(
            growth, cpi_ratio, frame["Kitzba"].to_numpy(), ii_buy_sell, ii_annual_fee
        )

    columns = ["KH", "II", "IIb", "Kitzba", "IIbShortfall"] if with_pension else ["KH", "PH", "II"]
    scale = initial / (cpi_ratio if adjust_cpi else 1.0)
    for column in columns:
        frame[column] = frame[column] * scale
    return frame[["date", "age", "year3", *columns]].reset_index(drop=True)


def _self_managed_pension(
    growth: np.ndarray,
    cpi_ratio: np.ndarray,
    payments: np.ndarray,
    buy_sell: float,
    annual_fee: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Self-managed portfolio that pays ``payments`` net of tax and selling costs.

    Each sale pays 25% tax on its share of the real gain and reduces the cost
    basis proportionally. Returns the after-tax liquidation value at each month
    and the cumulative unpaid amount once the portfolio is exhausted.
    """

    cost = 1 - buy_sell / 100
    fee = _monthly_fee_factor(annual_fee)
    holding = cost
    basis = 1.0
    shortfall = 0.0
    values = np.empty(len(growth), dtype=float)
    shortfalls = np.zeros(len(growth), dtype=float)
    for pos in range(len(growth)):
        if pos:
            holding *= growth[pos] / growth[pos - 1] * fee
        if payments[pos] > 0:
            # Per unit of holding sold: proceeds after exit cost, minus tax on
            # the proceeds above the matching share of the indexed basis.
            basis_per_unit = basis * cpi_ratio[pos] / holding if holding > 0 else 0.0
            net_per_unit_sold = cost - TAX_RATE * max(cost - basis_per_unit, 0.0)
            needed = payments[pos] / net_per_unit_sold if net_per_unit_sold > 0 else np.inf
            sold = min(needed, holding)
            shortfall += max(payments[pos] - sold * net_per_unit_sold, 0.0)
            basis *= 1 - sold / holding if holding > 0 else 0.0
            holding -= sold
        values[pos] = _real_after_tax(np.array([holding * cost]), np.array([cpi_ratio[pos]]), basis)[0]
        shortfalls[pos] = shortfall
    return values, shortfalls


# ---------------------------------------------------------------------------
# Self-managed account costs (monthly)
# ---------------------------------------------------------------------------


def independent_commissions(
    data: InvestData | None = None,
    tax_mode: str = "optional_tax",
    start: str | pd.Timestamp = DEFAULT_INDEPENDENT_START,
    end: str | pd.Timestamp = DEFAULT_INDEPENDENT_END,
    initial: float = 100000,
    share_price: float = 50,
    dollar_commission: float = 0.005,
    commission_per_share: float = 0.01,
    min_dollar_commission: float = 7.5,
    yearly_commission: float = 0.003,
) -> pd.DataFrame:
    """Buy a US S&P 500 fund with shekels, hold, then convert back.

    Costs: currency conversion spread on the way in and out, a per-share broker
    commission with a minimum on buy and sell, and an annual custody/fund fee.
    The number of shares is fixed at purchase. ``optional_tax`` shows the value
    before tax; ``us_vs_il`` compares tax on the CPI-indexed shekel gain
    (``v_final_il``) with tax on the dollar gain converted at the sale rate,
    capped at the nominal shekel gain (``v_final_dollar``). Values are in real
    shekels of the start date.
    """

    if tax_mode not in {"optional_tax", "us_vs_il"}:
        raise ValueError("tax_mode must be 'optional_tax' or 'us_vs_il'")

    frame = _monthly_window(data or load_data(), start, end, ["value_ils", "cpi_il"])
    price = frame["price"].to_numpy()
    fx = frame["fx"].to_numpy()
    cpi_ratio = (frame["cpi_il"] / frame["cpi_il"].iloc[0]).to_numpy()
    months = np.arange(len(frame))

    usd_bought = initial * (1 - dollar_commission) / fx[0]
    buy_commission = max(min_dollar_commission, usd_bought / share_price * commission_per_share)
    usd_invested = max(usd_bought - buy_commission, 0.0)
    shares = usd_invested / share_price
    sell_commission = max(min_dollar_commission, shares * commission_per_share)

    fee = (1 - yearly_commission) ** (1 / 12)
    usd_value = usd_invested * price / price[0] * fee ** months
    usd_proceeds = np.maximum(usd_value - sell_commission, 0.0)
    shekel_proceeds = usd_proceeds * fx * (1 - dollar_commission)

    nominal_gain = shekel_proceeds - initial
    tax_il = TAX_RATE * np.maximum(shekel_proceeds - initial * cpi_ratio, 0.0)
    dollar_gain = usd_proceeds - initial / fx[0]
    tax_dollar = TAX_RATE * np.maximum(np.minimum(dollar_gain * fx, nominal_gain), 0.0)

    real = 1 / cpi_ratio
    result = pd.DataFrame({"date": frame["date"], "v0": initial * frame["value_ils"] / frame["value_ils"].iloc[0] * real})
    if tax_mode == "optional_tax":
        result["v_final"] = shekel_proceeds * real
        return result
    result["v_final_il"] = (shekel_proceeds - tax_il) * real
    result["v_final_dollar"] = (shekel_proceeds - tax_dollar) * real
    return result


# ---------------------------------------------------------------------------
# Safe withdrawal rate (annual, real US dollars)
# ---------------------------------------------------------------------------


def trinity(
    data: InvestData | None = None,
    portfolio: str = DEFAULT_TRINITY_PORTFOLIO,
    yearly_draw: float = DEFAULT_TRINITY_DRAW,
    years: int = DEFAULT_TRINITY_YEARS,
    base: float = DEFAULT_TRINITY_BASE,
    year_end: int | None = None,
) -> pd.DataFrame:
    """Fixed real withdrawal of ``yearly_draw * base`` at the start of each year, for every start year.

    Balances are in real (US CPI) money of the start year. A depleted portfolio
    stays at zero; ``depleted_year`` is the year in which it ran out.
    """

    data = data or load_data()
    source = data.LazyReturns1.loc[
        (data.LazyReturns1["Portfolio"] == portfolio) & (~data.LazyReturns1["CommissionUse"]),
        ["Year", "commission", "CPI_US", "YearReturn"],
    ].sort_values("Year")
    if year_end is not None:
        source = source[source["Year"] <= year_end]
    source = source.set_index(source["Year"].astype(int))
    real_growth = (
        (1 + source["YearReturn"] / 100)
        * (1 - source["commission"] / 100)
        * source["CPI_US"].shift(1)
        / source["CPI_US"]
    ).dropna()

    draw = base * yearly_draw
    rows = []
    first_year = int(real_growth.index.min())
    last_start = int(real_growth.index.max()) - years + 1
    for start_year in range(first_year, last_start + 1):
        balance = base
        low = np.inf
        depleted_year = None
        for year in range(start_year, start_year + years):
            balance = max(balance - draw, 0.0) * real_growth[year]
            low = min(low, balance)
            if balance <= 0 and depleted_year is None:
                depleted_year = year
        rows.append(
            {
                "start_year": start_year,
                "end_year": start_year + years - 1,
                "Investment_remained": balance,
                "Investment_low": low,
                "depleted_year": depleted_year,
            }
        )
    return pd.DataFrame(rows, columns=["start_year", "end_year", "Investment_remained", "Investment_low", "depleted_year"])
