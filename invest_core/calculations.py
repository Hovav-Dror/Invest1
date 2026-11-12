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
# Realization schedules compared by the tax screens, in months (the first is
# selling every month).
REALIZATION_MONTHS = (1, 12, 60, 120)
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
    "Gold Miners",
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
    for months in REALIZATION_MONTHS[1:]:
        frame[f"every_{months}"] = _tax_ledger(value, cpi, months, fee)
    return frame


def tax_events(
    data: InvestData | None = None,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """S&P 500 in shekels: tax once at the end vs selling every month, year, 5 or 10 years."""

    frame = _tax_scenarios(data or load_data(), start, end, 0.0)
    scale = initial / (frame["cpi_ratio"] if adjust_cpi else 1.0)
    result = pd.DataFrame(
        {
            "date": frame["date"],
            "v": frame["gross"] * scale,
            "Gain_i": frame["gross"].pct_change().fillna(0) + 1,
            "End25": frame["at_end"] * scale,
            "EveryMonth": frame["every_1"] * scale,
            "Every12Months": frame["every_12"] * scale,
            "Every60Months": frame["every_60"] * scale,
            "Every120Months": frame["every_120"] * scale,
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
            "tax_every_12_months": frame["every_12"] * scale,
            "tax_every_60_months": frame["every_60"] * scale,
            "tax_every_120_months": frame["every_120"] * scale,
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


RISK_LADDER_YEARS = (1, 3, 5, 10, 15, 20, 30)


def sp500_risk_ladder(
    data: InvestData | None = None,
    start: str | None = None,
    end: str | None = None,
    horizons: Iterable[int] = RISK_LADDER_YEARS,
) -> pd.DataFrame:
    """For each holding period: share of windows that ended in a real loss, median, worst and best.

    Same windows as ``sp500_risk`` (real, US-CPI adjusted, rolling monthly).
    Horizons longer than the selected range are skipped.
    """

    data = data or load_data()
    rows = []
    for years in horizons:
        try:
            frame = sp500_risk(data=data, years=years, start=start, end=end)
        except CalculationInputError:
            continue
        returns = frame["TotalReturnP"]
        worst = frame.loc[returns.idxmin()]
        best = frame.loc[returns.idxmax()]
        rows.append(
            {
                "Years": years,
                "Periods": len(frame),
                "LossShare": float((returns < 0).mean()),
                "Losses": int((returns < 0).sum()),
                "Median": float(returns.median()),
                "Worst": float(worst["TotalReturnP"]),
                "WorstTotal": float(worst["TotalReturn"] - 1),
                "WorstEnd": worst["date"],
                "Best": float(best["TotalReturnP"]),
                "BestTotal": float(best["TotalReturn"] - 1),
                "BestEnd": best["date"],
            }
        )
    if not rows:
        raise CalculationInputError("הטווח שנבחר קצר מדי לכל משכי ההשקעה.")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Lazy portfolios (annual)
# ---------------------------------------------------------------------------

VALUE_COLUMNS = {
    "cpi_il": "Index_CPI_IL",
    "cpi_us": "Index_CPI_US",
    "nominal": "index",
}


def _underwater(values: np.ndarray, years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per year: worst later loss for a buyer at that year end, and the current underwater spell.

    The spell is the number of years since the last peak, counted until the
    year the portfolio is back at or above that peak (that year included). Its
    maximum is the longest stretch below a previous peak; an unrecovered spell
    runs to the last observation.
    """

    drops = np.full(len(values), np.nan)
    shefel = np.full(len(values), np.nan)
    peak = np.nan
    peak_year = np.nan
    below = False
    for pos, value in enumerate(values):
        if np.isnan(value):
            continue
        future = values[pos:]
        drops[pos] = np.nanmin(future) / value - 1
        if np.isnan(peak):
            peak, peak_year = value, years[pos]
            shefel[pos] = 0.0
            continue
        if value >= peak:
            shefel[pos] = years[pos] - peak_year if below else 0.0
            peak, peak_year, below = value, years[pos], False
        else:
            below = True
            shefel[pos] = years[pos] - peak_year
    return drops, shefel


def _portfolio_window(
    data: InvestData,
    portfolios: Iterable[str],
    year_start: int,
    year_end: int,
    commission_adjusted: bool,
    value_mode: str,
    common_period: bool = False,
) -> pd.DataFrame:
    """Annual rows for each portfolio from its base year (year_start - 1, or first available).

    With ``common_period`` every portfolio starts at the latest of those base
    years, so all of them cover the same years.
    """

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
    if common_period and not frame.empty:
        frame = frame[frame["Year"] >= frame.groupby("Portfolio")["Year"].min().max()]

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
    common_period: bool = False,
) -> pd.DataFrame:
    """Normalized annual rows (base row excluded) with drawdown columns."""

    frame = _portfolio_window(data or load_data(), portfolios, year_start, year_end, commission_adjusted, value_mode, common_period)
    return frame[~frame["is_base"]].drop(columns=["is_base"]).reset_index(drop=True)


def portfolio_summary(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2025,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
    common_period: bool = False,
) -> pd.DataFrame:
    """Per-portfolio CAGR, volatility of annual returns, worst drop and longest underwater period."""

    frame = _portfolio_window(data or load_data(), portfolios, year_start, year_end, commission_adjusted, value_mode, common_period)
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
    common_period: bool = False,
) -> pd.DataFrame:
    """Accumulated value, annual return, CAGR since start and rolling CAGR per portfolio.

    With ``full_history_rolling`` the rolling windows may reach back before
    ``year_start``; values are still normalized to the selected start.
    """

    data = data or load_data()
    history_start = 1871 if full_history_rolling else year_start
    frame = _portfolio_window(data, portfolios, history_start, year_end, commission_adjusted, value_mode)
    common_base = frame.groupby("Portfolio")["Year"].min().max() if common_period else -np.inf
    frames = []
    for _, group in frame.groupby("Portfolio", sort=True):
        group = group.copy()
        base_year = max(group["Year"].iloc[0], year_start - 1, common_base)
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
    value_mode: str = "cpi_us",
) -> pd.DataFrame:
    """Fixed real withdrawal of ``yearly_draw * base`` at the start of each year, for every start year.

    ``cpi_us`` (as in the original study): US returns in real dollars (US CPI).
    ``cpi_il``: the same portfolio in real shekels, including the dollar/shekel
    rate and Israeli CPI. A depleted portfolio stays at zero; ``depleted_year``
    is the year in which it ran out.
    """

    if value_mode not in {"cpi_us", "cpi_il"}:
        raise ValueError("value_mode must be 'cpi_us' or 'cpi_il'")
    data = data or load_data()
    source = data.LazyReturns1.loc[
        (data.LazyReturns1["Portfolio"] == portfolio) & (~data.LazyReturns1["CommissionUse"]),
        ["Year", "commission", "CPI_US", "YearReturn", "Index_CPI_IL"],
    ].sort_values("Year")
    if year_end is not None:
        source = source[source["Year"] <= year_end]
    source = source.set_index(source["Year"].astype(int))
    if value_mode == "cpi_il":
        index = source["Index_CPI_IL"].where(source["Index_CPI_IL"] > 0)
        real_growth = (index / index.shift(1) * (1 - source["commission"] / 100)).dropna()
    else:
        real_growth = (
            (1 + source["YearReturn"] / 100)
            * (1 - source["commission"] / 100)
            * source["CPI_US"].shift(1)
            / source["CPI_US"]
        ).dropna()
    if real_growth.empty:
        raise CalculationInputError("אין מספיק נתונים לתיק הזה.")

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


# --- Young couples: how much apartment the down payment buys ------------------

DEFAULT_AFFORD_EQUITY = 400_000.0
DEFAULT_AFFORD_INCOME = 20_000.0
DEFAULT_AFFORD_RATE = 0.05
DEFAULT_AFFORD_YEARS = 30
DEFAULT_AFFORD_PTI = 0.35
DEFAULT_AFFORD_COSTS = 0.02
DEFAULT_AFFORD_DROP = 0.30
DEFAULT_AFFORD_BUYER = "first"
DEFAULT_AFFORD_RENOVATION = 0.0
AFFORD_CHART_MAX = 1_000_000.0

# Bank of Israel financing limit by buyer: a sole apartment, replacing one
# (upgrading), or an additional apartment (investors).
AFFORD_LTV = {"first": 0.75, "upgrade": 0.70, "investor": 0.50}
DEFAULT_AFFORD_LTV = AFFORD_LTV["first"]

# Purchase tax brackets (lower bound, rate), frozen until January 2028. A buyer
# who upgrades and sells the old apartment within 18 months pays the sole-
# apartment rates too.
PURCHASE_TAX_SOLE = ((0.0, 0.0), (1_978_745.0, 0.035), (2_347_040.0, 0.05), (6_055_070.0, 0.08), (20_183_565.0, 0.10))
PURCHASE_TAX_ADDITIONAL = ((0.0, 0.08), (6_055_070.0, 0.10))


def purchase_tax(price: float, buyer: str = DEFAULT_AFFORD_BUYER) -> float:
    """Israeli purchase tax on a dwelling, by marginal brackets."""

    brackets = PURCHASE_TAX_ADDITIONAL if buyer == "investor" else PURCHASE_TAX_SOLE
    tax = 0.0
    for index, (lower, rate) in enumerate(brackets):
        upper = brackets[index + 1][0] if index + 1 < len(brackets) else float("inf")
        if price > lower:
            tax += (min(price, upper) - lower) * rate
    return tax


def _annuity_factor(rate: float, years: int) -> float:
    """Loan amount per 1 of monthly payment (Shpitzer schedule, monthly compounding)."""

    months = years * 12
    monthly = rate / 12
    if monthly == 0:
        return float(months)
    return (1 - (1 + monthly) ** -months) / monthly


def _largest_price(cost, budget: float) -> float:
    """Largest price whose ``cost(price)`` fits ``budget``; ``cost`` is increasing."""

    if budget <= 0:
        return 0.0
    low, high = 0.0, 1.0
    while cost(high) <= budget:
        high *= 2
    for _ in range(80):
        middle = (low + high) / 2
        if cost(middle) <= budget:
            low = middle
        else:
            high = middle
    return low


def affordability(
    equity: float = DEFAULT_AFFORD_EQUITY,
    income: float = DEFAULT_AFFORD_INCOME,
    rate: float = DEFAULT_AFFORD_RATE,
    years: int = DEFAULT_AFFORD_YEARS,
    ltv: float | None = None,
    pti: float = DEFAULT_AFFORD_PTI,
    costs: float = DEFAULT_AFFORD_COSTS,
    drop: float = DEFAULT_AFFORD_DROP,
    buyer: str = DEFAULT_AFFORD_BUYER,
    renovation: float = DEFAULT_AFFORD_RENOVATION,
) -> pd.DataFrame:
    """Highest apartment price a given down payment can buy, for a range of down payments.

    First ``renovation`` (renovation, furniture, moving) comes out of the
    equity; what is left pays for everything the bank does not lend: the part
    of the price above the mortgage, ``costs`` of the price (lawyer, broker,
    appraiser) and purchase tax (by ``buyer``). Two limits apply to the
    mortgage: at most ``ltv`` of the price (by default the Bank of Israel
    limit for ``buyer``), and a monthly payment of at most ``pti`` of net
    household ``income``. The price is the highest one that meets both:

    * by LTV: ``price * (1 - ltv + costs) + tax(price) <= cash``
    * by income: ``price * (1 + costs) + tax(price) <= cash + max_loan``

    Under the LTV limit each shekel of equity buys about 1 / (1 - ltv + costs)
    shekels of apartment; under the income limit, only about one. Rows cover
    down payments from zero to ``AFFORD_CHART_MAX`` (more when ``equity`` or
    the switch point is beyond it); ``point`` marks the current down payment
    (``now``), the down payment after a ``drop`` in the portfolio
    (``after_drop``) and the down payment at which the binding limit switches
    (``kink``). ``marginal`` is how much more apartment the next 1,000 shekels
    of equity would buy, per shekel.
    """

    if equity <= 0:
        raise CalculationInputError("ההון העצמי צריך להיות גדול מאפס.")
    if buyer not in AFFORD_LTV:
        raise CalculationInputError("סוג הרוכש לא מוכר.")
    ltv = AFFORD_LTV[buyer] if ltv is None else ltv
    if not 0 < ltv < 1:
        raise CalculationInputError("שיעור המימון צריך להיות בין 0 ל-100%.")
    if renovation < 0:
        raise CalculationInputError("עלות השיפוץ לא יכולה להיות שלילית.")
    factor = _annuity_factor(rate, years)
    max_loan = pti * income * factor

    def tax(price: float) -> float:
        return purchase_tax(price, buyer)

    def by_ltv_cost(price: float) -> float:
        return price * (1 - ltv + costs) + tax(price)

    def by_income_cost(price: float) -> float:
        return price * (1 + costs) + tax(price)

    def price_for(value: float) -> tuple[float, float]:
        cash = max(value - renovation, 0.0)
        return _largest_price(by_ltv_cost, cash), _largest_price(by_income_cost, cash + max_loan)

    def row(value: float, point: str = "") -> dict:
        cash = max(value - renovation, 0.0)
        price_ltv, price_income = price_for(value)
        price = min(price_ltv, price_income)
        loan = max(by_income_cost(price) - cash, 0.0)
        next_ltv, next_income = price_for(value + 1000)
        return {
            "equity": value,
            "max_price": price,
            "mortgage": loan,
            "payment": loan / factor,
            "price_ltv": price_ltv,
            "price_income": price_income,
            "binding": "ltv" if price_ltv <= price_income else "income",
            "renovation": min(renovation, value),
            "fees": price * costs,
            "purchase_tax": tax(price),
            "marginal": (min(next_ltv, next_income) - price) / 1000,
            "point": point,
        }

    # The switch: the loan is both the LTV share of the price and the income maximum.
    kink_price = max_loan / ltv
    kink = by_ltv_cost(kink_price) + renovation if max_loan > 0 else 0.0
    # A fixed range for typical down payments, so the chart axis stays put
    # while the down payment changes; wider only when needed.
    top = max(AFFORD_CHART_MAX, equity * 1.15, kink * 1.3)
    marks = {equity: "now", equity * (1 - drop): "after_drop"}
    if 0 < kink < top:
        marks.setdefault(kink, "kink")
    grid = [float(value) for value in np.linspace(0, top, 121) if not any(np.isclose(value, mark) for mark in marks)]
    rows = [row(value) for value in grid] + [row(value, point) for value, point in marks.items()]
    return pd.DataFrame(rows).sort_values("equity", kind="stable").reset_index(drop=True)


# --- Young couples: how much apartment the down payment buys after N years ----

DEFAULT_DOWN_YEARS = 4
DEFAULT_DOWN_STOCKS = 0.3
DEFAULT_DOWN_WAIT = 0
DOWN_STOCK_FEE = 0.001  # annual, a cheap S&P 500 fund
DOWN_CASH_SPREAD = 0.003  # annual, money-market fund return below the Bank of Israel rate
DOWN_WAIT_TRIGGER = 0.10  # postpone only after the portfolio fell this much from its peak
# Israeli shares: the TASE general index and TA-125 are price indices, so a
# constant dividend yield is added. TASE reported an average yield of 2.8% in
# 2022 and 2.9% in 2023 for listed companies; 2.5% is a little below that.
DOWN_IL_DIVIDEND = 0.025
DOWN_MARKETS = ("sp500", "israel")
# Cash: a shekel money-market fund (the cash rate less the spread), or money
# linked to the CPI with no real interest (a benchmark: it keeps its buying power
# in goods, not in apartments).
DOWN_CASH_KINDS = ("fund", "linked")


def _down_payment_market(data: InvestData, housing: pd.DataFrame) -> pd.DataFrame:
    """Monthly boundaries with S&P 500 in shekels, Israeli CPI, dwelling prices, the cash rate and Israeli shares.

    At boundary ``d`` the dwelling index and the Israeli share index are the
    ones for month ``d - 1`` (the boundary closes that month), and cash earns
    month ``d``'s rate until the next boundary. ``tase`` is empty when the
    housing frame has no ``tase_index``.
    """

    market = monthly_market(data)[["date", "value_ils", "cpi_il"]]
    index = housing.set_index("month")

    def previous(month):
        return month + pd.DateOffset(months=1)

    market = market.assign(
        housing=market["date"].map(index["housing_index"].rename(previous)),
        cash_rate=market["date"].map(index["boi_rate"]),
        tase=market["date"].map(index["tase_index"].rename(previous)) if "tase_index" in index else np.nan,
    )
    valid = market[["value_ils", "cpi_il", "housing", "cash_rate"]].notna().all(axis=1)
    if not valid.any():
        raise CalculationInputError("אין נתונים משותפים למניות, לדיור ולריבית.")
    first, last = valid.idxmax(), valid[::-1].idxmax()
    market = market.loc[first:last].reset_index(drop=True)
    if market[["value_ils", "cpi_il", "housing", "cash_rate"]].isna().any().any():
        raise CalculationInputError("יש חודשים חסרים בנתוני הדיור או הריבית.")
    return market


def down_payment(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    years: int = DEFAULT_DOWN_YEARS,
    stock_share: float = DEFAULT_DOWN_STOCKS,
    glide: bool = False,
    wait_years: int = DEFAULT_DOWN_WAIT,
    stock_fee: float = DOWN_STOCK_FEE,
    cash_spread: float = DOWN_CASH_SPREAD,
    market_index: str = "sp500",
    cash_kind: str = "fund",
) -> pd.DataFrame:
    """How much apartment a down payment buys after ``years``, for every start month.

    The money is split between stocks and cash, rebalanced monthly. Cash is a
    money-market fund earning the cash rate less ``cash_spread``
    (``cash_kind="fund"``), or CPI-linked with no real interest (``"linked"``). Stocks are the S&P 500 in shekels with
    dividends (``market_index="sp500"``) or Israeli shares (``"israel"``: the
    TASE general index, then TA-125, plus ``DOWN_IL_DIVIDEND`` a year). With ``glide`` the
    stock share falls linearly from ``stock_share`` to zero at the purchase
    date. ``apartment`` is the value after tax divided by the growth of the
    dwelling price index: 1.0 buys the same apartment as at the start.

    Tax: 25% of the real gain, once at the purchase (no tax on rebalancing, as
    in a provident fund for investment), never a refund on a loss.

    Waiting: if at the planned date the portfolio (in shekels, before tax) is
    ``DOWN_WAIT_TRIGGER`` or more below its highest value since the start, the
    couple keeps it invested and buys in the first month it is back at that
    peak, or after ``wait_years`` at the latest. All cash never waits. Rent
    while waiting is not counted. When the data ends during a wait, the
    purchase is in the last month with data, so every setting covers the same
    start months.

    For comparison each row also has ``cash`` (all cash) and ``stocks`` (all
    stocks), both bought on the planned date without waiting.
    """

    if not 0 <= stock_share <= 1:
        raise CalculationInputError("חלק המניות צריך להיות בין 0 ל-100%.")
    if years < 1 or wait_years < 0:
        raise CalculationInputError("משך החיסכון צריך להיות לפחות שנה.")
    if market_index not in DOWN_MARKETS:
        raise CalculationInputError("מדד המניות לא מוכר.")
    if cash_kind not in DOWN_CASH_KINDS:
        raise CalculationInputError("סוג המזומן לא מוכר.")
    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    market = _down_payment_market(data, housing)
    horizon = years * 12
    starts = len(market) - horizon
    if starts <= 0:
        raise CalculationInputError("אין מספיק שנים של נתונים לתקופה הזו.")

    if market_index == "israel":
        if market["tase"].isna().any():
            raise CalculationInputError("אין נתוני מניות ישראליות לכל התקופה.")
        value = market["tase"].to_numpy()
        dividend = (1 + DOWN_IL_DIVIDEND) ** (1 / 12)
    else:
        value = market["value_ils"].to_numpy()
        dividend = 1.0
    stock_growth = value[1:] / value[:-1] * dividend * (1 - stock_fee) ** (1 / 12)
    if cash_kind == "linked":
        cpi_values = market["cpi_il"].to_numpy()
        cash_growth = cpi_values[1:] / cpi_values[:-1]
    else:
        cash_growth = 1 + (market["cash_rate"].to_numpy()[:-1] / 100 - cash_spread) / 12
    cpi = market["cpi_il"].to_numpy()
    homes = market["housing"].to_numpy()
    dates = market["date"]

    wait_months = wait_years * 12

    def shares(share: float, glide_path: bool, months: int) -> np.ndarray:
        steps = np.arange(months)
        if not glide_path:
            return np.full(months, share)
        return np.where(steps < horizon, share * (1 - steps / horizon), 0.0)

    def paths(start: int, share: float, glide_path: bool) -> tuple[np.ndarray, np.ndarray]:
        """Balance before tax and apartment fraction after tax, from the start to the last month available."""
        months = min(horizon + wait_months, len(market) - 1 - start)
        weights = shares(share, glide_path, months)
        span = slice(start, start + months)
        growth = weights * stock_growth[span] + (1 - weights) * cash_growth[span]
        balance = np.concatenate([[1.0], np.cumprod(growth)])
        inflation = cpi[start : start + months + 1] / cpi[start]
        after_tax = balance - TAX_RATE * np.maximum(balance - inflation, 0.0)
        return balance, after_tax / (homes[start : start + months + 1] / homes[start])

    rows = []
    for start in range(starts):
        balance, path = paths(start, stock_share, glide)
        cash_path = paths(start, 0.0, False)[1]
        buy = horizon
        # With a glide path the money is all in cash by the planned date, so waiting cannot recover a fall.
        if wait_months and stock_share > 0 and not glide:
            peak = balance[: horizon + 1].max()
            if balance[horizon] < peak * (1 - DOWN_WAIT_TRIGGER):
                back = np.nonzero(balance[horizon + 1 :] >= peak - 1e-12)[0]
                buy = horizon + 1 + int(back[0]) if len(back) else len(balance) - 1
        rows.append(
            {
                "start": dates[start],
                "buy": dates[start + buy],
                "waited_months": buy - horizon,
                "apartment": path[buy],
                "apartment_on_time": path[horizon],
                "cash": cash_path[horizon],
                "stocks": paths(start, 1.0, False)[1][horizon],
                "homes_change": homes[start + buy] / homes[start] - 1,
            }
        )
    return pd.DataFrame(rows)


DOWN_LADDER_SHARES = (0.0, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0)


def down_payment_ladder(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    years: int = DEFAULT_DOWN_YEARS,
    glide: bool = False,
    wait_years: int = DEFAULT_DOWN_WAIT,
    market_index: str = "sp500",
    cash_kind: str = "fund",
) -> pd.DataFrame:
    """``down_payment`` summarized over all start months, for several stock shares."""

    rows = []
    for share in DOWN_LADDER_SHARES:
        result = down_payment(
            data, housing, years=years, stock_share=share, glide=glide, wait_years=wait_years, market_index=market_index,
            cash_kind=cash_kind,
        )
        apartment = result["apartment"]
        rows.append(
            {
                "stock_share": share,
                "windows": len(result),
                "median": apartment.median(),
                "p10": apartment.quantile(0.1),
                "worst": apartment.min(),
                "below_90": (apartment < 0.9).mean(),
                "beat_cash": (apartment > result["cash"] + 1e-12).mean(),
                "waited": (result["waited_months"] > 0).mean(),
            }
        )
    return pd.DataFrame(rows)


STOCK_DROP_THRESHOLD = 0.2
HOMES_AFTER_MONTHS = 24


def homes_vs_stocks(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    real: bool = True,
) -> pd.DataFrame:
    """Dwelling prices next to stocks, monthly, from the first month with both.

    Columns: ``date`` (monthly boundary, as in ``down_payment``), ``homes``
    (CBS dwelling index), ``sp500`` (S&P 500 total return in shekels),
    ``tase`` (Israeli shares: TASE general index, then TA-125 from 2016-09; a
    price index without dividends), each 1.0
    at the first row and divided by Israeli CPI when ``real``; the 12-month
    change of each (``homes_12m``, ``sp500_12m``, ``tase_12m``); and
    ``rate``, the Bank of Israel rate in percent.

    The TASE index for month ``d - 1`` sits at boundary ``d``, like the
    dwelling index.
    """

    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    market = _down_payment_market(data, housing)
    frame = pd.DataFrame(
        {
            "date": market["date"],
            "homes": market["housing"],
            "sp500": market["value_ils"],
            "tase": market["tase"],
        }
    )
    deflator = market["cpi_il"] if real else pd.Series(1.0, index=market.index)
    for column in ("homes", "sp500", "tase"):
        values = frame[column] / deflator
        first = values.first_valid_index()
        frame[column] = values / values[first] if first is not None else np.nan
        frame[f"{column}_12m"] = frame[column] / frame[column].shift(12) - 1
    frame["rate"] = market["cash_rate"]
    return frame


def homes_vs_stocks_episodes(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    real: bool = True,
    threshold: float = STOCK_DROP_THRESHOLD,
) -> pd.DataFrame:
    """Every stock fall of at least ``threshold`` from a peak, and dwelling prices meanwhile.

    For each stock series (S&P 500 in shekels, TASE general index) an episode
    runs from a peak to the lowest point before the series regains that peak
    (or the end of the data). ``homes_change`` is the dwelling index change
    over the same months, ``homes_after`` over the ``HOMES_AFTER_MONTHS``
    after the low (empty when the data ends sooner), ``rate_peak`` and
    ``rate_low`` the Bank of Israel rate at both ends.
    """

    frame = homes_vs_stocks(data, housing, real=real)
    rows = []
    for column, market in (("sp500", "sp500"), ("tase", "tase")):
        series = frame[column]
        valid = series.notna()
        if not valid.any():
            continue
        index = series[valid].index
        peak = index[0]
        low = peak
        for position in index[1:]:
            value = series[position]
            if value >= series[peak]:
                if series[low] / series[peak] - 1 <= -threshold:
                    rows.append(_episode_row(frame, column, market, peak, low))
                peak = low = position
            elif value < series[low]:
                low = position
        if series[low] / series[peak] - 1 <= -threshold:
            rows.append(_episode_row(frame, column, market, peak, low))
    columns = ["market", "peak", "low", "stocks_change", "homes_change", "homes_after", "rate_peak", "rate_low"]
    return pd.DataFrame(rows, columns=columns).sort_values("peak").reset_index(drop=True)


def _episode_row(frame: pd.DataFrame, column: str, market: str, peak: int, low: int) -> dict:
    after = low + HOMES_AFTER_MONTHS
    homes = frame["homes"]
    return {
        "market": market,
        "peak": frame["date"][peak],
        "low": frame["date"][low],
        "stocks_change": frame[column][low] / frame[column][peak] - 1,
        "homes_change": homes[low] / homes[peak] - 1,
        "homes_after": homes[after] / homes[low] - 1 if after < len(frame) else np.nan,
        "rate_peak": frame["rate"][peak],
        "rate_low": frame["rate"][low],
    }


DEFAULT_CASH_AMOUNT = 300_000.0
DEFAULT_CASH_YEARS = 4
DEFAULT_CASH_RATE = 0.0325  # Bank of Israel rate, November 2026
DEFAULT_CASH_INFLATION = 0.02  # middle of the Bank of Israel target range
DEFAULT_FUND_FEE = 0.002
DEFAULT_DEPOSIT_SPREAD = 0.0075
DEFAULT_MAKAM_COST = 0.001
DEFAULT_GEMEL_FEE = 0.006
NOMINAL_INTEREST_TAX = 0.15

# (id, cost parameter, tax rule, rolled over and taxed every year)
CASH_VEHICLES = (
    ("fund", "fund_fee", "real", False),
    ("deposit", "deposit_spread", "nominal", True),
    ("makam", "makam_cost", "nominal", True),
    ("gemel", "gemel_fee", "real", False),
)


def _cash_value(years: int, rate: float, inflation: float, cost: float, tax: str, yearly: bool) -> float:
    """After-tax nominal value of 1 after ``years``.

    ``real`` tax: 25% of the gain above inflation, once at the end, never a
    refund. ``nominal`` tax: 15% of the interest; with ``yearly`` it is paid
    every year when the deposit or makam matures and is rolled over.
    """

    net = rate - cost
    if tax == "nominal":
        if yearly:
            return (1 + net * (1 - NOMINAL_INTEREST_TAX)) ** years
        gross = (1 + net) ** years
        return gross - NOMINAL_INTEREST_TAX * max(gross - 1, 0.0)
    gross = (1 + net) ** years
    return gross - TAX_RATE * max(gross - (1 + inflation) ** years, 0.0)


def cash_vehicles(
    amount: float = DEFAULT_CASH_AMOUNT,
    years: int = DEFAULT_CASH_YEARS,
    rate: float = DEFAULT_CASH_RATE,
    inflation: float = DEFAULT_CASH_INFLATION,
    fund_fee: float = DEFAULT_FUND_FEE,
    deposit_spread: float = DEFAULT_DEPOSIT_SPREAD,
    makam_cost: float = DEFAULT_MAKAM_COST,
    gemel_fee: float = DEFAULT_GEMEL_FEE,
) -> pd.DataFrame:
    """What ``amount`` held as cash grows to, after fees and tax, by vehicle and year.

    A fixed rate and inflation; no historical data. Vehicles: a money-market
    fund (``rate - fund_fee``, 25% of the real gain at the end), a bank
    deposit (``rate - deposit_spread``, 15% of the interest every year), a
    makam bought directly (``rate - makam_cost``, 15% every year) and a
    provident fund for investment in its shekel money-market track
    (``rate - gemel_fee``, 25% of the real gain at the end).

    Columns: vehicle, year, value (shekels after tax if withdrawn that year),
    real_value (in today's shekels), gap (value minus the best vehicle that
    year).
    """

    if amount <= 0:
        raise CalculationInputError("הסכום צריך להיות חיובי.")
    if not 1 <= years <= 15:
        raise CalculationInputError("מספר השנים צריך להיות בין 1 ל-15.")
    costs = {"fund_fee": fund_fee, "deposit_spread": deposit_spread, "makam_cost": makam_cost, "gemel_fee": gemel_fee}
    rows = []
    for year in range(years + 1):
        for vehicle, cost, tax, yearly in CASH_VEHICLES:
            value = amount * _cash_value(year, rate, inflation, costs[cost], tax, yearly)
            rows.append({"vehicle": vehicle, "year": year, "value": value, "real_value": value / (1 + inflation) ** year})
    frame = pd.DataFrame(rows)
    frame["gap"] = frame["value"] - frame.groupby("year")["value"].transform("max")
    return frame


CASH_INFLATION_GRID = tuple(round(step * 0.005, 3) for step in range(0, 11))


def cash_vehicles_inflation(
    amount: float = DEFAULT_CASH_AMOUNT,
    years: int = DEFAULT_CASH_YEARS,
    rate: float = DEFAULT_CASH_RATE,
    fund_fee: float = DEFAULT_FUND_FEE,
    deposit_spread: float = DEFAULT_DEPOSIT_SPREAD,
    makam_cost: float = DEFAULT_MAKAM_COST,
    gemel_fee: float = DEFAULT_GEMEL_FEE,
) -> pd.DataFrame:
    """``cash_vehicles`` at the last year, for inflation from 0% to 5%.

    Real tax is lighter when inflation is high, so the ranking can change.
    Columns: inflation, then the after-tax value of each vehicle, and best.
    """

    rows = []
    for inflation in CASH_INFLATION_GRID:
        frame = cash_vehicles(amount, years, rate, inflation, fund_fee, deposit_spread, makam_cost, gemel_fee)
        last = frame[frame["year"] == years].set_index("vehicle")["value"]
        rows.append({"inflation": inflation, **last.to_dict(), "best": last.idxmax()})
    return pd.DataFrame(rows)


DEFAULT_PENSION_AGE = 28
DEFAULT_PENSION_RETIRE = 67
DEFAULT_PENSION_SALARY = 15_000.0
DEFAULT_PENSION_CONTRIBUTION = 0.185  # 6% employee + 6.5% employer + 6% severance
DEFAULT_PENSION_SALARY_GROWTH = 0.01  # real, per year
DEFAULT_PENSION_RETURN = 0.035  # real, per year, before fees
DEFAULT_PENSION_FEE_DEPOSIT = 0.0157  # market average, 2024
DEFAULT_PENSION_FEE_BALANCE = 0.0015
DEFAULT_PENSION_COEFFICIENT = 200.0

# Investment tracks. A track's real return is its stock share times a long-run
# real return on stocks, plus the rest times a real return on bonds and other
# assets (including earmarked government bonds in comprehensive funds).
# Assumptions, not forecasts: about 5% a year above inflation for world stocks
# over the long run, 2% for the rest.
PENSION_STOCK_RETURN = 0.05
PENSION_OTHER_RETURN = 0.02
# Age-based tracks (the default for most members): stock share by age band.
# 53% and 22% are typical shares for the youngest and oldest tracks; 38% is
# between them for the 50-60 track.
PENSION_AGE_BANDS = ((50, 0.53), (60, 0.38), (200, 0.22))
PENSION_TRACKS = ("age", "sp500", "bonds", "fixed")
DEFAULT_PENSION_TRACK = "age"


def pension_track_return(track: str, age: float, fixed_return: float = DEFAULT_PENSION_RETURN) -> float:
    """Real yearly return before fees of a track at an age."""

    def mix(stocks: float) -> float:
        return stocks * PENSION_STOCK_RETURN + (1 - stocks) * PENSION_OTHER_RETURN

    if track == "age":
        for upper, stocks in PENSION_AGE_BANDS:
            if age < upper:
                return mix(stocks)
    if track == "sp500":
        return mix(1.0)
    if track == "bonds":
        return mix(0.0)
    if track == "fixed":
        return fixed_return
    raise CalculationInputError("מסלול ההשקעה לא מוכר.")

# Fixed comparisons: (id, fee on deposits, fee on balance).
PENSION_SCENARIOS = (
    ("default_fund", 0.01, 0.0022),  # default funds, 2024 tender (2024-2028)
    ("cap", 0.06, 0.005),  # legal maximum
    ("none", 0.0, 0.0),
)


def _pension_path(
    months: int,
    salary: float,
    contribution: float,
    salary_growth: float,
    yearly_returns: list[float],
    fee_deposit: float,
    fee_balance: float,
) -> np.ndarray:
    """Real balance at the end of each year, monthly deposits and fees; ``yearly_returns[y]`` applies in year ``y``."""

    monthly_fee = (1 - fee_balance) ** (1 / 12)
    balance = 0.0
    yearly = [0.0]
    for month in range(months):
        wage = salary * (1 + salary_growth) ** (month // 12)
        monthly_return = (1 + yearly_returns[month // 12]) ** (1 / 12)
        balance = balance * monthly_return * monthly_fee + wage * contribution * (1 - fee_deposit)
        if (month + 1) % 12 == 0:
            yearly.append(balance)
    return np.array(yearly)


def pension_fees(
    age: int = DEFAULT_PENSION_AGE,
    retire_age: int = DEFAULT_PENSION_RETIRE,
    salary: float = DEFAULT_PENSION_SALARY,
    contribution: float = DEFAULT_PENSION_CONTRIBUTION,
    salary_growth: float = DEFAULT_PENSION_SALARY_GROWTH,
    real_return: float = DEFAULT_PENSION_RETURN,
    fee_deposit: float = DEFAULT_PENSION_FEE_DEPOSIT,
    fee_balance: float = DEFAULT_PENSION_FEE_BALANCE,
    coefficient: float = DEFAULT_PENSION_COEFFICIENT,
    track: str = DEFAULT_PENSION_TRACK,
) -> pd.DataFrame:
    """Pension balance by age under your fees and three fixed comparisons.

    Everything is in today's shekels: ``salary`` is the gross monthly salary
    now, growing ``salary_growth`` a year above inflation. The fund's return
    above inflation, before fees, follows ``track`` (see
    ``pension_track_return``); ``real_return`` is used only with ``"fixed"``. Each month ``contribution``
    of the salary is deposited, less ``fee_deposit``; the balance fee is
    charged monthly so that a year removes exactly ``fee_balance``.

    Columns: scenario (yours, default_fund, cap, none), age, balance,
    pension (balance / ``coefficient``, the monthly annuity at retirement).
    """

    if not 18 <= age < retire_age <= 75:
        raise CalculationInputError("גיל ההתחלה צריך להיות לפני גיל הפרישה.")
    if salary <= 0 or coefficient <= 0:
        raise CalculationInputError("השכר והמקדם צריכים להיות חיוביים.")
    if track not in PENSION_TRACKS:
        raise CalculationInputError("מסלול ההשקעה לא מוכר.")
    months = (retire_age - age) * 12
    returns = [pension_track_return(track, age + year, real_return) for year in range(retire_age - age)]
    rows = []
    for scenario, deposit_fee, balance_fee in (("yours", fee_deposit, fee_balance),) + PENSION_SCENARIOS:
        path = _pension_path(months, salary, contribution, salary_growth, returns, deposit_fee, balance_fee)
        for offset, balance in enumerate(path):
            rows.append({"scenario": scenario, "age": age + offset, "balance": balance, "pension": balance / coefficient})
    return pd.DataFrame(rows)


PENSION_STEPS = (
    ("balance_01", 0.0, 0.001),
    ("deposit_1", 0.01, 0.0),
)


def pension_fees_steps(**kwargs) -> pd.DataFrame:
    """What 0.1% more of the balance, or 1% more of deposits, costs by retirement.

    Takes the same arguments as ``pension_fees``. Columns: step, balance_loss,
    pension_loss, share (of the balance under your fees).
    """

    base = pension_fees(**kwargs)
    final = base[base["scenario"] == "yours"].iloc[-1]
    rows = []
    for step, extra_deposit, extra_balance in PENSION_STEPS:
        changed = dict(kwargs)
        changed["fee_deposit"] = kwargs.get("fee_deposit", DEFAULT_PENSION_FEE_DEPOSIT) + extra_deposit
        changed["fee_balance"] = kwargs.get("fee_balance", DEFAULT_PENSION_FEE_BALANCE) + extra_balance
        other = pension_fees(**changed)
        last = other[other["scenario"] == "yours"].iloc[-1]
        loss = final["balance"] - last["balance"]
        rows.append(
            {
                "step": step,
                "balance_loss": loss,
                "pension_loss": final["pension"] - last["pension"],
                "share": loss / final["balance"],
            }
        )
    return pd.DataFrame(rows)


# --- Young couples: buy now, or rent and invest -------------------------------

DEFAULT_RENT_PRICE = 2_200_000.0
DEFAULT_RENT_RENT = 5_000.0  # 2.7% a year of the price; the national average is about 2.5%-3%
DEFAULT_RENT_YEARS = 10
DEFAULT_RENT_RATE = DEFAULT_AFFORD_RATE
DEFAULT_RENT_TERM = DEFAULT_AFFORD_YEARS
DEFAULT_RENT_INFLATION = 0.02
DEFAULT_RENT_GROWTH = 0.025  # nominal, per year; CBS rent index rose ~2.4% a year in 2015-2025
DEFAULT_RENT_INVEST = 0.06  # nominal, per year, after fees, before tax
DEFAULT_RENT_UPKEEP = 0.005  # of the home value, per year
DEFAULT_RENT_BUY_COSTS = DEFAULT_AFFORD_COSTS
DEFAULT_RENT_SELL_COSTS = 0.02
DEFAULT_RENT_LTV = DEFAULT_AFFORD_LTV
DEFAULT_RENT_BUYER = DEFAULT_AFFORD_BUYER
DEFAULT_RENT_STOCKS = 1.0  # the renter's money in stocks, in the historical test
DEFAULT_RENT_LIFE_INSURANCE = 0.0024  # mortgage life insurance, of the balance a year (~200 ILS a month per million, a couple in their 20s)
DEFAULT_RENT_HOME_INSURANCE = 0.0004  # building insurance the bank requires, of the home value a year
RENT_GROWTH_GRID = tuple(round(-0.03 + step * 0.005, 3) for step in range(19))  # real, -3% to +6%
RENT_HORIZONS = (2, 3, 4, 5, 7, 10, 15, 20, 25)


class _Portfolio:
    """Money invested monthly; 25% tax on the gain above inflation when sold."""

    def __init__(self, monthly_return: float, monthly_inflation: float) -> None:
        self.value = 0.0
        self.basis = 0.0  # what was put in, in shekels of the current month
        self.growth = monthly_return
        self.inflation = monthly_inflation

    def step(self, deposit: float) -> None:
        self.value = self.value * self.growth + deposit
        self.basis = self.basis * self.inflation + deposit

    def after_tax(self) -> float:
        return self.value - TAX_RATE * max(self.value - self.basis, 0.0)


def _buy_rent_wealth(
    home_growth: float,
    price: float,
    rent: float,
    years: int,
    rate: float,
    term: int,
    inflation: float,
    rent_growth: float,
    invest_return: float,
    upkeep: float,
    buy_costs: float,
    sell_costs: float,
    ltv: float,
    buyer: str,
    home_path: np.ndarray | None = None,
    invest_path: np.ndarray | None = None,
    extra_equity: float = 0.0,
    life_insurance: float = DEFAULT_RENT_LIFE_INSURANCE,
    home_insurance: float = DEFAULT_RENT_HOME_INSURANCE,
) -> dict:
    """Nominal wealth after ``years`` of buying vs renting, if homes grow ``home_growth`` a year (nominal).

    Both start with the same cash: the buyer's down payment, fees and purchase
    tax. The renter invests it. Each month whoever pays less (mortgage and
    upkeep vs rent) invests the difference, at ``invest_return``. At the end
    the buyer sells the home (``sell_costs``) and repays the mortgage; both
    sell their investments and pay 25% tax on the real gain.

    ``home_path`` and ``invest_path``, when given, are monthly nominal growth
    factors (``years * 12`` of them) that replace the fixed yearly rates.

    ``extra_equity`` is cash beyond the minimum down payment. Both start with
    it: the buyer puts it into the home, so the mortgage is smaller (and
    invests whatever is left once there is no mortgage); the renter invests it.

    The buyer also pays mortgage life insurance (``life_insurance`` of the
    balance a year) and building insurance (``home_insurance`` of the home
    value a year).
    """

    months = years * 12
    loan = max(price * ltv - extra_equity, 0.0)
    upfront = price * (1 - ltv + buy_costs) + purchase_tax(price, buyer) + extra_equity
    payment = loan / _annuity_factor(rate, term)
    monthly_rate = rate / 12
    monthly_inflation = (1 + inflation) ** (1 / 12)
    if home_path is None:
        home_path = np.full(months, (1 + home_growth) ** (1 / 12))
    if invest_path is None:
        invest_path = np.full(months, (1 + invest_return) ** (1 / 12))
    owner, renter = _Portfolio(1.0, monthly_inflation), _Portfolio(1.0, monthly_inflation)
    renter.value = renter.basis = upfront
    owner.value = owner.basis = max(extra_equity - price * ltv, 0.0)
    balance = loan
    home = price
    paid_owner = paid_renter = 0.0
    for month in range(months):
        mortgage = 0.0
        if balance > 0:
            interest = balance * monthly_rate
            mortgage = min(payment, balance + interest)
            balance = balance + interest - mortgage
        owner_cost = mortgage + home * (upkeep + home_insurance) / 12 + max(balance, 0.0) * life_insurance / 12
        rent_cost = rent * (1 + rent_growth) ** (month // 12)
        paid_owner += owner_cost
        paid_renter += rent_cost
        owner.growth = renter.growth = invest_path[month]
        owner.step(max(rent_cost - owner_cost, 0.0))
        renter.step(max(owner_cost - rent_cost, 0.0))
        home *= home_path[month]
    buy = home * (1 - sell_costs) - max(balance, 0.0) + owner.after_tax()
    rent_total = renter.after_tax()
    return {
        "buy": buy,
        "rent": rent_total,
        "home_value": home,
        "mortgage_left": max(balance, 0.0),
        "upfront": upfront,
        "payment": payment,
        "paid_owner": paid_owner,
        "paid_renter": paid_renter,
    }


def _breakeven_growth(wealth) -> float:
    """Nominal yearly home growth at which buying and renting end equal (``wealth(g)`` gives buy - rent)."""

    low, high = -0.5, 1.0
    if wealth(low) > 0:
        return low
    if wealth(high) < 0:
        return high
    for _ in range(60):
        middle = (low + high) / 2
        if wealth(middle) < 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _home_real_growth_history(data: InvestData, housing: pd.DataFrame, years: int) -> np.ndarray:
    """Real yearly growth of dwelling prices over every ``years``-long window since 1986."""

    homes = homes_vs_stocks(data=data, housing=housing, real=True)["homes"].to_numpy()
    months = years * 12
    if len(homes) <= months:
        return np.array([])
    return (homes[months:] / homes[:-months]) ** (1 / years) - 1


def buy_vs_rent(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    price: float = DEFAULT_RENT_PRICE,
    rent: float = DEFAULT_RENT_RENT,
    years: int = DEFAULT_RENT_YEARS,
    rate: float = DEFAULT_RENT_RATE,
    term: int = DEFAULT_RENT_TERM,
    inflation: float = DEFAULT_RENT_INFLATION,
    rent_growth: float = DEFAULT_RENT_GROWTH,
    invest_return: float = DEFAULT_RENT_INVEST,
    upkeep: float = DEFAULT_RENT_UPKEEP,
    buy_costs: float = DEFAULT_RENT_BUY_COSTS,
    sell_costs: float = DEFAULT_RENT_SELL_COSTS,
    ltv: float = DEFAULT_RENT_LTV,
    buyer: str = DEFAULT_RENT_BUYER,
    stock_share: float = DEFAULT_RENT_STOCKS,
    extra_equity: float = 0.0,
    life_insurance: float = DEFAULT_RENT_LIFE_INSURANCE,
    home_insurance: float = DEFAULT_RENT_HOME_INSURANCE,
) -> pd.DataFrame:
    """Buy now or rent and invest: wealth after ``years`` by yearly home price growth.

    A forward calculation at fixed rates (see ``_buy_rent_wealth``). Rows
    cover real home growth from -3% to +6% a year, plus the break-even growth
    (``point == "breakeven"``) and the median of history (``"history"``).
    Columns: growth_real, growth_nominal, buy_wealth, rent_wealth (nominal),
    buy_advantage (buy - rent, in today's shekels), buy_today, rent_today, history_share (the share of
    ``years``-long windows since 1986 in which real dwelling prices grew at
    least this fast), point, and the fixed upfront, payment and mortgage_left.
    ``history_buy_wins`` (the same on every row) is the share of start months
    since 1986 in which buying won when the renter's returns also come from
    history (see ``buy_vs_rent_history``, with ``stock_share`` in stocks).
    """

    if price <= 0 or rent <= 0:
        raise CalculationInputError("המחיר ושכר הדירה צריכים להיות חיוביים.")
    if not 1 <= years <= 30:
        raise CalculationInputError("מספר השנים צריך להיות בין 1 ל-30.")
    if not 0 < ltv < 1:
        raise CalculationInputError("שיעור המימון צריך להיות בין 0 ל-100%.")
    if buyer not in AFFORD_LTV:
        raise CalculationInputError("סוג הרוכש לא מוכר.")
    if extra_equity < 0:
        raise CalculationInputError("ההון העצמי הנוסף לא יכול להיות שלילי.")
    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    history = _home_real_growth_history(data, housing, years)
    deflator = (1 + inflation) ** years
    settings = dict(
        price=price, rent=rent, years=years, rate=rate, term=term, inflation=inflation, rent_growth=rent_growth,
        invest_return=invest_return, upkeep=upkeep, buy_costs=buy_costs, sell_costs=sell_costs, ltv=ltv, buyer=buyer,
        extra_equity=extra_equity, life_insurance=life_insurance, home_insurance=home_insurance,
    )

    def wealth(nominal: float) -> dict:
        return _buy_rent_wealth(nominal, **settings)

    joint = _buy_rent_history(data, housing, settings, stock_share)
    buy_wins = float((joint["buy_advantage"] > 0).mean()) if len(joint) else np.nan

    breakeven = _breakeven_growth(lambda nominal: (lambda w: w["buy"] - w["rent"])(wealth(nominal)))
    marks = {round((1 + breakeven) / (1 + inflation) - 1, 6): "breakeven"}
    if len(history):
        marks.setdefault(round(float(np.median(history)), 6), "history")

    def row(real: float, point: str = "") -> dict:
        nominal = (1 + real) * (1 + inflation) - 1
        result = wealth(nominal)
        return {
            "growth_real": real,
            "growth_nominal": nominal,
            "buy_wealth": result["buy"],
            "rent_wealth": result["rent"],
            "buy_advantage": (result["buy"] - result["rent"]) / deflator,
            "buy_today": result["buy"] / deflator,
            "rent_today": result["rent"] / deflator,
            "history_share": float(np.mean(history >= real - 1e-12)) if len(history) else np.nan,
            "history_buy_wins": buy_wins,
            "upfront": result["upfront"],
            "payment": result["payment"],
            "mortgage_left": result["mortgage_left"],
            "paid_owner": result["paid_owner"],
            "paid_renter": result["paid_renter"],
            "point": point,
        }

    grid = [value for value in RENT_GROWTH_GRID if not any(abs(value - mark) < 1e-9 for mark in marks)]
    rows = [row(value) for value in grid] + [row(value, point) for value, point in marks.items()]
    return pd.DataFrame(rows).sort_values("growth_real", kind="stable").reset_index(drop=True)


def buy_vs_rent_horizons(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Break-even real home growth for each horizon, next to what history shows.

    Takes the same arguments as ``buy_vs_rent`` (``years`` is ignored).
    Columns: years, breakeven_real, history_median, history_p10, history_p90,
    history_share (windows at or above the break-even), windows, and
    history_buy_wins (start months in which buying won with the renter's
    returns from history too, see ``buy_vs_rent_history``).
    """

    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    kwargs.pop("years", None)
    stock_share = kwargs.pop("stock_share", DEFAULT_RENT_STOCKS)
    settings = _rent_settings(kwargs)
    settings.pop("years")
    rows = []
    for years in RENT_HORIZONS:
        nominal = _breakeven_growth(lambda g: (lambda w: w["buy"] - w["rent"])(_buy_rent_wealth(g, years=years, **settings)))
        joint = _buy_rent_history(data, housing, {**settings, "years": years}, stock_share)
        real = (1 + nominal) / (1 + settings["inflation"]) - 1
        history = _home_real_growth_history(data, housing, years)
        rows.append(
            {
                "years": years,
                "breakeven_real": real,
                "history_median": float(np.median(history)) if len(history) else np.nan,
                "history_p10": float(np.quantile(history, 0.1)) if len(history) else np.nan,
                "history_p90": float(np.quantile(history, 0.9)) if len(history) else np.nan,
                "history_share": float(np.mean(history >= real)) if len(history) else np.nan,
                "windows": len(history),
                "history_buy_wins": float((joint["buy_advantage"] > 0).mean()) if len(joint) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _rent_settings(kwargs: dict) -> dict:
    return {
        "price": DEFAULT_RENT_PRICE, "rent": DEFAULT_RENT_RENT, "years": DEFAULT_RENT_YEARS, "rate": DEFAULT_RENT_RATE,
        "term": DEFAULT_RENT_TERM, "inflation": DEFAULT_RENT_INFLATION, "rent_growth": DEFAULT_RENT_GROWTH,
        "invest_return": DEFAULT_RENT_INVEST, "upkeep": DEFAULT_RENT_UPKEEP, "buy_costs": DEFAULT_RENT_BUY_COSTS,
        "sell_costs": DEFAULT_RENT_SELL_COSTS, "ltv": DEFAULT_RENT_LTV, "buyer": DEFAULT_RENT_BUYER, **kwargs,
    }


def _buy_rent_history(data: InvestData, housing: pd.DataFrame, settings: dict, stock_share: float) -> pd.DataFrame:
    """Buy minus rent for every start month, with home prices and the renter's returns from history."""

    if not 0 <= stock_share <= 1:
        raise CalculationInputError("חלק המניות צריך להיות בין 0 ל-100%.")
    years, inflation = settings["years"], settings["inflation"]
    homes = homes_vs_stocks(data=data, housing=housing, real=True)
    market = _down_payment_market(data, housing)
    if not homes["date"].reset_index(drop=True).equals(market["date"].reset_index(drop=True)):
        raise CalculationInputError("סדרות מחירי הדירות והמניות לא מתאימות.")
    home = homes["homes"].to_numpy()
    value = market["value_ils"].to_numpy()
    cpi = market["cpi_il"].to_numpy()
    stock = value[1:] / value[:-1] * (1 - DOWN_STOCK_FEE) ** (1 / 12)
    cash = 1 + (market["cash_rate"].to_numpy()[:-1] / 100 - DOWN_CASH_SPREAD) / 12
    monthly_inflation = (1 + inflation) ** (1 / 12)
    invest_real = (stock_share * stock + (1 - stock_share) * cash) / (cpi[1:] / cpi[:-1])
    home_real = home[1:] / home[:-1]
    months = years * 12
    if len(home_real) < months:
        raise CalculationInputError("אין מספיק שנים של נתונים לתקופה הזו.")
    deflator = (1 + inflation) ** years
    rows = []
    for start in range(len(home_real) - months + 1):
        homes_window = home_real[start:start + months]
        invest_window = invest_real[start:start + months]
        result = _buy_rent_wealth(
            0.0, home_path=homes_window * monthly_inflation, invest_path=invest_window * monthly_inflation, **settings
        )
        rows.append(
            {
                "start": market["date"].iloc[start],
                "end": market["date"].iloc[start + months],
                "buy_advantage": (result["buy"] - result["rent"]) / deflator,
                "buy_today": result["buy"] / deflator,
                "rent_today": result["rent"] / deflator,
                "home_real": float(np.prod(homes_window)) ** (1 / years) - 1,
                "invest_real": float(np.prod(invest_window)) ** (1 / years) - 1,
            }
        )
    return pd.DataFrame(rows)


def buy_vs_rent_history(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    stock_share: float = DEFAULT_RENT_STOCKS,
    **kwargs,
) -> pd.DataFrame:
    """Buy or rent for every start month since 1986, with both home prices and returns from history.

    The fixed calculator takes home prices from history but the renter's
    return as an input; here both come from the same months. Homes follow the
    real CBS dwelling index, and the renter's money is ``stock_share`` in the
    S&P 500 in shekels (dividends, 0.1% a year fee) and the rest in a
    money-market fund, rebalanced monthly, deflated by Israeli CPI. Both real
    paths are turned nominal at the ``inflation`` input, so the mortgage rate,
    rent and costs stay today's inputs. Takes the same arguments as
    ``buy_vs_rent``. Columns: start, end, buy_advantage (today's shekels),
    buy_today, rent_today, home_real and invest_real (yearly, in that window).
    """

    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    return _buy_rent_history(data, housing, _rent_settings(kwargs), stock_share)


# --- Young couples: repay the mortgage early, or invest ----------------------

DEFAULT_PREPAY_AMOUNT = 100_000.0
DEFAULT_PREPAY_RATE = 0.05  # nominal mortgage rate on the track being repaid
DEFAULT_PREPAY_YEARS_LEFT = 25
DEFAULT_PREPAY_HORIZON = 10
DEFAULT_PREPAY_INFLATION = 0.02
DEFAULT_PREPAY_FEE = 0.0  # early-repayment fee, as a share of the amount
DEFAULT_PREPAY_STOCKS = 1.0
PREPAY_RETURN_GRID = tuple(round(-0.02 + step * 0.005, 3) for step in range(21))  # real, -2% to +8%


def _prepay_gap(
    amount: float,
    real_rate: float,
    years_left: int,
    fee: float,
    growth: np.ndarray,
) -> tuple[float, float, float]:
    """Wealth of investing minus wealth of prepaying, in real terms, over ``len(growth)`` months.

    Prepaying ``amount`` (less ``fee``) cuts the monthly payment and keeps the
    term; the saving is invested every month. Investing puts ``amount`` in the
    market at once and keeps paying the higher payment. Everything is in
    today's shekels (as for a CPI-linked loan) and 25% tax is paid on the real
    gain at the end. Returns (gap, invest_wealth, prepay_wealth), where wealth
    is the portfolio after tax less the part of the loan still owed.
    """

    repaid = amount * (1 - fee)
    saving = repaid / _annuity_factor(real_rate, years_left)
    monthly = real_rate / 12
    invest_value = amount
    prepay_value = prepay_basis = 0.0
    owed = repaid  # the part of the loan the investor still owes
    months_left = years_left * 12
    for month, step in enumerate(growth):
        invest_value *= step
        prepay_value = prepay_value * step
        if month < months_left:
            prepay_value += saving
            prepay_basis += saving
            owed = owed * (1 + monthly) - saving
    owed = max(owed, 0.0)

    def after_tax(value: float, basis: float) -> float:
        return value - TAX_RATE * max(value - basis, 0.0)

    invest = after_tax(invest_value, amount) - owed
    prepay = after_tax(prepay_value, prepay_basis)
    return invest - prepay, invest, prepay


def prepay_vs_invest(
    amount: float = DEFAULT_PREPAY_AMOUNT,
    rate: float = DEFAULT_PREPAY_RATE,
    years_left: int = DEFAULT_PREPAY_YEARS_LEFT,
    horizon: int = DEFAULT_PREPAY_HORIZON,
    inflation: float = DEFAULT_PREPAY_INFLATION,
    fee: float = DEFAULT_PREPAY_FEE,
) -> pd.DataFrame:
    """Investing minus prepaying after ``horizon`` years, by a fixed real return on the investment.

    Rows cover real yearly returns from -2% to +8%, plus the break-even return
    (``point == "breakeven"``). Columns: return_real, invest_advantage, invest_wealth, prepay_wealth
    (today's shekels), point, saving (the monthly payment cut by prepaying),
    rate_real.
    """

    _check_prepay(amount, years_left, horizon, fee)
    real_rate = (1 + rate) / (1 + inflation) - 1
    months = horizon * 12

    def gap(real_return: float) -> tuple[float, float, float]:
        growth = np.full(months, (1 + real_return) ** (1 / 12))
        return _prepay_gap(amount, real_rate, years_left, fee, growth)

    low, high = -0.5, 1.0
    for _ in range(60):
        middle = (low + high) / 2
        if gap(middle)[0] < 0:
            low = middle
        else:
            high = middle
    breakeven = round((low + high) / 2, 6)
    saving = amount * (1 - fee) / _annuity_factor(real_rate, years_left)
    rows = []
    for value, point in [(value, "") for value in PREPAY_RETURN_GRID if abs(value - breakeven) > 1e-9] + [(breakeven, "breakeven")]:
        difference, invest, prepay = gap(value)
        rows.append({"return_real": value, "invest_advantage": difference, "invest_wealth": invest, "prepay_wealth": prepay, "point": point, "saving": saving, "rate_real": real_rate})
    return pd.DataFrame(rows).sort_values("return_real", kind="stable").reset_index(drop=True)


def _check_prepay(amount: float, years_left: int, horizon: int, fee: float) -> None:
    if amount <= 0:
        raise CalculationInputError("הסכום צריך להיות חיובי.")
    if not 1 <= years_left <= 30:
        raise CalculationInputError("מספר השנים שנשארו במשכנתא צריך להיות בין 1 ל-30.")
    if not 1 <= horizon <= 30:
        raise CalculationInputError("מספר השנים צריך להיות בין 1 ל-30.")
    if not 0 <= fee < 0.5:
        raise CalculationInputError("עמלת הפירעון צריכה להיות בין 0 ל-50%.")


def prepay_history(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    amount: float = DEFAULT_PREPAY_AMOUNT,
    rate: float = DEFAULT_PREPAY_RATE,
    years_left: int = DEFAULT_PREPAY_YEARS_LEFT,
    horizon: int = DEFAULT_PREPAY_HORIZON,
    inflation: float = DEFAULT_PREPAY_INFLATION,
    fee: float = DEFAULT_PREPAY_FEE,
    stock_share: float = DEFAULT_PREPAY_STOCKS,
) -> pd.DataFrame:
    """Investing minus prepaying for every start month since 1986, with historical returns.

    The investment is ``stock_share`` in the S&P 500 in shekels (dividends,
    0.1% a year fee) and the rest in a money-market fund, rebalanced monthly,
    all deflated by Israeli CPI. The mortgage keeps the fixed real rate
    implied by ``rate`` and ``inflation``. Columns: start, end, invest_advantage,
    invest_wealth, prepay_wealth (today's shekels), return_real (the investment's yearly real
    return in that window).
    """

    _check_prepay(amount, years_left, horizon, fee)
    if not 0 <= stock_share <= 1:
        raise CalculationInputError("חלק המניות צריך להיות בין 0 ל-100%.")
    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    market = _down_payment_market(data, housing)
    value = market["value_ils"].to_numpy()
    cpi = market["cpi_il"].to_numpy()
    stock = value[1:] / value[:-1] * (1 - DOWN_STOCK_FEE) ** (1 / 12)
    cash = 1 + (market["cash_rate"].to_numpy()[:-1] / 100 - DOWN_CASH_SPREAD) / 12
    real_growth = (stock_share * stock + (1 - stock_share) * cash) / (cpi[1:] / cpi[:-1])
    real_rate = (1 + rate) / (1 + inflation) - 1
    months = horizon * 12
    if len(real_growth) < months:
        raise CalculationInputError("אין מספיק שנים של נתונים לתקופה הזו.")
    fixed = prepay_vs_invest(amount=amount, rate=rate, years_left=years_left, horizon=horizon, inflation=inflation, fee=fee)
    breakeven = float(fixed.loc[fixed["point"] == "breakeven", "return_real"].iloc[0])
    saving = float(fixed["saving"].iloc[0])
    rows = []
    for start in range(len(real_growth) - months + 1):
        growth = real_growth[start:start + months]
        difference, invest, prepay = _prepay_gap(amount, real_rate, years_left, fee, growth)
        rows.append(
            {
                "start": market["date"][start],
                "end": market["date"][start + months],
                "invest_advantage": difference,
                "invest_wealth": invest,
                "prepay_wealth": prepay,
                "return_real": float(np.prod(growth)) ** (1 / horizon) - 1,
                "breakeven_real": breakeven,
                "saving": saving,
            }
        )
    return pd.DataFrame(rows)


# --- Young couples: money for a planned expense --------------------------------

DEFAULT_GOAL_AMOUNT = 30_000.0
DEFAULT_GOAL_YEARS = 2
DEFAULT_GOAL_STOCKS = 1.0


def short_goal_history(
    data: InvestData | None = None,
    housing: pd.DataFrame | None = None,
    amount: float = DEFAULT_GOAL_AMOUNT,
    years: int = DEFAULT_GOAL_YEARS,
    stock_share: float = DEFAULT_GOAL_STOCKS,
) -> pd.DataFrame:
    """Money put aside for an expense ``years`` ahead: invested vs a money-market fund, every start month since 1986.

    The invested money is ``stock_share`` in the S&P 500 in shekels
    (dividends, 0.1% a year fee) and the rest in a money-market fund
    (Bank of Israel rate minus a spread), rebalanced monthly. Both are sold at
    the end with 25% tax on the real gain, and shown in shekels of the start
    month (deflated by Israeli CPI). Columns: start, end, invest_today,
    cash_today, gap (invest minus cash) and stock_real (the S&P 500's real
    yearly return in that window).
    """

    if amount <= 0:
        raise CalculationInputError("הסכום צריך להיות חיובי.")
    if not 1 <= years <= 10:
        raise CalculationInputError("מספר השנים צריך להיות בין 1 ל-10.")
    if not 0 <= stock_share <= 1:
        raise CalculationInputError("חלק המניות צריך להיות בין 0 ל-100%.")
    data = data or load_data()
    if housing is None:
        from invest_core.data import load_housing_monthly

        housing = load_housing_monthly()
    market = _down_payment_market(data, housing)
    value = market["value_ils"].to_numpy()
    cpi = market["cpi_il"].to_numpy()
    stock = value[1:] / value[:-1] * (1 - DOWN_STOCK_FEE) ** (1 / 12)
    cash = 1 + (market["cash_rate"].to_numpy()[:-1] / 100 - DOWN_CASH_SPREAD) / 12
    inflation = cpi[1:] / cpi[:-1]
    mix_real = (stock_share * stock + (1 - stock_share) * cash) / inflation
    cash_real = cash / inflation
    stock_real = stock / inflation
    months = years * 12
    if len(mix_real) < months:
        raise CalculationInputError("אין מספיק שנים של נתונים לתקופה הזו.")

    def after_tax(growth: float) -> float:
        end = amount * growth
        return end - 0.25 * max(end - amount, 0.0)

    rows = []
    for start in range(len(mix_real) - months + 1):
        invest = after_tax(float(np.prod(mix_real[start:start + months])))
        saved = after_tax(float(np.prod(cash_real[start:start + months])))
        rows.append(
            {
                "start": market["date"].iloc[start],
                "end": market["date"].iloc[start + months],
                "invest_today": invest,
                "cash_today": saved,
                "gap": invest - saved,
                "stock_real": float(np.prod(stock_real[start:start + months])) ** (1 / years) - 1,
            }
        )
    return pd.DataFrame(rows)


# --- Young couples: help from parents, a gift or a loan ----------------------

DEFAULT_FAMILY_HELP = 200_000.0
DEFAULT_FAMILY_LOAN_YEARS = 10
FAMILY_SCENARIOS = ("none", "gift", "loan")


def family_help(
    equity: float = DEFAULT_AFFORD_EQUITY,
    income: float = DEFAULT_AFFORD_INCOME,
    help_amount: float = DEFAULT_FAMILY_HELP,
    loan_years: int = DEFAULT_FAMILY_LOAN_YEARS,
    rate: float = DEFAULT_AFFORD_RATE,
    years: int = DEFAULT_AFFORD_YEARS,
    pti: float = DEFAULT_AFFORD_PTI,
    costs: float = DEFAULT_AFFORD_COSTS,
    buyer: str = DEFAULT_AFFORD_BUYER,
    renovation: float = DEFAULT_AFFORD_RENOVATION,
) -> pd.DataFrame:
    """Highest apartment price without help, with a gift and with an interest-free loan from parents.

    A gift adds to the equity. A loan adds the same equity, but the bank
    counts its monthly repayment (``help_amount / loan_years / 12``) against
    the income limit, so the mortgage can be smaller. Columns: help,
    equity, max_price, mortgage, payment, family_payment, binding.
    """

    if help_amount < 0:
        raise CalculationInputError("סכום העזרה לא יכול להיות שלילי.")
    if not 1 <= loan_years <= 30:
        raise CalculationInputError("תקופת ההלוואה צריכה להיות בין 1 ל-30 שנים.")
    family_payment = help_amount / (loan_years * 12)
    cases = (
        ("none", equity, income, 0.0),
        ("gift", equity + help_amount, income, 0.0),
        # The bank lowers the mortgage payment it allows by the repayment to the parents.
        ("loan", equity + help_amount, max(income - family_payment / pti, 0.0), family_payment),
    )
    rows = []
    for scenario, value, usable_income, repayment in cases:
        frame = affordability(equity=value, income=max(usable_income, 1e-9), rate=rate, years=years, pti=pti, costs=costs, buyer=buyer, renovation=renovation)
        now = frame[frame["point"] == "now"].iloc[0]
        rows.append(
            {
                "help": scenario,
                "equity": value,
                "max_price": now["max_price"],
                "mortgage": now["mortgage"],
                "payment": now["payment"],
                "family_payment": repayment,
                "binding": now["binding"],
            }
        )
    return pd.DataFrame(rows)


# --- Young couples: savings for every child ------------------------------------

KIDS_DEPOSIT = 58.0  # monthly government deposit, 2026; indexed every January, so constant in today's shekels
KIDS_GRANT = 582.0  # at 21 if nothing was withdrawn; at 18 only for children born before 2017
KIDS_SMALL_GRANT = 291.0  # at 3 and at bar/bat mitzvah, for children born from 2017
# Investment tracks: share in stocks (assumption, see the page), and a bank deposit.
KIDS_TRACKS = {"low": 0.15, "medium": 0.4, "high": 0.75, "bank": None}
KIDS_BANK_REAL = 0.005
DEFAULT_KIDS_TRACK = "high"


def kids_savings(withdraw_age: int = 21, parent_addition: bool = True, born_2017: bool = True) -> pd.DataFrame:
    """The child-savings plan from birth, by track, in today's shekels.

    Bituach Leumi deposits ``KIDS_DEPOSIT`` a month, and parents may add the
    same from the child allowance. Provident-fund tracks earn the stock share
    times ``PENSION_STOCK_RETURN`` plus the rest times ``PENSION_OTHER_RETURN``
    (real, no fees: the state pays them until 21); the bank track earns
    ``KIDS_BANK_REAL``. Grants: ``KIDS_SMALL_GRANT`` at 3 and 13 for children
    born from 2017 (``KIDS_GRANT`` at 18 for earlier ones), and ``KIDS_GRANT``
    at 21 when nothing was withdrawn before. Tax: 25% of the real gain at
    withdrawal.

    Columns: track, age, balance, deposits (with the parent addition when
    chosen), balance_no_parent, and at the last age after_tax (as chosen),
    after_tax_parent and after_tax_no_parent.
    """

    if withdraw_age not in (18, 21):
        raise CalculationInputError("גיל המשיכה צריך להיות 18 או 21.")
    rows = []
    for track, stocks in KIDS_TRACKS.items():
        real = KIDS_BANK_REAL if stocks is None else stocks * PENSION_STOCK_RETURN + (1 - stocks) * PENSION_OTHER_RETURN
        monthly = (1 + real) ** (1 / 12)
        balances = {True: 0.0, False: 0.0}
        deposits = {True: 0.0, False: 0.0}
        rows.append({"track": track, "age": 0, "balance": 0.0, "deposits": 0.0, "balance_no_parent": 0.0})
        for month in range(withdraw_age * 12):
            age_after = (month + 1) / 12
            for with_parent in (True, False):
                deposit = KIDS_DEPOSIT * (2 if with_parent else 1) if month < 18 * 12 else 0.0
                grant = 0.0
                if month + 1 in (3 * 12, 13 * 12) and born_2017:
                    grant = KIDS_SMALL_GRANT
                if month + 1 == 18 * 12 and not born_2017:
                    grant = KIDS_GRANT
                if month + 1 == 21 * 12:
                    grant = KIDS_GRANT
                balances[with_parent] = balances[with_parent] * monthly + deposit + grant
                deposits[with_parent] += deposit + grant
            if (month + 1) % 12 == 0:
                rows.append(
                    {
                        "track": track,
                        "age": int(age_after),
                        "balance": balances[parent_addition],
                        "deposits": deposits[parent_addition],
                        "balance_no_parent": balances[False],
                    }
                )
        last = rows[-1]
        last["after_tax"] = balances[parent_addition] - TAX_RATE * max(balances[parent_addition] - deposits[parent_addition], 0.0)
        last["after_tax_parent"] = balances[True] - TAX_RATE * max(balances[True] - deposits[True], 0.0)
        last["after_tax_no_parent"] = balances[False] - TAX_RATE * max(balances[False] - deposits[False], 0.0)
    return pd.DataFrame(rows)


# --- Young couples: keren hishtalmut as part of the down payment ---------------

HISHTALMUT_CEILING = 15_712.0  # monthly salary ceiling for the tax exemption, 2026 (frozen until 2027)
HISHTALMUT_RATE = 0.10  # 7.5% employer + 2.5% employee
HISHTALMUT_LIQUID_YEARS = 6
DEFAULT_HISHTALMUT_SALARY = 15_000.0
DEFAULT_HISHTALMUT_RETURN = 0.04  # real, before fees
DEFAULT_HISHTALMUT_FEE = 0.005
DEFAULT_HISHTALMUT_YEARS = 5


def hishtalmut(
    salary_a: float = DEFAULT_HISHTALMUT_SALARY,
    salary_b: float = DEFAULT_HISHTALMUT_SALARY,
    balance_a: float = 35_000.0,
    balance_b: float = 0.0,
    opened_a: int = 2,
    opened_b: int = 0,
    years: int = DEFAULT_HISHTALMUT_YEARS,
    real_return: float = DEFAULT_HISHTALMUT_RETURN,
    fee: float = DEFAULT_HISHTALMUT_FEE,
) -> pd.DataFrame:
    """Two partners' study funds year by year until a purchase in ``years``, in today's shekels.

    Each month ``HISHTALMUT_RATE`` of the salary up to ``HISHTALMUT_CEILING``
    is deposited. ``opened_*`` is how many years ago the fund got its first
    deposit (0 = no fund yet, opened now); the money is liquid without tax
    ``HISHTALMUT_LIQUID_YEARS`` after that. A salary of 0 means no deposits.
    Columns: year, balance_a, balance_b, liquid_a, liquid_b (bool), available
    (the liquid balances), total.
    """

    if not 1 <= years <= 15:
        raise CalculationInputError("מספר השנים צריך להיות בין 1 ל-15.")
    if min(salary_a, salary_b, balance_a, balance_b) < 0 or min(opened_a, opened_b) < 0:
        raise CalculationInputError("השכר, היתרה והוותק לא יכולים להיות שליליים.")
    monthly = ((1 + real_return) * (1 - fee)) ** (1 / 12)
    people = {"a": [salary_a, balance_a, opened_a], "b": [salary_b, balance_b, opened_b]}
    rows = []
    for year in range(years + 1):
        if year:
            for person in people.values():
                for _ in range(12):
                    person[1] = person[1] * monthly + HISHTALMUT_RATE * min(person[0], HISHTALMUT_CEILING)
        row = {"year": year}
        available = total = 0.0
        for key, (salary, balance, opened) in people.items():
            exists = balance > 0 or salary > 0
            liquid = exists and opened + year >= HISHTALMUT_LIQUID_YEARS
            row[f"balance_{key}"] = balance
            row[f"liquid_{key}"] = liquid
            total += balance
            available += balance if liquid else 0.0
        row["available"] = available
        row["total"] = total
        rows.append(row)
    return pd.DataFrame(rows)
