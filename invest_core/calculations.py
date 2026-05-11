"""Core server-side calculations ported from the Shiny/R baseline."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from invest_core.data import InvestData, load_data

DEFAULT_TAX_START = "1993-01-01"
DEFAULT_TAX_END = "2023-01-01"
DEFAULT_COMMISSIONS = (0.0, 0.2, 0.7)
DEFAULT_KUPAT_START_YEAR = 1995
DEFAULT_KUPAT_AGE = 40
DEFAULT_KUPAT_INITIAL = 70000
DEFAULT_KUPAT_PENSION_MONTHS = 250
DEFAULT_INDEPENDENT_START = "2000-01-01"
DEFAULT_INDEPENDENT_END = "2023-01-01"
DEFAULT_TRINITY_PORTFOLIO = "US Small Cap Value"
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


def _as_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value)


def _year_fraction(dates: pd.Series) -> pd.Series:
    return dates.dt.year + (dates.dt.month - 1) / 12


def _sp500_tax_base(
    data: InvestData,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
) -> pd.DataFrame:
    frame = (
        data.SP500DIV.loc[
            lambda df: (df["date"] >= _as_timestamp(start)) & (df["date"] <= _as_timestamp(end)),
            ["date", "SP500wDividends", "CPI"],
        ]
        .rename(columns={"SP500wDividends": "v"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    frame["CPI"] = frame["CPI"] / frame["CPI"].iloc[0]
    return frame


def tax_events(
    data: InvestData | None = None,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Return tax-event scenarios for the S&P 500 fixture date range."""

    data = data or load_data()
    frame = _sp500_tax_base(data, start, end)
    frame["v"] = frame["v"] / frame["CPI"]
    frame["v"] = frame["v"] / frame["v"].iloc[0]
    frame["Gain_i"] = frame["v"] / frame["v"].shift(1)
    frame["End25"] = frame["v"] - (frame["v"] - 1) * 0.25
    frame["EveryMonth"] = 1.0
    frame["EveryNMonths"] = 1.0
    frame["Every12Months"] = 1.0
    frame["Gain"] = 1.0

    for pos in range(1, len(frame)):
        relative = frame.at[pos, "v"] / frame.at[pos - 1, "v"]

        if relative <= 1:
            frame.at[pos, "EveryMonth"] = frame.at[pos - 1, "EveryMonth"] * relative
        else:
            gain = relative - (relative - 1) * 0.25
            frame.at[pos, "Gain"] = gain
            frame.at[pos, "EveryMonth"] = frame.at[pos - 1, "EveryMonth"] * gain

        for months, column in ((6, "EveryNMonths"), (12, "Every12Months")):
            frame.at[pos, column] = frame.at[pos - 1, column] * frame.at[pos, "Gain_i"]
            if pos >= months and (pos + 2) % months == 0:
                gain = frame.at[pos, column] - frame.at[pos - months, column]
                if gain > 0:
                    frame.at[pos, column] = frame.at[pos, column] - 0.25 * gain

    if not adjust_cpi:
        numeric_columns = frame.columns.difference(["date"])
        frame.loc[:, numeric_columns] = frame.loc[:, numeric_columns].multiply(frame["CPI"], axis=0)

    value_columns = ["v", "End25", "EveryMonth", "EveryNMonths", "Every12Months"]
    frame.loc[:, value_columns] = frame.loc[:, value_columns] * initial

    return frame[["date", "v", "Gain_i", "End25", "EveryMonth", "EveryNMonths", "Every12Months", "Gain"]]


