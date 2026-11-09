"""Flask API endpoints over the ported Invest calculation layer."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from functools import lru_cache
import gzip
import math
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
import numpy as np
import pandas as pd

from invest_core import calculations as calc
from invest_core.data import load_data, load_housing_monthly
from invest_core.methodology import data_version, result_metadata

JsonDict = dict[str, Any]
Params = tuple[tuple[str, Any], ...]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


ENDPOINT_NAMES = (
    "tax_events",
    "commission_effect",
    "commission_tax",
    "sp500_risk",
    "sp500_risk_ladder",
    "portfolio_summary",
    "portfolio_structure",
    "portfolio_commissions",
    "kupat_gemel",
    "kupat_gemel_pension",
    "independent_commissions",
    "tax_us_vs_il",
    "portfolio_over_time",
    "us_world_rolling",
    "us_global_rolling",
    "global_vs_sp500_heatmap",
    "sp500_scv_rolling",
    "sp500_scv_heatmap",
    "sp500_scv_after_tax",
    "trinity",
    "affordability",
    "down_payment",
    "down_payment_ladder",
)

EXPENSIVE_ENDPOINTS = {
    "commission_effect",
    "commission_tax",
    "independent_commissions",
    "tax_us_vs_il",
    "portfolio_summary",
    "portfolio_structure",
    "portfolio_commissions",
    "portfolio_over_time",
    "us_world_rolling",
    "us_global_rolling",
    "global_vs_sp500_heatmap",
    "sp500_scv_rolling",
    "sp500_scv_heatmap",
    "sp500_scv_after_tax",
    "trinity",
    "down_payment",
    "down_payment_ladder",
}


# Old portfolio names still accepted in links.
PORTFOLIO_ALIASES = {"Precious Metals": "Gold Miners"}


class ApiValidationError(ValueError):
    """Raised when API query parameters are invalid. Messages are shown to users, in Hebrew."""


FIELD_LABELS = {
    "start": "תאריך התחלה",
    "end": "תאריך סיום",
    "adjust_cpi": "התאמה למדד",
    "initial": "הסכום ההתחלתי",
    "commissions": "דמי ניהול",
    "years": "מספר השנים",
    "threshold": "סף התשואה",
    "portfolios": "תיקים",
    "portfolio": "תיק",
    "year_start": "שנת התחלה",
    "year_end": "שנת סיום",
    "commission_adjusted": "דמי ניהול",
    "rolling_window": "מספר שנות ההשקעה",
    "full_history_rolling": "היסטוריה מלאה",
    "age": "גיל",
    "start_year": "שנת התחלה",
    "pension_months": "מקדם ההמרה לקצבה",
    "kh_buy_sell": "עלות קנייה ומכירה (קופת גמל)",
    "kh_annual_fee": "דמי ניהול (קופת גמל)",
    "ph_buy_sell": "עלות קנייה ומכירה (פוליסה)",
    "ph_annual_fee": "דמי ניהול (פוליסה)",
    "ii_buy_sell": "עלות קנייה ומכירה (השקעה עצמאית)",
    "ii_annual_fee": "דמי ניהול (השקעה עצמאית)",
    "share_price": "מחיר יחידה",
    "dollar_commission": "עמלת המרה",
    "commission_per_share": "עמלה ליחידה",
    "min_dollar_commission": "מינימום עמלה",
    "yearly_commission": "דמי ניהול שנתיים",
    "window": "מספר שנות ההשקעה",
    "max_years": "מספר שנות ההשקעה המרבי",
    "yearly_draw": "אחוז המשיכה השנתית",
    "base": "הסכום ההתחלתי",
}
# Sent as fractions but shown to users as percentages.
FRACTION_FIELDS = {"dollar_commission", "yearly_commission", "yearly_draw", "threshold"}


def _label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


def _limit(name: str, value: float) -> str:
    if name in FRACTION_FIELDS:
        return f"{value * 100:g}%"
    return f"{value:g}"


@lru_cache(maxsize=1)
def _data():
    return load_data()


def _parse_bool(raw: str, name: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ApiValidationError(f"{_label(name)}: הערך צריך להיות כן או לא")


def _parse_int(raw: str, name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiValidationError(f"{_label(name)}: צריך להזין מספר שלם") from exc
    if minimum is not None and value < minimum:
        raise ApiValidationError(f"{_label(name)}: הערך המינימלי הוא {_limit(name, minimum)}")
    if maximum is not None and value > maximum:
        raise ApiValidationError(f"{_label(name)}: הערך המרבי הוא {_limit(name, maximum)}")
    return value


def _parse_float(raw: str, name: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ApiValidationError(f"{_label(name)}: צריך להזין מספר") from exc
    if not math.isfinite(value):
        raise ApiValidationError(f"{_label(name)}: צריך להזין מספר")
    if minimum is not None and value < minimum:
        raise ApiValidationError(f"{_label(name)}: הערך המינימלי הוא {_limit(name, minimum)}")
    if maximum is not None and value > maximum:
        raise ApiValidationError(f"{_label(name)}: הערך המרבי הוא {_limit(name, maximum)}")
    return value


def _parse_date(raw: str, name: str) -> str:
    try:
        value = pd.Timestamp(raw)
    except ValueError as exc:
        raise ApiValidationError(f"{_label(name)}: התאריך לא תקין") from exc
    if pd.isna(value):
        raise ApiValidationError(f"{_label(name)}: התאריך לא תקין")
    return value.strftime("%Y-%m-%d")


def _parse_float_list(values: list[str], name: str) -> tuple[float, ...]:
    parsed: list[float] = []
    for raw in values:
        parts = [part.strip() for part in raw.split(",")]
        parsed.extend(_parse_float(part, name, minimum=0) for part in parts if part)
    if not parsed:
        raise ApiValidationError(f"{_label(name)}: צריך לבחור לפחות ערך אחד")
    return tuple(parsed)


def _parse_portfolios(values: list[str], name: str) -> tuple[str, ...]:
    parsed: list[str] = []
    for raw in values:
        parsed.extend(part.strip() for part in raw.split(",") if part.strip())
    if not parsed:
        raise ApiValidationError(f"{_label(name)}: צריך לבחור לפחות ערך אחד")

    parsed = [PORTFOLIO_ALIASES.get(portfolio, portfolio) for portfolio in parsed]
    valid = set(_data().lazy_return_portfolios)
    unknown = [portfolio for portfolio in parsed if portfolio not in valid]
    if unknown:
        raise ApiValidationError(f"תיק לא מוכר: {unknown[0]}")
    return tuple(parsed)


def _get_bool(args: Mapping[str, str], name: str, default: bool) -> bool:
    return _parse_bool(args[name], name) if name in args else default


def _get_int(args: Mapping[str, str], name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    return _parse_int(args[name], name, minimum=minimum, maximum=maximum) if name in args else default


def _get_float(
    args: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    return _parse_float(args[name], name, minimum=minimum, maximum=maximum) if name in args else default


def _get_date(args: Mapping[str, str], name: str, default: str) -> str:
    return _parse_date(args[name], name) if name in args else default


def _reject_unknown(args: Mapping[str, str], allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    unknown = sorted(key for key in args if key not in allowed_set)
    if unknown:
        raise ApiValidationError(f"פרמטר לא מוכר: {unknown[0]}")


def _normalize_common_dates(params: JsonDict, *, start_key: str = "start", end_key: str = "end") -> None:
    if pd.Timestamp(params[start_key]) > pd.Timestamp(params[end_key]):
        raise ApiValidationError("תאריך ההתחלה צריך להיות לפני תאריך הסיום")


def _parse_tax_args(args) -> Params:
    _reject_unknown(args, {"start", "end", "adjust_cpi", "initial"})
    params: JsonDict = {
        "start": _get_date(args, "start", calc.DEFAULT_TAX_START),
        "end": _get_date(args, "end", calc.DEFAULT_TAX_END),
        "adjust_cpi": _get_bool(args, "adjust_cpi", True),
        "initial": _get_float(args, "initial", 1.0, minimum=0),
    }
    _normalize_common_dates(params)
    return _freeze(params)


def _parse_commission_args(args) -> Params:
    _reject_unknown(args, {"start", "end", "adjust_cpi", "commissions", "initial"})
    params = {
        "start": _get_date(args, "start", calc.DEFAULT_TAX_START),
        "end": _get_date(args, "end", calc.DEFAULT_TAX_END),
        "adjust_cpi": _get_bool(args, "adjust_cpi", True),
        "initial": _get_float(args, "initial", 1.0, minimum=0),
    }
    _normalize_common_dates(params)
    params["commissions"] = (
        _parse_float_list(args.getlist("commissions"), "commissions")
        if "commissions" in args
        else tuple(calc.DEFAULT_COMMISSIONS)
    )
    return _freeze(params)


def _parse_risk_ladder_args(args) -> Params:
    _reject_unknown(args, {"start", "end"})
    params = {
        "start": _get_date(args, "start", "1871-01-01"),
        "end": _get_date(args, "end", "2026-01-01"),
    }
    _normalize_common_dates(params)
    return _freeze(params)


def _parse_sp500_risk_args(args) -> Params:
    _reject_unknown(args, {"years", "threshold", "start", "end"})
    params = {
        "start": _get_date(args, "start", "1871-01-01"),
        "end": _get_date(args, "end", "2026-01-01"),
        "years": _get_int(args, "years", 15, minimum=1, maximum=100),
        "threshold": _get_float(args, "threshold", 0.04, minimum=-1, maximum=1),
    }
    _normalize_common_dates(params)
    return _freeze(params)


def _parse_portfolio_args(args) -> Params:
    _reject_unknown(args, {"portfolios", "year_start", "year_end", "commission_adjusted", "value_mode", "rolling_window", "full_history_rolling", "common_period"})
    value_mode = args.get("value_mode", "cpi_il")
    if value_mode not in {"cpi_il", "cpi_us", "nominal"}:
        raise ApiValidationError("סוג התקנון למדד לא מוכר")
    params: JsonDict = {
        "portfolios": (
            _parse_portfolios(args.getlist("portfolios"), "portfolios")
            if "portfolios" in args
            else tuple(calc.DEFAULT_PORTFOLIOS)
        ),
        "year_start": _get_int(args, "year_start", 1955, minimum=1871, maximum=2025),
        "year_end": _get_int(args, "year_end", 2025, minimum=1871, maximum=2025),
        "commission_adjusted": _get_bool(args, "commission_adjusted", True),
        "value_mode": value_mode,
        "rolling_window": _get_int(args, "rolling_window", 10, minimum=1, maximum=100) if "rolling_window" in args else None,
        "full_history_rolling": _get_bool(args, "full_history_rolling", False),
        "common_period": _get_bool(args, "common_period", False),
    }
    if params["year_start"] > params["year_end"]:
        raise ApiValidationError("שנת ההתחלה צריכה להיות לפני שנת הסיום")
    return _freeze(params)


def _parse_kupat_args(args) -> Params:
    _reject_unknown(
        args,
        {
            "age",
            "start_year",
            "end",
            "initial",
            "pension_months",
            "adjust_cpi",
            "kh_buy_sell",
            "kh_annual_fee",
            "ph_buy_sell",
            "ph_annual_fee",
            "ii_buy_sell",
            "ii_annual_fee",
        },
    )
    return _freeze(
        {
            "age": _get_int(args, "age", calc.DEFAULT_KUPAT_AGE, minimum=18, maximum=100),
            "start_year": _get_int(args, "start_year", calc.DEFAULT_KUPAT_START_YEAR, minimum=1871, maximum=2026),
            "end": _get_date(args, "end", "2026-01-01"),
            "initial": _get_float(args, "initial", calc.DEFAULT_KUPAT_INITIAL, minimum=0),
            "pension_months": _get_int(args, "pension_months", calc.DEFAULT_KUPAT_PENSION_MONTHS, minimum=1, maximum=1200),
            "adjust_cpi": _get_bool(args, "adjust_cpi", True),
            "kh_buy_sell": _get_float(args, "kh_buy_sell", 0.0, minimum=0, maximum=100),
            "kh_annual_fee": _get_float(args, "kh_annual_fee", 0.65, minimum=0, maximum=100),
            "ph_buy_sell": _get_float(args, "ph_buy_sell", 0.0, minimum=0, maximum=100),
            "ph_annual_fee": _get_float(args, "ph_annual_fee", 0.75, minimum=0, maximum=100),
            "ii_buy_sell": _get_float(args, "ii_buy_sell", 0.07, minimum=0, maximum=100),
            "ii_annual_fee": _get_float(args, "ii_annual_fee", 0.07, minimum=0, maximum=100),
        }
    )


def _parse_independent_args(args) -> Params:
    allowed = {
        "start",
        "end",
        "initial",
        "share_price",
        "dollar_commission",
        "commission_per_share",
        "min_dollar_commission",
        "yearly_commission",
    }
    _reject_unknown(args, allowed)
    params: JsonDict = {
        "start": _get_date(args, "start", calc.DEFAULT_INDEPENDENT_START),
        "end": _get_date(args, "end", calc.DEFAULT_INDEPENDENT_END),
        "initial": _get_float(args, "initial", 100000, minimum=0),
        "share_price": _get_float(args, "share_price", 50, minimum=0.01),
        "dollar_commission": _get_float(args, "dollar_commission", 0.005, minimum=0, maximum=1),
        "commission_per_share": _get_float(args, "commission_per_share", 0.01, minimum=0),
        "min_dollar_commission": _get_float(args, "min_dollar_commission", 7.5, minimum=0),
        "yearly_commission": _get_float(args, "yearly_commission", 0.003, minimum=0, maximum=1),
    }
    _normalize_common_dates(params)
    return _freeze(params)


def _parse_scv_rolling_args(args) -> Params:
    _reject_unknown(args, {"window", "year_end"})
    params: JsonDict = {"window": _get_int(args, "window", 15, minimum=1, maximum=100)}
    if "year_end" in args:
        params["year_end"] = _get_int(args, "year_end", 2025, minimum=1871, maximum=2025)
    return _freeze(params)


def _parse_heatmap_args(args) -> Params:
    _reject_unknown(args, {"max_years", "year_end"})
    params: JsonDict = {"max_years": _get_int(args, "max_years", 20, minimum=1, maximum=100)}
    if "year_end" in args:
        params["year_end"] = _get_int(args, "year_end", 2025, minimum=1871, maximum=2025)
    return _freeze(params)


def _parse_trinity_args(args) -> Params:
    _reject_unknown(args, {"portfolio", "yearly_draw", "years", "base", "year_end", "value_mode"})
    portfolio = args.get("portfolio", calc.DEFAULT_TRINITY_PORTFOLIO).strip()
    portfolio = PORTFOLIO_ALIASES.get(portfolio, portfolio)
    if portfolio not in set(_data().lazy_return_portfolios):
        raise ApiValidationError(f"תיק לא מוכר: {portfolio}")
    params: JsonDict = {
        "portfolio": portfolio,
        "yearly_draw": _get_float(args, "yearly_draw", calc.DEFAULT_TRINITY_DRAW, minimum=0, maximum=1),
        "years": _get_int(args, "years", calc.DEFAULT_TRINITY_YEARS, minimum=1, maximum=100),
        "base": _get_float(args, "base", calc.DEFAULT_TRINITY_BASE, minimum=0),
        "value_mode": args.get("value_mode", "cpi_us"),
    }
    if params["value_mode"] not in {"cpi_us", "cpi_il"}:
        raise ApiValidationError("בסיס החישוב לא מוכר")
    if "year_end" in args:
        params["year_end"] = _get_int(args, "year_end", 2025, minimum=1871, maximum=2025)
    return _freeze(params)


def _parse_affordability_args(args) -> Params:
    _reject_unknown(args, {"equity", "income", "rate", "years", "ltv", "pti", "costs", "drop"})
    params: JsonDict = {
        "equity": _get_float(args, "equity", calc.DEFAULT_AFFORD_EQUITY, minimum=1000, maximum=1e8),
        "income": _get_float(args, "income", calc.DEFAULT_AFFORD_INCOME, minimum=0, maximum=1e7),
        "rate": _get_float(args, "rate", calc.DEFAULT_AFFORD_RATE, minimum=0, maximum=0.3),
        "years": _get_int(args, "years", calc.DEFAULT_AFFORD_YEARS, minimum=1, maximum=40),
        "ltv": _get_float(args, "ltv", calc.DEFAULT_AFFORD_LTV, minimum=0.05, maximum=0.95),
        "pti": _get_float(args, "pti", calc.DEFAULT_AFFORD_PTI, minimum=0.05, maximum=0.7),
        "costs": _get_float(args, "costs", calc.DEFAULT_AFFORD_COSTS, minimum=0, maximum=0.2),
        "drop": _get_float(args, "drop", calc.DEFAULT_AFFORD_DROP, minimum=0, maximum=0.9),
    }
    return _freeze(params)


def _parse_down_payment_args(args) -> Params:
    _reject_unknown(args, {"years", "stock_share", "glide", "wait_years"})
    params: JsonDict = {
        "years": _get_int(args, "years", calc.DEFAULT_DOWN_YEARS, minimum=1, maximum=10),
        "stock_share": _get_float(args, "stock_share", calc.DEFAULT_DOWN_STOCKS, minimum=0, maximum=1),
        "glide": _get_bool(args, "glide", False),
        "wait_years": _get_int(args, "wait_years", calc.DEFAULT_DOWN_WAIT, minimum=0, maximum=3),
    }
    return _freeze(params)


def _parse_year_end_args(args) -> Params:
    _reject_unknown(args, {"year_end"})
    params: JsonDict = {}
    if "year_end" in args:
        params["year_end"] = _get_int(args, "year_end", 2025, minimum=1871, maximum=2025)
    return _freeze(params)


def _parse_global_args(args) -> Params:
    _reject_unknown(args, {"year_end", "global_mix"})
    params: JsonDict = {"global_mix": _get_bool(args, "global_mix", True)}
    if "year_end" in args:
        params["year_end"] = _get_int(args, "year_end", 2025, minimum=1871, maximum=2025)
    return _freeze(params)


def _parse_no_args(args) -> Params:
    _reject_unknown(args, set())
    return _freeze({})


def _freeze(params: Mapping[str, Any]) -> Params:
    return tuple(params.items())


def _thaw(params: Params) -> JsonDict:
    return dict(params)


def _json_value(value: Any) -> Any:
    if pd.isna(value) or (isinstance(value, (float, np.floating)) and not math.isfinite(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _frame_payload(frame: pd.DataFrame) -> JsonDict:
    columns = frame.columns.tolist()
    rows = []
    for record in frame.to_dict(orient="records"):
        rows.append({column: _json_value(record[column]) for column in columns})
    return {"columns": columns, "data": rows, "rows": len(rows)}


def _dispatch(name: str, params: Params) -> pd.DataFrame:
    data = _data()
    kwargs = _thaw(params)
    if name == "tax_events":
        return calc.tax_events(data=data, **kwargs)
    if name == "commission_effect":
        return calc.commission_effect(data=data, **kwargs)
    if name == "commission_tax":
        return calc.commission_tax_scenarios(data=data, **kwargs)
    if name == "sp500_risk":
        return calc.sp500_risk(data=data, **kwargs)
    if name == "sp500_risk_ladder":
        return calc.sp500_risk_ladder(data=data, **kwargs)
    if name == "portfolio_summary":
        kwargs.pop("rolling_window", None)
        kwargs.pop("full_history_rolling", None)
        return calc.portfolio_summary(data=data, **kwargs)
    if name == "portfolio_structure":
        return calc.portfolio_structure(data=data)
    if name == "portfolio_commissions":
        return calc.portfolio_commissions(data=data)
    if name == "kupat_gemel":
        return calc.kupat_gemel(data=data, with_pension=False, **kwargs)
    if name == "kupat_gemel_pension":
        return calc.kupat_gemel(data=data, with_pension=True, **kwargs)
    if name == "independent_commissions":
        return calc.independent_commissions(data=data, tax_mode="optional_tax", **kwargs)
    if name == "tax_us_vs_il":
        return calc.independent_commissions(data=data, tax_mode="us_vs_il", **kwargs)
    if name == "portfolio_over_time":
        return calc.portfolio_over_time(data=data, **kwargs)
    if name == "us_world_rolling":
        return calc.us_world_rolling(data=data, **kwargs)
    if name == "us_global_rolling":
        return calc.us_global_rolling(data=data, **kwargs)
    if name == "global_vs_sp500_heatmap":
        return calc.global_vs_sp500_heatmap(data=data, **kwargs)
    if name == "sp500_scv_rolling":
        return calc.sp500_scv_rolling(data=data, after_tax=False, **kwargs)
    if name == "sp500_scv_heatmap":
        return calc.sp500_scv_heatmap(data=data, **kwargs)
    if name == "sp500_scv_after_tax":
        return calc.sp500_scv_rolling(data=data, after_tax=True, **kwargs)
    if name == "trinity":
        return calc.trinity(data=data, **kwargs)
    if name == "affordability":
        return calc.affordability(**kwargs)
    if name == "down_payment":
        return calc.down_payment(data=data, housing=_housing(), **kwargs)
    if name == "down_payment_ladder":
        kwargs.pop("stock_share", None)
        return calc.down_payment_ladder(data=data, housing=_housing(), **kwargs)
    raise KeyError(name)


@lru_cache(maxsize=1)
def _housing() -> pd.DataFrame:
    return load_housing_monthly(DATA_DIR)


@lru_cache(maxsize=1)
def _data_version() -> str:
    return data_version()


def _result(name: str, params: Params) -> JsonDict:
    frame = _dispatch(name, params)
    return {**_frame_payload(frame), "metadata": result_metadata(name, _thaw(params), frame, _data_version())}


@lru_cache(maxsize=128)
def _cached_payload(name: str, params: Params) -> JsonDict:
    return _result(name, params)


def _payload(name: str, params: Params) -> JsonDict:
    if name in EXPENSIVE_ENDPOINTS:
        return _cached_payload(name, params)
    return _result(name, params)


PARSERS: dict[str, Callable[[Any], Params]] = {
    "tax_events": _parse_tax_args,
    "commission_effect": _parse_commission_args,
    "commission_tax": _parse_commission_args,
    "sp500_risk": _parse_sp500_risk_args,
    "sp500_risk_ladder": _parse_risk_ladder_args,
    "portfolio_summary": _parse_portfolio_args,
    "portfolio_structure": _parse_no_args,
    "portfolio_commissions": _parse_no_args,
    "kupat_gemel": _parse_kupat_args,
    "kupat_gemel_pension": _parse_kupat_args,
    "independent_commissions": _parse_independent_args,
    "tax_us_vs_il": _parse_independent_args,
    "portfolio_over_time": _parse_portfolio_args,
    "us_world_rolling": _parse_year_end_args,
    "us_global_rolling": _parse_global_args,
    "global_vs_sp500_heatmap": _parse_heatmap_args,
    "sp500_scv_rolling": _parse_scv_rolling_args,
    "sp500_scv_heatmap": _parse_heatmap_args,
    "sp500_scv_after_tax": _parse_scv_rolling_args,
    "trinity": _parse_trinity_args,
    "affordability": _parse_affordability_args,
    "down_payment": _parse_down_payment_args,
    "down_payment_ladder": _parse_down_payment_args,
}


COMPRESSIBLE_TYPES = ("application/json", "text/javascript", "application/javascript", "text/css", "text/html", "image/svg+xml")


def _compress_response(response):
    """Gzip text responses for clients that accept it (JSON tables and app.js shrink ~5-10x)."""

    if (
        response.status_code != 200
        or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
        or response.headers.get("Content-Encoding")
        or not response.mimetype
        or not response.mimetype.startswith(COMPRESSIBLE_TYPES)
    ):
        return response
    response.direct_passthrough = False
    data = response.get_data()
    if len(data) < 1024:
        return response
    response.set_data(gzip.compress(data, compresslevel=6))
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Vary"] = "Accept-Encoding"
    response.headers.pop("Accept-Ranges", None)
    etag, weak = response.get_etag()
    if etag:
        response.set_etag(f"{etag}-gzip", weak=weak)
    return response


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False
    # Static files are small; always revalidate (cheap 304s) so a deploy never
    # mixes an old index.html with new JavaScript modules.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.after_request(_compress_response)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.errorhandler(ApiValidationError)
    @app.errorhandler(calc.CalculationInputError)
    def validation_error(error: ApiValidationError):
        return jsonify({"error": str(error)}), 400

    @app.get("/api/status")
    def status():
        data = _data()
        return jsonify(
            {
                "status": "ok",
                "api": "invest",
                "calculation_version": calc.CALCULATION_VERSION,
                "endpoints": list(ENDPOINT_NAMES),
                "sources": "/api/sources",
                "data_objects": {
                    "LazyReturns1": len(data.LazyReturns1),
                    "PortfoliosStructure": len(data.PortfoliosStructure),
                    "SP500DIV": len(data.SP500DIV),
                    "SP500US": len(data.SP500US),
                    "US_Small_Cap_Value_Monthly": len(data.US_Small_Cap_Value_Monthly),
                },
            }
        )

    @app.get("/api/sources")
    def sources():
        sources_path = DATA_DIR / "sources.json"
        if not sources_path.exists():
            return jsonify({"error": "Source metadata is unavailable"}), 404
        return app.response_class(
            sources_path.read_text(encoding="utf-8"),
            mimetype="application/json",
        )

    @app.get("/api/<name>")
    def calculation_endpoint(name: str):
        if name not in ENDPOINT_NAMES:
            return jsonify({"error": "Unknown endpoint"}), 404
        params = PARSERS[name](request.args)
        response = {"endpoint": name, "params": _thaw(params), **_payload(name, params)}
        return jsonify(response)

    return app


app = create_app()
