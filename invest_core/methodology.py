"""Calculation provenance returned with every API result.

The rules themselves are documented in docs/methodology.md; this module only
describes a result: versions, periods, units, assumptions and data warnings.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

CALCULATION_VERSION = "2.0.0"
ROOT = Path(__file__).resolve().parents[1]
TAX_SOURCE = "https://www.gov.il/BlobFolder/policy/professional-directives-271125-1/he/IncomeTax_professional-directives-271125-1.pdf"
PENSION_SOURCE = "https://haotzarsheli.mof.gov.il/Subject/Pages/Provident-Fund.aspx"

MONEY_ENDPOINTS = {
    "tax_events", "commission_effect", "commission_tax", "kupat_gemel", "kupat_gemel_pension",
    "independent_commissions", "tax_us_vs_il", "trinity", "affordability",
    "cash_vehicles", "cash_vehicles_inflation", "pension_fees", "pension_fees_steps",
}
# Pure calculators: no historical data, so no data period or history warnings.
CALCULATOR_ENDPOINTS = {"affordability", "cash_vehicles", "cash_vehicles_inflation", "pension_fees", "pension_fees_steps"}
TAX_ENDPOINTS = {
    "tax_events", "commission_effect", "commission_tax", "kupat_gemel", "kupat_gemel_pension",
    "tax_us_vs_il", "sp500_scv_after_tax",
}
FEE_ENDPOINTS = {
    "commission_effect", "commission_tax", "kupat_gemel", "kupat_gemel_pension",
    "independent_commissions", "tax_us_vs_il",
}
USD_ENDPOINTS = {"sp500_risk", "sp500_risk_ladder", "us_world_rolling", "us_global_rolling", "global_vs_sp500_heatmap", "trinity"}
CATALOG_ENDPOINTS = {"portfolio_structure", "portfolio_commissions"}


def data_version() -> str:
    """Short SHA-256 of every Parquet file, so a result can be tied to its data."""

    digest = hashlib.sha256()
    for path in sorted((ROOT / "data").glob("*.parquet")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _period(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"start": None, "end": None}
    if "date" in frame:
        dates = pd.to_datetime(frame["date"])
        return {"start": dates.min().strftime("%Y-%m-%d"), "end": dates.max().strftime("%Y-%m-%d")}
    if {"FirstYear", "N"} <= set(frame.columns):
        return {"start": int(frame["FirstYear"].min()) - 1, "end": int((frame["FirstYear"] + frame["N"] - 1).max())}
    for first, last in (("start_year", "end_year"), ("StartYear", "EndYear")):
        if {first, last} <= set(frame.columns):
            return {"start": int(frame[first].min()), "end": int(frame[last].max())}
    if {"Year", "N", "Portfolio"} <= set(frame.columns):
        return {"start": int((frame["Year"] - frame["N"]).min()), "end": int(frame["Year"].max())}
    if "Year" in frame:
        return {"start": int(frame["Year"].min()), "end": int(frame["Year"].max())}
    if {"start", "buy"} <= set(frame.columns):
        return {"start": pd.to_datetime(frame["start"]).min().strftime("%Y-%m-%d"), "end": pd.to_datetime(frame["buy"]).max().strftime("%Y-%m-%d")}
    if {"peak", "low"} <= set(frame.columns):
        return {"start": pd.to_datetime(frame["peak"]).min().strftime("%Y-%m-%d"), "end": pd.to_datetime(frame["low"]).max().strftime("%Y-%m-%d")}
    return {"start": None, "end": None}


def _assumptions(name: str, params: dict) -> list[str]:
    if name == "affordability":
        buyer = params.get("buyer", "first")
        ltv = {"first": 0.75, "upgrade": 0.70, "investor": 0.50}.get(buyer, 0.75)
        tax = "8% מהשקל הראשון ו-10% מעל 6,055,070 ש\"ח (דירה נוספת)" if buyer == "investor" else "לפי המדרגות לדירה יחידה: פטור עד 1,978,745 ש\"ח, ואחר כך 3.5%, 5%, 8% ו-10% (המדרגות קפואות עד ינואר 2028)"
        return [
            "מחשבון לימודי, לא אישור עקרוני למשכנתא. הבנק בודק גם דירוג אשראי, התחייבויות, יציבות הכנסה ושמאות.",
            f"משכנתא עד {ltv:.0%} ממחיר הדירה (מגבלת בנק ישראל לסוג הרוכש), והחזר חודשי עד {params.get('pti', 0.35):.0%} מההכנסה נטו של משק הבית. בנק ישראל מתיר עד 50%, ובנקים בדרך כלל מחמירים.",
            "ריבית אחת לכל ההלוואה, לוח שפיצר, בלי הצמדה למדד. בפועל משכנתא מורכבת מכמה מסלולים.",
            f"מההון העצמי יוצאים קודם שיפוץ, ריהוט ומעבר ({params.get('renovation', 0):,.0f} ש\"ח), ואחר כך עלויות העסקה ({params.get('costs', 0.02):.0%} מהמחיר: עורך דין, תיווך, שמאי) ומס רכישה {tax}. מה שנשאר הוא החלק של המחיר שמעל המשכנתא.",
        ]
    if name in {"down_payment", "down_payment_ladder"}:
        stocks = (
            "מניות ישראליות: מדד מחיר, ולכן נוספה תשואת דיבידנד קבועה של 2.5% בשנה. דמי ניהול 0.1% בשנה."
            if params.get("market_index") == "israel"
            else "מניות: S&P 500 בשקלים, כולל דיבידנדים. דמי ניהול 0.1% בשנה."
        )
        cash = (
            "החלק הסולידי: צמוד למדד המחירים לצרכן, בלי ריבית."
            if params.get("cash_kind") == "linked"
            else "החלק הסולידי: קרן כספית, שמרוויחה את הריבית פחות 0.3% בשנה (לפני 1994 תשואת מק\"מ במקום ריבית בנק ישראל)."
        )
        return [
            "מודל לימודי; סכום חד-פעמי בהתחלה, בלי הפקדות נוספות. איזון חודשי לחלוקה שבחרתם, בלי עלות.",
            stocks,
            cash,
            "מס של 25% על הרווח הריאלי, פעם אחת בקנייה, בלי מס על האיזון (כמו בקופת גמל להשקעה). הפסד לא מקבל החזר.",
            "ערך הכסף מול מחירי הדירות: השווי אחרי מס חלקי השינוי במחירי הדירות. 100% פירושו שהכסף מספיק לאותה דירה כמו בהתחלה. כל חודש נמדד בסופו; מדד מחירי הדירות מבוסס על עסקאות של חודשיים, ולכן מאחר בכחודש.",
            "דחיית הקנייה: רק אם ביום המתוכנן התיק ירד ב-10% או יותר מהשיא שלו מאז ההתחלה. מחכים עד שהתיק חוזר לשיא, "
            "ולא יותר מהזמן שבחרתם. שכר הדירה בזמן ההמתנה לא נספר. אם הנתונים נגמרים באמצע ההמתנה, קונים בחודש האחרון שיש לו נתונים.",
        ]
    if name in {"pension_fees", "pension_fees_steps"}:
        return [
            "מחשבון לימודי. הכל בשקלים של היום: השכר עולה מעל האינפלציה בקצב שבחרתם, והתשואה היא מעל האינפלציה, לפני דמי ניהול, ובלי תנודות משנה לשנה.",
            {
                "age": "מסלול תלוי גיל: חלק המניות 53% עד גיל 50, 38% בגילי 50–60 ו-22% מגיל 60. תשואה מעל האינפלציה: 5% בשנה על המניות ו-2% על השאר, כלומר כ-3.6%, 3.1% ו-2.7%.",
                "sp500": "מסלול S&P 500: כל הכסף במניות, בתשואה של 5% בשנה מעל האינפלציה. בעבר ה-S&P 500 הרוויח יותר, אבל זו הערכה זהירה לטווח ארוך.",
                "bonds": "מסלול אג\"ח: בלי מניות, בתשואה של 2% בשנה מעל האינפלציה.",
                "fixed": f"תשואה קבועה של {params.get('real_return', 0.035):.1%} בשנה מעל האינפלציה, בכל הגילים.",
            }.get(params.get("track", "age"), ""),
            f"הפקדה חודשית של {params.get('contribution', 0.185):.1%} מהשכר ברוטו, בלי הפסקות (חופשת לידה, אבטלה, מעבר עבודה), ובלי תקרה על השכר המבוטח.",
            "דמי ניהול מההפקדה נלקחים מכל הפקדה; דמי ניהול מהצבירה נגבים מדי חודש, כך ששנה מורידה בדיוק את השיעור השנתי.",
            f"קצבה: הצבירה חלקי מקדם המרה של {params.get('coefficient', 200):.0f}. המקדם בפועל תלוי בגיל, במין, במסלול ובקרן. לא נכלל רכיב הביטוח (נכות ושארים), שעולה כסף ומקטין את החיסכון.",
            "ההשוואות: קרן ברירת מחדל לפי המכרז של 2021 (1% מההפקדה, 0.22% מהצבירה), והתקרה בחוק (6% ו-0.5%).",
        ]
    if name in {"cash_vehicles", "cash_vehicles_inflation"}:
        return [
            "מחשבון לימודי עם ריבית ואינפלציה קבועות לכל התקופה. בפועל שתיהן משתנות.",
            "קרן כספית וקופת גמל להשקעה במסלול כספי: הריבית פחות דמי הניהול, ומס של 25% על הרווח הריאלי (מעל האינפלציה) פעם אחת במשיכה. הפסד ריאלי לא מקבל החזר.",
            "פיקדון בנקאי ומק\"מ: הריבית פחות הפער או העמלה, ומס של 15% על הריבית הנומינלית, שמשולם בכל שנה כשהפיקדון או המק\"מ נפדים ומתחדשים.",
            "מק\"מ שנקנה ישירות ממוסה כמו כל אג\"ח שקלית לא צמודה: 15% על הריבית הנומינלית.",
            "בלי מס רווח הון על קופת הגמל אם הכסף נשאר בה עד גיל 60 ונמשך כקצבה. כאן מניחים שהוא נמשך לדירה.",
        ]
    if name in {"homes_vs_stocks", "homes_vs_stocks_episodes"}:
        real = "חלקי מדד המחירים לצרכן, כלומר במונחים ריאליים" if params.get("real", True) else "נומינליים, בלי תקנון למדד"
        return [
            f"כל הסדרות {real}. 1 בחודש הראשון.",
            "מדד מחירי הדירות מבוסס על עסקאות של חודשיים, ולכן מאחר בכחודש. כל חודש נמדד בסופו.",
            "S&P 500 בשקלים כולל דיבידנדים; מניות תל אביב הן מדד מחיר, בלי דיבידנדים, ולכן הן נראות כאן חלשות מעט ממה שהיו בפועל.",
            "נפילה: ירידה של 20% לפחות משיא, עד הנקודה הנמוכה לפני שהשיא חוזר. \"אחרי\": 24 החודשים שאחרי הנקודה הנמוכה.",
        ]
    items = ["מודל לימודי; ללא הפקדות נוספות או התאמה למצב אישי."]
    if name in TAX_ENDPOINTS:
        items.append("מס מודל של 25% על הרווח הריאלי; הפסד אינו מוחזר אלא מקוזז מרווחים מאוחרים יותר.")
    if name in {"tax_events", "commission_effect", "commission_tax"}:
        items.append("מימוש מלא בכל אירוע ובסיס עלות חדש לתמורה נטו. כל נקודה מראה מה היה נשאר אחרי מכירה מלאה באותו מועד.")
    if name.startswith("kupat_gemel"):
        items.append("כל החלופות מחזיקות אותה חשיפה. בגיל 60 הקופה הופכת לקצבה פטורה ממס; משיכה חד-פעמית הייתה חייבת במס על הרווח.")
    if name == "kupat_gemel_pension":
        items.append("הקצבה מחושבת לפי מקדם קבוע, ללא תמחור ביטוחי. התיק העצמאי נעצר באפס, והחוסר מדווח.")
    if name == "trinity":
        items.append("משיכה בתחילת כל שנה, בסכום קבוע בכוח קנייה (לפי ההון ההתחלתי), מהשנה הראשונה כולל התשואה שלה. התיק נעצר באפס. לפני מס.")
    if name in {"portfolio_summary", "portfolio_over_time"}:
        if params.get("common_period"):
            items.append("כל התיקים נמדדים באותה תקופה: מהשנה הראשונה שיש בה נתונים לכולם.")
        else:
            items.append("כל תיק נמדד מהשנה הראשונה שיש לו נתונים, ולכן התקופות יכולות להיות שונות.")
        items.append("תנודתיות וירידות מחושבות מנתונים שנתיים, ולכן ירידות בתוך השנה נראות קטנות יותר.")
    return items


def _warnings(name: str, frame: pd.DataFrame, period: dict, params: dict) -> list[str]:
    if name in {"pension_fees", "pension_fees_steps"}:
        return ["דמי הניהול בקרנות ברירת המחדל נקבעים במכרז ומובטחים לתקופה מוגבלת. כדאי לבדוק את דמי הניהול שלכם בדוח השנתי או באתר הר הכסף."]
    if name in {"cash_vehicles", "cash_vehicles_inflation"}:
        return ["דמי הניהול, הפער בפיקדון וכללי המס משתנים בין גופים ולאורך זמן. כדאי לבדוק את ההצעה הספציפית שלכם, ואת דמי הניהול בפועל בקופה."]
    if name in CALCULATOR_ENDPOINTS:
        return ["הכללים והריביות משתנים מבנק לבנק ומשנה לשנה. כדאי לבדוק את המספרים שלכם מול הבנק או יועץ משכנתאות."]
    items = [
        "היסטוריה היא תיאור של העבר, ולא תחזית או הסתברות להצלחה בעתיד.",
        "הנתונים ההיסטוריים משלבים כמה מקורות ושחזורים; נתוני ישראל בתקופות המוקדמות אינם מאומתים במלואם.",
    ]
    if name in {"down_payment", "down_payment_ladder"}:
        items.append("הנתונים מתחילים ב-1986. תקופות חופפות, ולכן יש בהן רק מעט תקופות שונות באמת. הנתונים של 1986–1993 (מחירי דירות וריבית) משוחזרים ממקורות עקיפים, והם פחות מדויקים.")
        items.append("מדד מחירי הדירות מתאר דירה ממוצעת. דירה מסוימת, באזור מסוים, יכולה להתנהג אחרת.")
        return items
    if name in {"homes_vs_stocks", "homes_vs_stocks_episodes"}:
        items.append("מאז 1986 היו כשבעה משברים גדולים במניות. חלקם מופיעים פעמיים (S&P 500 ות\"א באותו משבר). זה מעט מדי כדי לקבוע כלל.")
        items.append("מדד מחירי הדירות מתאר דירה ממוצעת. דירה מסוימת, באזור מסוים, יכולה להתנהג אחרת.")
        return items
    monthly = "date" in frame or name == "sp500_risk_ladder"
    if not monthly and name not in CATALOG_ENDPOINTS:
        items.append("נתוני 2024–2025 נלקחו מאותו מדד או קרן כמו ההיסטוריה של כל סדרה ככל האפשר; לחלק מהסדרות יש תחליף.")
    if monthly and period["start"] and period["end"] and period["start"] <= "2025-11-01" <= period["end"]:
        items.append("מדד המחירים בארה״ב לאוקטובר 2025 לא פורסם (השבתת הממשל); הערך הוא ממוצע גאומטרי של ספטמבר ונובמבר.")
    requested = params.get("start")
    if monthly and requested and period["start"] and period["start"] > requested:
        items.append(f"הטווח מתחיל בפועל ב־{period['start']}, כי אין נתונים מלאים לפני כן. נתונים חסרים לא הושלמו.")
    return items


def result_metadata(name: str, params: dict, frame: pd.DataFrame, version: str) -> dict:
    period = _period(frame)
    catalog = name in CATALOG_ENDPOINTS
    mode = params.get("value_mode", "cpi_il")
    if catalog:
        currency, inflation = None, None
    else:
        usd = (name in USD_ENDPOINTS and not (name == "trinity" and mode == "cpi_il")) or (name.startswith("portfolio_") and mode != "cpi_il")
        currency = "USD" if usd else "ILS"
        if name in {"sp500_risk", "sp500_risk_ladder"} or (name == "trinity" and mode != "cpi_il") or (name.startswith("portfolio_") and mode == "cpi_us"):
            inflation = "US"
        elif name.startswith("homes_vs_stocks"):
            inflation = "IL" if params.get("real", True) else None
        elif name in {"us_world_rolling", "us_global_rolling", "global_vs_sp500_heatmap"} or name in CALCULATOR_ENDPOINTS or mode == "nominal":
            inflation = None
        else:
            inflation = "IL" if params.get("adjust_cpi", True) else None
    return {
        "calculation_version": CALCULATION_VERSION,
        "data_version": version,
        "result_period": period,
        "requested_period": {key: params[key] for key in ("start", "end", "year_start", "year_end") if key in params},
        "units": {
            "currency": currency,
            "value": "weights_or_fees" if catalog else "money" if name in MONEY_ENDPOINTS else "return_or_index",
            "inflation": inflation,
            "returns": "fraction",
        },
        "tax_included": name in TAX_ENDPOINTS,
        "fees_included": name in FEE_ENDPOINTS or bool(params.get("commission_adjusted", False)),
        "assumptions": _assumptions(name, params),
        "warnings": _warnings(name, frame, period, params),
        "quality": "mixed_historical_sources",
        "missing_values": int(frame.isna().sum().sum()),
        "sources_url": "api/sources",
        "series_coverage": [
            {"portfolio": str(row["Portfolio"]), "start": int(row["FirstYear"]) - 1, "end": int(row["FirstYear"] + row["N"] - 1)}
            for _, row in frame.iterrows()
        ] if name == "portfolio_summary" and not frame.empty else [],
        "legal_sources": [TAX_SOURCE, PENSION_SOURCE],
    }