def commission_tax(
    data: InvestData | None = None,
    commission: float = 0.0,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Return combined management-fee and tax-event scenarios."""

    data = data or load_data()
    frame = _sp500_tax_base(data, start, end)
    frame["v"] = frame["v"] / frame["CPI"]
    frame["v0"] = frame["v"]
    frame["v"] = frame["v"] / frame["v"].iloc[0]
    frame["Gain_i"] = frame["v"] / frame["v"].shift(1)
    frame["End25"] = frame["v"] - (frame["v"] - 1) * 0.25
    frame["EveryMonth"] = 1.0
    frame["EveryNMonths"] = 1.0
    frame["Every12Months"] = 1.0
    frame["Gain"] = 1.0

    monthly_commission = (1 + commission / 100) ** (1 / 12) - 1
    for pos in range(1, len(frame)):
        relative = frame.at[pos, "v0"] / frame.at[pos - 1, "v0"]
        frame.at[pos, "v"] = frame.at[pos - 1, "v"] * (1 - monthly_commission) * relative

        if relative <= 1:
            frame.at[pos, "EveryMonth"] = frame.at[pos - 1, "EveryMonth"] * relative * (1 - monthly_commission)
        else:
            gain = relative - (relative - 1) * 0.25
            frame.at[pos, "Gain"] = gain
            frame.at[pos, "EveryMonth"] = frame.at[pos - 1, "EveryMonth"] * gain * (1 - monthly_commission)

        for months, column in ((6, "EveryNMonths"), (12, "Every12Months")):
            frame.at[pos, column] = frame.at[pos - 1, column] * frame.at[pos, "Gain_i"] * (1 - monthly_commission)
            if pos >= months and (pos + 2) % months == 0:
                gain = frame.at[pos, column] - frame.at[pos - months, column]
                if gain > 0:
                    frame.at[pos, column] = frame.at[pos, column] * (1 - monthly_commission) - 0.25 * gain

    frame["End25"] = frame["v"] - (frame["v"] - 1) * 0.25
    result = frame.rename(
        columns={
            "v0": "SP500_in_NIS",
            "End25": "tax_at_end",
            "EveryNMonths": "tax_every_6_months",
            "Every12Months": "tax_every_12_months",
            "EveryMonth": "tax_every_month",
        }
    )

    if not adjust_cpi:
        numeric_columns = ["SP500_in_NIS", "tax_at_end", "tax_every_month", "tax_every_6_months", "tax_every_12_months"]
        result.loc[:, numeric_columns] = result.loc[:, numeric_columns].multiply(result["CPI"], axis=0)

    numeric_columns = ["SP500_in_NIS", "tax_at_end", "tax_every_month", "tax_every_6_months", "tax_every_12_months"]
    result.loc[:, numeric_columns] = result.loc[:, numeric_columns] * initial
    result["commission"] = commission
    return result[
        ["date", "SP500_in_NIS", "tax_at_end", "tax_every_month", "tax_every_6_months", "tax_every_12_months", "commission"]
    ]


def commission_tax_scenarios(
    data: InvestData | None = None,
    commissions: Iterable[float] = DEFAULT_COMMISSIONS,
    start: str | pd.Timestamp = DEFAULT_TAX_START,
    end: str | pd.Timestamp = DEFAULT_TAX_END,
    adjust_cpi: bool = True,
    initial: float = 1.0,
) -> pd.DataFrame:
    """Return the default combined commission/tax scenarios."""

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
    """Return annual management-fee drag scenarios from the Phase 1 fixture."""

    return commission_tax_scenarios(data, commissions, start, end, adjust_cpi, initial)


def sp500_risk(
    data: InvestData | None = None,
    years: int = 15,
    threshold: float = 0.04,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Return rolling S&P 500 real return risk for a window in years."""

    data = data or load_data()
    period = years * 12
    frame = data.SP500US.sort_values("date").reset_index(drop=True).copy()
    if start is not None:
        frame = frame[frame["date"] >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame["date"] <= pd.Timestamp(end)]
    frame["TotalReturn"] = frame["Real_Total_Return_Price"] / frame["Real_Total_Return_Price"].shift(period)
    frame = frame.dropna(subset=["TotalReturn"]).copy()
    frame["TotalReturnP"] = frame["TotalReturn"] ** (12 / period) - 1
    frame["Median"] = frame["TotalReturnP"].median()
    frame["Above0"] = (frame["TotalReturnP"] > 0).sum() / len(frame)
    frame["AboveThreshold"] = (frame["TotalReturnP"] > threshold).sum() / len(frame)
    return frame[["date", "TotalReturn", "TotalReturnP", "Median", "Above0", "AboveThreshold"]].reset_index(drop=True)


def portfolio_table(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2023,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
) -> pd.DataFrame:
    """Return normalized lazy-portfolio data used by summary calculations."""

    data = data or load_data()
    value_columns = {
        "cpi_il": ("Index_CPI_IL", "BadYears_CPI_IL", "Drop_CPI_IL"),
        "cpi_us": ("Index_CPI_US", "BadYears_CPI_US", "Drop_CPI_US"),
        "nominal": ("index", "BadYears", "Drop"),
    }
    if value_mode not in value_columns:
        raise ValueError(f"Unknown value_mode: {value_mode}")
    value_column, bad_years_column, drop_column = value_columns[value_mode]
    frame = data.LazyReturns1.copy()
    selected = set(portfolios)
    frame = frame[
        (frame["CommissionUse"] == commission_adjusted)
        & (frame["Portfolio"].isin(selected))
        & (frame["Year"] >= year_start - 1)
        & (frame["Year"] <= year_end)
    ].copy()
    min_index_year = frame.loc[frame[value_column].notna(), "Year"].min()
    frame = frame[frame["Year"] >= min_index_year].copy()
    frame["v"] = frame[value_column]
    frame["ShefelYears"] = frame[bad_years_column]
    frame["Drop"] = frame[drop_column]
    frame = frame.sort_values(["Portfolio", "Year"]).copy()
    frame["v"] = frame.groupby("Portfolio", sort=True)["v"].transform(lambda values: values / values.dropna().iloc[0])
    frame["row_number"] = frame.groupby("Portfolio", sort=True).cumcount()
    frame = frame[frame["row_number"] > 0].drop(columns=["row_number"])
    return frame.reset_index(drop=True)


def portfolio_summary(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2023,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
) -> pd.DataFrame:
    """Return portfolio CAGR, volatility, drawdown, and bad-year summary."""

    table = portfolio_table(data, portfolios, year_start, year_end, commission_adjusted, value_mode)
    rows: list[dict[str, float | str]] = []
    for portfolio, group in table.groupby("Portfolio", sort=True):
        group = group.sort_values("Year")
        n = len(group)
        cagr = group["v"].iloc[-1] ** (1 / n) - 1
        rows.append(
            {
                "Portfolio": portfolio,
                "FirstYear": group["Year"].iloc[0],
                "N": n,
                "SD": (group["v"] / group["v"].shift(1) - 1).std(skipna=True, ddof=1),
                "CAGR": cagr,
                "MaxDrop": group["Drop"].min(skipna=True),
                "MaxShefelYears": group["ShefelYears"].max(skipna=True),
                "Factor15": (1 + cagr) ** 15,
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Portfolio", "FirstYear", "N", "SD", "CAGR", "MaxDrop", "MaxShefelYears", "Factor15"],
    )


def portfolio_structure(data: InvestData | None = None) -> pd.DataFrame:
    """Return lazy-portfolio component weights in the original wide table shape."""

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
    """Return the assumed management-fee table for lazy portfolios."""

    data = data or load_data()
    frame = data.PortfoliosStructure.copy()
    frame = frame.groupby("Portfolio", sort=True, as_index=False).first()
    frame["Portfolio"] = frame["Portfolio"].str.replace("_", " ", regex=False)
    return frame.loc[:, ["Portfolio", "commission"]].rename(columns={"commission": "Assumed Commission"})


def kupat_gemel(
    data: InvestData | None = None,
    with_pension: bool = False,
    age: int = DEFAULT_KUPAT_AGE,
    start_year: int = DEFAULT_KUPAT_START_YEAR,
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
    """Return Kupat Gemel / policy / independent-investment comparison."""

    data = data or load_data()
    frame = (
        data.SP500DIV[["date", "SP500wDividends", "CPI"]]
        .rename(columns={"SP500wDividends": "v"})
        .copy()
    )
    frame["year"] = frame["date"].dt.year
    frame = frame[frame["year"] >= start_year].sort_values("date").reset_index(drop=True)
    frame["year3"] = _year_fraction(frame["date"])
    frame["age"] = frame["year3"] - start_year + age
    frame["CPI"] = frame["CPI"] / frame["CPI"].iloc[0]
    frame["MG"] = (frame["v"] / frame["v"].shift(1) - 1).fillna(0)

    kh_buy_factor = 1 - kh_buy_sell / 100
    ph_buy_factor = 1 - ph_buy_sell / 100
    ii_buy_factor = 1 - ii_buy_sell / 100

    kh_raw = kh_buy_factor * ((1 + frame["MG"]) * ((1 - kh_annual_fee / 100) ** (1 / 12))).cumprod()
    kh_raw = kh_raw * kh_buy_factor
    kh_taxed = (kh_raw / frame["CPI"] - (kh_raw / frame["CPI"] - 1) * 0.25) * frame["CPI"]
    frame["KH"] = np.select(
        [kh_raw / frame["CPI"] <= 1, frame["age"] < 60],
        [kh_raw, kh_taxed],
        default=kh_raw,
    )

    kh60 = frame.loc[frame["age"] == 60, "KH"].sum()
    cpi60 = frame.loc[frame["age"] == 60, "CPI"].sum()
    frame["Kitzba"] = np.where(frame["age"] > 60, (kh60 / pension_months) * (frame["CPI"] / cpi60), 0)
    frame["KH"] = np.where(frame["age"] > 60, kh60 * frame["CPI"] / cpi60, frame["KH"])

    ph_raw = ph_buy_factor * ((1 + frame["MG"]) * ((1 - ph_annual_fee / 100) ** (1 / 12))).cumprod()
    ph_raw = ph_raw * ph_buy_factor
    ph_taxed = (ph_raw / frame["CPI"] - (ph_raw / frame["CPI"] - 1) * 0.25) * frame["CPI"]
    frame["PH"] = np.where(ph_raw / frame["CPI"] <= 1, ph_raw, ph_taxed)

    ii_raw = ii_buy_factor * ((1 + frame["MG"]) * ((1 - ii_annual_fee / 100) ** (1 / 12))).cumprod()
    ii_taxed = (ii_raw / frame["CPI"] - (ii_raw / frame["CPI"] - 1) * 0.25) * frame["CPI"]
    frame["II"] = np.where(ii_raw / frame["CPI"] <= 1, ii_raw, ii_taxed) * ii_buy_factor

    if with_pension:
        iib = np.empty(len(frame), dtype=float)
        iib[0] = ii_buy_factor
        monthly_fee = (1 - ii_annual_fee / 100) ** (1 / 12)
        for pos in range(1, len(frame)):
            iib[pos] = iib[pos - 1] * (1 + frame.at[pos, "MG"]) * monthly_fee
            tax_i = iib[pos] / frame.at[pos, "CPI"]
            tax_i = 1 if tax_i <= 1 else (tax_i - (tax_i - 1) * 0.25) / tax_i
            iib[pos] = iib[pos] - frame.at[pos, "Kitzba"] / tax_i
        iib = iib * ii_buy_factor
        frame["IIb"] = np.where(iib / frame["CPI"] <= 1, iib, (iib / frame["CPI"] - (iib / frame["CPI"] - 1) * 0.25) * frame["CPI"])

    columns = ["KH", "II", "IIb", "Kitzba"] if with_pension else ["KH", "PH", "II"]
    for column in columns:
        if adjust_cpi:
            frame[column] = frame[column] * frame["CPI"].iloc[0] / frame["CPI"] * initial
        else:
            frame[column] = frame[column] * initial
    return frame[["date", "age", "year3", *columns]].reset_index(drop=True)


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
    """Return independent-investment commission and tax scenarios."""

    if tax_mode not in {"optional_tax", "us_vs_il"}:
        raise ValueError("tax_mode must be 'optional_tax' or 'us_vs_il'")

    data = data or load_data()
    frame = (
        data.SP500DIV.loc[
            lambda df: (df["date"] >= _as_timestamp(start)) & (df["date"] <= _as_timestamp(end)),
            ["date", "SP500wDividends", "CPI", "dollar"],
        ]
        .rename(columns={"SP500wDividends": "value", "dollar": "USD"})
        .merge(data.SP500US[["date", "CPI_US"]], on="date", how="left")
        .sort_values("date")
        .reset_index(drop=True)
    )

    monthly_commission = (1 - yearly_commission) ** (1 / 12)
    first_usd = frame["USD"].iloc[0]
    buy_sell_price = max(min_dollar_commission * first_usd, (initial / first_usd / share_price) * commission_per_share * first_usd)

    frame["value"] = frame["value"] / frame["value"].iloc[0]
    frame["firstUSD"] = first_usd
    frame["CPI"] = frame["CPI"] / frame["CPI"].iloc[0]
    frame["CPI_US"] = frame["CPI_US"] / frame["CPI_US"].iloc[0]
    frame["delta"] = (frame["value"] / frame["value"].shift(1) - 1).fillna(0)
    frame["v0"] = frame["value"] * initial
    frame["AfterBuying"] = initial * (1 - dollar_commission) - buy_sell_price

    values = np.empty(len(frame), dtype=float)
    values[0] = frame["AfterBuying"].iloc[0]
    for pos in range(1, len(frame)):
        values[pos] = values[pos - 1] * (1 + frame.at[pos, "delta"]) * monthly_commission
    frame["v"] = values

    frame["Profit"] = frame["v"] / frame["CPI"] - initial
    frame["TaxIL"] = np.maximum(0.25 * frame["Profit"], 0)
    frame["ProfitNominal"] = frame["v"] - initial
    frame["TaxILNominal"] = np.maximum(0.25 * frame["ProfitNominal"], 0)
    frame["vDollar"] = frame["v"] / frame["USD"]
    frame["ProfitUS"] = (frame["vDollar"] - initial / frame["firstUSD"]) * (frame["firstUSD"] / frame["USD"])
    frame["TaxDollar"] = np.minimum(np.maximum(0.25 * frame["ProfitUS"], 0) * frame["USD"], frame["TaxILNominal"])
    frame["BuySellPrice_i"] = np.maximum(frame["vDollar"] / share_price * commission_per_share * frame["USD"], min_dollar_commission * frame["USD"])
    frame["v_final"] = frame["v"] * (1 - dollar_commission) - (0 if tax_mode == "optional_tax" else frame["TaxIL"]) - frame["BuySellPrice_i"]
    frame["v_finalDollar"] = frame["v"] * (1 - dollar_commission) - frame["TaxDollar"] - frame["BuySellPrice_i"]

    for column in ("v0", "v_final", "v_finalDollar"):
        frame[column] = frame[column] * frame["CPI"].iloc[0] / frame["CPI"]

    if tax_mode == "optional_tax":
        return frame[["date", "v0", "v_final"]].reset_index(drop=True)
    return frame[["date", "v0", "v_final", "v_finalDollar"]].rename(
        columns={"v_final": "v_final_il", "v_finalDollar": "v_final_dollar"}
    ).reset_index(drop=True)


def portfolio_over_time(
    data: InvestData | None = None,
    portfolios: Iterable[str] = DEFAULT_PORTFOLIOS,
    year_start: int = 1955,
    year_end: int = 2023,
    commission_adjusted: bool = True,
    value_mode: str = "cpi_il",
    rolling_window: int | None = None,
    full_history_rolling: bool = False,
) -> pd.DataFrame:
    """Return portfolio accumulated and rolling return series."""

    if full_history_rolling:
        table = portfolio_table(data, portfolios, 1871, year_end, commission_adjusted, value_mode)
        table = table.sort_values(["Portfolio", "Year"]).copy()
        normalized = []
        for _, group in table.groupby("Portfolio", sort=True):
            group = group.sort_values("Year").copy()
            first_year = int(group["Year"].iloc[0])
            base_year = max(first_year, year_start - 1)
            base_values = group.loc[group["Year"] == base_year, "v"].dropna()
            if base_values.empty:
                continue
            group["v"] = group["v"] / base_values.iloc[0]
            normalized.append(group)
        table = pd.concat(normalized, ignore_index=True) if normalized else table.iloc[0:0].copy()
    else:
        table = portfolio_table(data, portfolios, year_start, year_end, commission_adjusted, value_mode)
    frames = []
    for _, group in table.groupby("Portfolio", sort=True):
        group = group.sort_values("Year").copy()
        group["N"] = group["Year"].max() - group["Year"].iloc[0]
        group["OneYear"] = group["v"] / group["v"].shift(1) - 1
        group["CAGR"] = group["v"] ** (1 / group["N"]) - 1
        group["CAGR10"] = (group["v"] / group["v"].shift(10)) ** (1 / 10) - 1
        columns = ["Year", "Portfolio", "v", "ShefelYears", "Drop", "N", "OneYear", "CAGR", "CAGR10"]
        if rolling_window is not None:
            group["RollingCAGR"] = (group["v"] / group["v"].shift(rolling_window)) ** (1 / rolling_window) - 1
            columns.append("RollingCAGR")
        if full_history_rolling:
            group = group[(group["Year"] >= year_start) & (group["Year"] <= year_end)]
        frames.append(group[columns])
    return pd.concat(frames, ignore_index=True)


def us_global_rolling(data: InvestData | None = None, global_mix: bool = False) -> pd.DataFrame:
    """Return S&P 500 rolling differences vs ex-US or a 60/40 global mix."""

    data = data or load_data()
    frame = data.LazyReturns1.loc[
        (~data.LazyReturns1["CommissionUse"])
        & (data.LazyReturns1["Portfolio"].isin(["S&P 500", "MSCI World ex USA index"])),
        ["Year", "Portfolio", "YearReturn"],
    ].copy()
    frame = frame.groupby("Year").filter(lambda group: len(group) == 2).dropna().reset_index(drop=True)

    compare_to = "MSCI World ex USA index"
    if global_mix:
        wide = frame.pivot(index="Year", columns="Portfolio", values="YearReturn").reset_index()
        wide["Mix"] = 0.6 * wide["S&P 500"] + 0.4 * wide["MSCI World ex USA index"]
        frame = wide.melt(id_vars="Year", value_vars=["S&P 500", "Mix"], var_name="Portfolio", value_name="YearReturn")
        compare_to = "Mix"

    out = []
    for _, group in frame.groupby("Portfolio", sort=True):
        group = group.sort_values("Year").copy()
        group["Five2"] = (1 + group["YearReturn"] / 100).cumprod()
        group["Five"] = (group["Five2"] / group["Five2"].shift(5)) ** (1 / 5)
        group["Ten"] = (group["Five2"] / group["Five2"].shift(10)) ** (1 / 10)
        group["Fifteen"] = (group["Five2"] / group["Five2"].shift(15)) ** (1 / 15)
        out.append(group)
    rolling = pd.concat(out, ignore_index=True).dropna(subset=["Five"])

    rows = []
    for year, group in rolling.groupby("Year", sort=True):
        sp = group[group["Portfolio"] == "S&P 500"]
        other = group[group["Portfolio"] == compare_to]
        rows.append(
            {
                "Year": year,
                "Diff5": sp["Five"].sum() - other["Five"].sum(),
                "Diff10": sp["Ten"].sum() - other["Ten"].sum(),
                "Diff15": sp["Fifteen"].sum() - other["Fifteen"].sum(),
            }
        )
    return pd.DataFrame(rows, columns=["Year", "Diff5", "Diff10", "Diff15"])


def us_world_rolling(data: InvestData | None = None) -> pd.DataFrame:
    """Return S&P 500 rolling differences vs MSCI World ex USA."""

    return us_global_rolling(data=data, global_mix=False)


def sp500_scv_rolling(
    data: InvestData | None = None,
    window: int = 15,
    after_tax: bool = False,
) -> pd.DataFrame:
    """Return S&P 500 vs US Small Cap Value rolling comparison."""

    data = data or load_data()
    source = data.LazyReturns1
    min_index_year = source.loc[source["Index_CPI_IL"].notna(), "Year"].min()
    frame = source.loc[
        (~source["CommissionUse"])
        & (source["Portfolio"].isin(["S&P 500", "US Small Cap Value"]))
        & (source["Year"] >= min_index_year)
        & (source["Year"] >= 1969 - window)
        & (source["Year"] <= 2023),
        ["Year", "Portfolio", "CPI_IL", "USD", "YearReturn", "index"],
    ].copy()

    frames = []
    for _, group in frame.groupby("Portfolio", sort=True):
        group = group.sort_values("Year").copy()
        if not after_tax:
            group["v"] = group["index"] * group["USD"] / group["CPI_IL"]
            group["CAGR"] = (group["v"] / group["v"].shift(window)) ** (1 / window) - 1
            frames.append(group.loc[group["Year"] >= 1969, ["Year", "Portfolio", "CAGR"]])
            continue

        group["A8"] = 1
        group["B8"] = group["A8"] / group["USD"].shift(window)
        group["D8"] = group["index"] / group["index"].shift(window)
        group["E8"] = group["CPI_IL"] / group["CPI_IL"].shift(window)
        group["F8"] = group["USD"] / group["USD"].shift(window)
        group["H8"] = group["D8"] * group["F8"] * group["A8"]
        group["I8"] = group["D8"] * group["B8"]
        group["K8"] = group["H8"] - group["A8"]
        group["L8"] = group["H8"] / group["E8"] - group["A8"]
        group["U8a"] = 0.25 * (group["I8"] - group["B8"]) * group["A8"] / group["B8"] * group["F8"]
        group["U8b"] = 0.25 * group["K8"]
        group["T8"] = np.maximum(0.25 * group["L8"], 0)
        group["U8"] = np.maximum(np.minimum(group["U8a"], group["U8b"]), 0)
        group["TaxPaidShekel"] = np.where(group["Portfolio"] == "S&P 500", group["T8"], group["U8"])
        group["NominalReturnAfterTax"] = group["H8"] - group["TaxPaidShekel"]
        group["GainAfterTax"] = (group["NominalReturnAfterTax"] / group["A8"]) / group["E8"] - 1
        group["CAGR_after_tax"] = (group["GainAfterTax"] + 1) ** (1 / window) - 1
        frames.append(group.dropna(subset=["CAGR_after_tax"]).loc[group["Year"] >= 1969, ["Year", "Portfolio", "GainAfterTax", "CAGR_after_tax"]])

    return pd.concat(frames, ignore_index=True).sort_values(["Year", "Portfolio"]).reset_index(drop=True)


def sp500_scv_heatmap(data: InvestData | None = None, max_years: int = 20) -> pd.DataFrame:
    """Return all-start/all-end S&P 500 vs SCV comparison rows."""

    data = data or load_data()
    source = data.LazyReturns1
    min_index_year = source.loc[source["Index_CPI_IL"].notna(), "Year"].min()
    frame = source.loc[
        (~source["CommissionUse"])
        & (source["Portfolio"].isin(["S&P 500", "US Small Cap Value"]))
        & (source["Year"] >= min_index_year),
        ["Portfolio", "Year", "index", "USD", "CPI_IL"],
    ].copy()
    frame["v"] = frame["index"] * frame["USD"] / frame["CPI_IL"]

    long_frames = []
    for _, group in frame[["Portfolio", "Year", "v"]].groupby("Portfolio", sort=True):
        group = group.sort_values(["Portfolio", "Year"]).copy()
        for years in range(1, max_years + 1):
            values = group["v"] / group["v"].shift(years) - 1
            chunk = pd.DataFrame(
                {
                    "Portfolio": group["Portfolio"],
                    "Year": group["Year"],
                    "InvYears": float(years),
                    "value": values,
                }
            ).dropna(subset=["value"])
            long_frames.append(chunk)
    long = pd.concat(long_frames, ignore_index=True)
    long["EndYear"] = long["Year"]
    long["StartYear"] = long["EndYear"] - long["InvYears"] + 1
    long["CAGR"] = (long["value"] + 1) ** (1 / long["InvYears"]) - 1

    rows = []
    for (start_year, end_year), group in long.groupby(["StartYear", "EndYear"], sort=True):
        group = group.sort_values("Portfolio")
        first = group.iloc[0]
        last = group.iloc[-1]
        rows.append(
            {
                "StartYear": start_year,
                "EndYear": end_year,
                "InvYears": first["InvYears"],
                "Portfolio": first["Portfolio"],
                "Portfolio2": last["Portfolio"],
                "val1": first["value"],
                "val2": last["value"],
                "cagr1": first["CAGR"],
                "cagr2": last["CAGR"],
                "delta_value": last["value"] - first["value"],
                "delta_cagr": last["CAGR"] - first["CAGR"],
            }
        )
    return pd.DataFrame(
        rows,
        columns=["StartYear", "EndYear", "InvYears", "Portfolio", "Portfolio2", "val1", "val2", "cagr1", "cagr2", "delta_value", "delta_cagr"],
    )


def global_vs_sp500_heatmap(data: InvestData | None = None, max_years: int = 20) -> pd.DataFrame:
    """Return all-start/all-end 60/40 global mix vs S&P 500 comparison rows."""

    data = data or load_data()
    frame = data.LazyReturns1.loc[
        (~data.LazyReturns1["CommissionUse"])
        & (data.LazyReturns1["Portfolio"].isin(["S&P 500", "MSCI World ex USA index"])),
        ["Year", "Portfolio", "YearReturn"],
    ].copy()
    frame = frame.groupby("Year").filter(lambda group: len(group) == 2).dropna().reset_index(drop=True)
    wide = frame.pivot(index="Year", columns="Portfolio", values="YearReturn").sort_index()
    wide["תיק גלובלי 60/40"] = 0.6 * wide["S&P 500"] + 0.4 * wide["MSCI World ex USA index"]

    values = wide[["S&P 500", "תיק גלובלי 60/40"]].copy()
    values = (1 + values / 100).cumprod()
    values = values.reset_index().melt(id_vars="Year", var_name="Portfolio", value_name="v")

    long_frames = []
    for _, group in values.groupby("Portfolio", sort=True):
        group = group.sort_values(["Portfolio", "Year"]).copy()
        for years in range(1, max_years + 1):
            returns = group["v"] / group["v"].shift(years) - 1
            chunk = pd.DataFrame(
                {
                    "Portfolio": group["Portfolio"],
                    "Year": group["Year"],
                    "InvYears": float(years),
                    "value": returns,
                }
            ).dropna(subset=["value"])
            long_frames.append(chunk)

    long = pd.concat(long_frames, ignore_index=True)
    long["EndYear"] = long["Year"]
    long["StartYear"] = long["EndYear"] - long["InvYears"] + 1
    long["CAGR"] = (long["value"] + 1) ** (1 / long["InvYears"]) - 1

    rows = []
    for (start_year, end_year), group in long.groupby(["StartYear", "EndYear"], sort=True):
        group = group.sort_values("Portfolio")
        sp500 = group.loc[group["Portfolio"] == "S&P 500"].iloc[0]
        global_mix = group.loc[group["Portfolio"] == "תיק גלובלי 60/40"].iloc[0]
        rows.append(
            {
                "StartYear": start_year,
                "EndYear": end_year,
                "InvYears": sp500["InvYears"],
                "Portfolio": sp500["Portfolio"],
                "Portfolio2": global_mix["Portfolio"],
                "val1": sp500["value"],
                "val2": global_mix["value"],
                "cagr1": sp500["CAGR"],
                "cagr2": global_mix["CAGR"],
                "delta_value": global_mix["value"] - sp500["value"],
                "delta_cagr": global_mix["CAGR"] - sp500["CAGR"],
            }
        )
    return pd.DataFrame(
        rows,
        columns=["StartYear", "EndYear", "InvYears", "Portfolio", "Portfolio2", "val1", "val2", "cagr1", "cagr2", "delta_value", "delta_cagr"],
    )


def trinity(
    data: InvestData | None = None,
    portfolio: str = DEFAULT_TRINITY_PORTFOLIO,
    yearly_draw: float = DEFAULT_TRINITY_DRAW,
    years: int = DEFAULT_TRINITY_YEARS,
    base: float = DEFAULT_TRINITY_BASE,
) -> pd.DataFrame:
    """Return Trinity withdrawal simulation by starting year."""

    data = data or load_data()
    source = data.LazyReturns1.loc[
        (data.LazyReturns1["Portfolio"] == portfolio) & (~data.LazyReturns1["CommissionUse"]),
        ["Year", "Portfolio", "commission", "CPI_US", "YearReturn"],
    ].copy()
    year_min = int(source["Year"].min())
    year_max = int(source["Year"].max() - years)

    rows = []
    for start_year in range(year_min, year_max + 1):
        group = source[(source["Year"] >= start_year) & (source["Year"] <= start_year + years)].sort_values("Year").reset_index(drop=True)
        left = np.empty(len(group), dtype=float)
        left[0] = base
        for pos in range(1, len(group)):
            previous = left[pos - 1]
            draw_left = previous - base * yearly_draw
            if previous > 0:
                left[pos] = draw_left * (1 - group.at[pos, "commission"] / 100) * (group.at[pos - 1, "CPI_US"] / group.at[pos, "CPI_US"]) * (1 + group.at[pos, "YearReturn"] / 100)
            else:
                left[pos] = draw_left * (group.at[pos - 1, "CPI_US"] / group.at[pos, "CPI_US"])
        rows.append(
            {
                "start_year": start_year,
                "end_year": start_year + years,
                "Investment_remained": left[-1],
                "Investment_low": left[1:].min(),
            }
        )
    return pd.DataFrame(rows, columns=["start_year", "end_year", "Investment_remained", "Investment_low"])
