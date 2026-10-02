# Audit of numbers in the site text

Date: 2026-10-02. Code: `invest_core/calculations.py` v2.0.0 with the working-tree change that
replaces the 6-month tax scenario with 5- and 10-year scenarios (`REALIZATION_MONTHS = (1, 12, 60, 120)`).

Line numbers refer to `invest_api/static/app.js` as it was during the audit. Another session was
editing the file at the same time, so search by the key and the quoted fragment if a line has moved.

All values come from the Python API (`PYTHONPATH=. .venv/bin/python`, `load_data()`), using the
screen defaults from `app.js` and `invest_api/app.py`. Scripts are listed under each screen.

Flags:

* **SAME**: the text is still correct.
* **SMALL**: the number changed by less than 10% and the sentence means the same.
* **BIG**: the number changed by 10% or more. The sentence still points the same way.
* **MEANING**: the conclusion or direction of the sentence is no longer true, or the fact is wrong.

Notes:

* Some sentences say "30 years ago" or "after 30 years", but the screen default now runs from
  1993-01 to 2026-01, which is 33 years. The tables give both the 30-year window and the
  default window. The proposed wording follows the default window, so the text matches the chart.
* "Real" means divided by Israeli CPI (`adjust_cpi=true`, the UI default).

---

## 1. `tax-events` (למה לא)

Defaults: `initial=100000`, 1993-01-01 to 2026-01-01, `adjust_cpi=true`, no fee.
Call: `c.tax_events(d, initial=100000)`. The new scenarios come from `c._tax_ledger(value, cpi, every)`
with `every` = None, 1, 12, 60 and 120 on `c._monthly_window(d, start, end, ["value_ils","cpi_il"])`.

### Reference values (100,000 ILS, no fee)

| Scenario | Real 1993→2026 (33 y, default) | Nominal 1993→2026 | Real 1993→2023 (30 y) | Real 1996→2026 (30 y) |
| --- | ---: | ---: | ---: | ---: |
| No tax (gross, `v`) | 1,173,695 | 3,247,889 | 767,819 | 926,300 |
| Realize only at the end (`End25`) | **905,271** | 2,505,097 | 600,865 | 719,725 |
| Every 10 years (`Every120Months`) | **737,314** (−18.6% vs end) | 2,040,320 | 527,989 | 619,261 |
| Every 5 years (`Every60Months`) | **704,570** (−22.2%) | 1,949,710 | 504,542 | 592,777 |
| Every year (`Every12Months`) | **652,940** (−27.9%) | 1,806,839 | 457,817 | 546,300 |
| Every month (`EveryMonth`) | **624,690** (−31.0%) | 1,728,665 | 442,289 | 523,967 |
| (old) every 6 months | n/a | n/a | 450,704 | 537,259 |

### Claims

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L301 `stories["tax-events"].sections[0]` (למה כן) | "100,000 ש"ח בפוליסת חסכון ... יראה בחשבון אחרי מס כמליון שקלים" | ~1,000,000 | 1,186,534 (policy fee 0.7%); 1,103,789 (0.95%) | `commission_tax_scenarios`, 1996-01→2026-01, `adjust_cpi=False`, `tax_at_end` | BIG |
| L302 same | "באופן עצמאי יראה בחשבונו כ-1,500,000 ש"ח" | 1,500,000 | 1,371,283 (fee 0.2%); 1,423,885 (0.07%) | same | SMALL (−9%). The gap between the two shrinks from +50% to about +16–29%. |
| L335 `afterChart[0]` (ליאורה) | "כ-550,000 ש"ח אחרי 30 שנה, אחרי מס ותקנון למדד" | 550,000 | 600,865 for 30 y (1993→2023); **905,271** for the default 33 y | `End25` | SMALL for 30 y; BIG for the chart default |
| L336 `afterChart[1]` (ניר, every year) | "אחרי 30 שנה כ-350,000 ש"ח בלבד" | 350,000 | 457,817 (30 y); **652,940** (33 y) | `Every12Months` | BIG. The penalty for yearly realization falls from about −36% to −24% (30 y) or −28% (33 y). |
| L337 `afterChart[2]` | "מליון שקלים לפני 30 שנה ... מעל 3 מליון ... אחת לשנה" | >3M | 4.58M (1993→2023); 5.46M (1996→2026); **6.53M** (1993→2026) | ×10 of the rows above, real | BIG ("above 3M" is still true but far too low) |
| L337 same | "מי שלא נגע ... מעל 5 מליון" | >5M | 6.01M; 7.20M; **9.05M** | same | BIG |
| L335 same | "הסכום הנומינלי שצברה גדול יותר" | n/a | nominal 2,505,097 > real 905,271 | `adjust_cpi=False` | SAME |
| L837 `views[tax-events].takeaway` | "אפילו רק אחת לשנה, עלולים להקטין מאוד את התשואה" | qualitative | yearly −27.9% vs the end | above | SAME |
| L328 `sections[2]` | "(כן, אחת לשנה זה לעיתים תכופות)" | qualitative | yearly is −28%; every 5 y is −22%; every 10 y is −19% | above | SAME. Every 5 and 10 years also cost a lot. |

### Proposed wording

* L301–302 (30 years back from 2026 is 1996, nominal, fees 0.7% vs 0.2% as on the next screen):
  > מי שהשקיע לפני 30 שנה 100,000 ש"ח בפוליסת חסכון במסלול מחקה S&P 500 ויפדה אותם כעת, יראה בחשבון אחרי מס כ-1,200,000 שקלים.
  > לעומתו מי שהשקיע את אותו סכום באותו מסלול באופן עצמאי יראה בחשבונו כ-1,400,000 ש"ח. זה למה כן.

  The difference is now about 200,000 rather than 500,000. To keep a stronger contrast, use the
  author's own policy fee (0.95%, L371) against 0.07%: about 1,100,000 vs 1,400,000.
* L335 (match the 1993→2026 default):
  > אם ליאורה השקיעה 100,000 שקלים ב-1993 במחקה מושלם של S&P 500 צובר דיוידנדים, היא תמצא בחשבונה כ-900,000 ש"ח אחרי 33 שנה, אחרי מס ותקנון למדד, אם לא הזיזה את הכסף ממקומו. הסכום הנומינלי שצברה גדול יותר, אבל כאן מציגים כוח קנייה מעבר למדד.
* L336:
  > ניר, לעומתה, השקיע סכום זהה באותה שנה ובאותו נייר, אבל פעם בשנה הזיז את הכסף: הוציא, שילם מס רווחים, ומיד החזיר אותו לאותו מקום. ניר ימצא בחשבונו אחרי 33 שנה כ-650,000 ש"ח בלבד.

  Optional addition for the new lines:
  > גם מי שהזיז את הכסף רק פעם ב-5 שנים יגיע לכ-700,000 ש"ח, ופעם ב-10 שנים לכ-740,000 ש"ח. כל אירוע מס עולה כסף.
* L337:
  > מי שהשקיע מליון שקלים לפני 33 שנה בלי דמי ניהול יהיה בעלים של כ-6.5 מליון שקלים אם "ניהל" את הכסף אחת לשנה. מי שלא נגע בהשקעה יהיה הבעלים המאושר עוד יותר של מעל 9 מליון שקלים.

---

## 2. `commission-drag` (השפעת עמלות ומסים)

Defaults: `commissions=0,0.2,0.7`, `initial=100000`, 1993-01-01 to 2026-01-01, `adjust_cpi=true`.
Call: `c.commission_tax_scenarios(d, commissions=(...), initial=100000, adjust_cpi=...)`, last row of each fee.

| Fee | Real `tax_at_end` 1993→2026 | Real 1993→2023 | Nominal 1993→2026 | Nominal 1993→2023 |
| --- | ---: | ---: | ---: | ---: |
| 0% | 905,271 | 600,865 | 2,505,097 | 1,523,768 |
| 0.07% | 885,163 | 588,893 | 2,449,453 | 1,493,410 |
| 0.2% | **848,994** | 567,296 | **2,349,367** | 1,438,640 |
| 0.7% | **723,139** | 491,442 | 2,001,094 | 1,246,277 |
| 0.95% | 667,413 | 457,469 | 1,846,888 | 1,160,122 |

With a 0.7% fee, realizing every year leaves 545,374, every 5 y 584,760, every 10 y 606,308 and every month 523,676 (real, 1993→2026).

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L354 `afterChartByEndpoint.commission_effect[0]` | "דמי ניהול במסחר עצמאי יהיו כ-0.2% ... בפוליסת חסכון ... כ-0.7%" | 0.2% / 0.7% | Fact, not computed. A CSPX-type ETF costs 0.07% (used on L532 and in `fee_basis.json`). The kupat screen assumes 0.75% for policies. | n/a | Fact to check. 0.2% looks high for an S&P 500 ETF today. |
| L355 `commission_effect[1]` | "0.7% ... ב-1993 ... יותר מ-450,000 ש"ח לאחר מס ... ותקנון למדד" | >450,000 | **723,139** (to 2026); 491,442 (to 2023) | table | BIG for the chart default (SAME for 30 y) |
| L356 `commission_effect[2]` | "0.2% ... כ-550,000 ש"ח ... אחרי מס" | 550,000 | **848,994**; 567,296 | table | BIG (SMALL for 30 y) |
| L356 same | "ועם כ-1,300,000 ש"ח אם לא מתקננים למדד" | 1,300,000 | **2,349,367**; 1,438,640 | `adjust_cpi=False` | BIG (+11% even for 30 y) |
| L357 | "ההבדל עצום" | qualitative | 0.2% vs 0.7% = 125,855 real per 100,000 (2026) | table | SAME |
| L371 `commission_tax[6]` | "פוליסת חסכון עם דמי ניהול של 0.7% והוצאות ניהול השקעה של 0.25%. ביחד 0.95% ... יותר מברירת המחדל" | 0.95% > 0.7% | default is still 0.7% | `commissionsField()` | SAME (personal fact) |

### Proposed wording

* L355:
  > מי שהשאיר 100,000 ש"ח עם דמי ניהול של 0.7% לשנה ב-1993, כשהם צמודים למדד S&P 500 כולל השקעה מחודשת של מרבית הדיווידנדים, מצא עצמו ב-2026 עם יותר מ-700,000 ש"ח לאחר מס רווחי הון ולאחר תקנון למדד.
* L356:
  > לעומתו, מי שהשקיע באותו מחקה בדיוק עם דמי ניהול של 0.2% בלבד, יהיה עם כ-850,000 ש"ח בכיס אחרי מס רווחי הון, ועם כ-2,350,000 ש"ח אם לא מתקננים למדד.
* L354 (optional, if the self-managed level should match the rest of the site):
  > בפשטנות, דמי ניהול במסחר עצמאי יהיו כ-0.1%-0.2% ודמי הניהול בפוליסת חסכון, ובפרט לאחר תוספת "הוצאות ניהול השקעה", יהיו כ-0.7%.

---

## 3. `sp500-risk` (הסיכון)

Defaults: 1871-01-01 to 2026-01-01, `years=15`, `threshold=4%`. Call: `c.sp500_risk(d, years=Y, threshold=0.04, start=..., end=...)`.

| Window | Windows | Below 0 | Above 4% | Median | Worst (end date) |
| --- | ---: | ---: | ---: | ---: | --- |
| 10 y | 1741 | 11.0% | 74.0% | 7.0% | −5.9%/y (2009-03) |
| 15 y | 1681 | 4.4% | 74.5% | 6.9% | −2.1%/y (1920-12) |
| 20 y | 1621 | 0.06% | 78.0% | 6.8% | −0.2%/y (1921-06) |
| 30 y | 1501 | 0% | 94.8% | 6.8% | +1.9%/y |

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L392 `afterChart[0]` | "אפילו בסיום תקופה ארוכה כמו 15 שנים נגלה שבידנו פחות כסף" | possible | 4.4% of 15-year windows are below zero (ending 1920–22, 1944, 1979–84) | table | SAME |
| L393 `afterChart[1]` | "יחכה הרבה שנים, נניח 10, ולא ירוויח אפילו שקל" | possible | 11% of 10-year windows are below zero | table | SAME |
| L1013 `views[sp500-risk].chart.caption` and L3399 (chart renderer caption) | "השקעה מחדש של כ-85% מהדיבידנדים" | 85% | Only from 2011-02 (CSPX: 15% withholding plus 0.07% fee, and 2024–2025 are adjusted the same way). Before 2011 the series is Shiller with 100% of dividends. | `docs/data_audit_findings.md` L235, `methodology.md` L97 | SMALL (fact) |

### Proposed wording

* L1013 / L3399:
  > נתוני S&P 500 כולל השקעה מחדש של הדיבידנדים (מ-2011 בניכוי מס מקור של 15%, כ-85% מהדיבידנדים) ...

---

## 4. `kupat-gemel` (קופת גמל להשקעה)

Defaults: age 40, start 1995, 70,000, pension_months 250, CPI on, fees KH 0/0.65, PH 0/0.75, II 0.07/0.07, end 2026-01-01.
Call: `c.kupat_gemel(d, end="2026-01-01")` and `c.kupat_gemel(d, with_pension=True, end="2026-01-01")`.

Values are real ILS at the start date. At 60 (2015-01): KH 274,795, PH 219,487, II 248,718. Just before 60: KH 221,641.
At 71 (2026-01, end of data): KH 274,795 (converted, CPI-linked), PH 518,982, II 636,334.
Pension: annuity of 1,099 a month (real), 145,092 received in total by 71. IIb, which pays the same net annuity from II, still holds **383,193**
at 71 with no shortfall.

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L416 `paragraphs[1]` | "אוכל למשוך קצבה גדולה יותר וגם להשאיר יותר כסף בהשקעה עצמאית" | claim | True to the end of the data. An annuity 1.5× the fund's leaves 256,623 at 71 with no shortfall (my script: `_self_managed_pension` with payments ×1.0–1.5). The data ends at 71, so later ages are not tested. | script | SAME |
| L422 `kupat_gemel[0]` | "פוליסת חסכון ... ובסוף פחות כסף בכיס" | claim | PH < II at 60 and at 71 (519k vs 636k) | above | SAME |
| L423 `kupat_gemel[1]` | "בהגעה לגיל 60, הטבת המס ... משמעותית מאוד" | claim | KH jumps from 221,641 to 274,795 (+24%) and passes II (248,718) | above | SAME |
| L429 `kupat_gemel_pension[2]` | "במקרים רבים אפשר לקבל קצבה שקולה ... ועדיין להשאר עם כסף נוסף" | claim | IIb is 383,193 at 71 | above | SAME |

No changes needed.

---

## 5. `us-world` (אמריקה)

Calls: `c.us_global_rolling(d, global_mix=False/True)`, `c.global_vs_sp500_heatmap(d, max_years=20)`,
`c._us_world_levels(d, True, None)` and `c.portfolio_summary(d, ["S&P 500","Global"], 1980, 2025, True, "cpi_il")`.

Share of windows (ending 1974–2025) where S&P 500 leads:

| Comparison | 5 y | 10 y | 15 y |
| --- | ---: | ---: | ---: |
| vs MSCI World ex USA | 31/52 (60%) | 27/47 (57%) | 31/42 (74%) |
| vs 60/40 global | 31/52 (60%) | **22/47 (47%)** | 28/42 (67%) |

15-year windows where ex-US led: ending 1984–1991, 1994, 2012 and 2013.
Heatmap (all cells up to 20 y): S&P better in 61% of 930 cells. By length: 1 y 30/56, 5 y 31/52, 10 y 22/47, 15 y 28/42, 20 y 29/37.
Annual: positive years S&P 45/56 vs 60/40 42/56. Worst year S&P −36.5% vs 60/40 −39.2%.
1980–2025, real ILS, after fees: S&P CAGR 8.45% with SD 15.8%; Global (60/40) 7.36% with SD 14.8%; MSCI ex US 5.23% with SD 17.0%. Underwater years: 13, 13 and 16.
40-year CAGR gap S&P minus MSCI World ex USA (nominal USD): 2.6 pp ending 2022, 3.3 pp ending 2025.

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L1109 `panels[0].intro[0]` | "שוק המניות האמריקאי מהווה ... כ 60% משוק המניות העולמי" | 60% | Fact, not in the data. The US share of MSCI ACWI has been about 62–65% in 2024–2026. | n/a | Fact. Suggest "כ-60%-65%". |
| L522 `us_world_rolling[0]` and L1113 `panels[0].intro[4]` | "בממוצע נע על 15 שנים התמונה נראית שונה לחלוטין. יש עדיפות ברורה" | clear US lead | 74% of 15-year windows (60% at 5 y). Ex-US led in every 15-year window ending 1984–1991. | table | SAME. "שונה לחלוטין" overstates a change from 60% to 74%. |
| L1198 `panels[2].intro[0]` (60/40) | "יש יותר שנים בהם השקעה רק באמריקה הייתה מוצלחת יותר ... אפילו אם מדובר בטווח של 5 שנים בלבד" | US leads in more years | True at 5 y (60%) and 15 y (67%). **False at 10 y: 60/40 led in 25 of 47 windows.** | table | MEANING (10-year window) |
| L530 `portfolio_over_time[2]` | "השילוב (60/40) ... תשואה ממוצעת דומה וגם סטיית תקן דומה" | similar | 7.4% vs 8.5% CAGR; SD 14.8% vs 15.8% | `portfolio_summary` | SAME |
| L532 `portfolio_over_time[4]` | "במקום 0.07% ... S&P 500 דמי ניהול של 0.2% לנייר שמחקה את המדד הגלובלי" | 0.07% / 0.2% | The data assumes 0.07% for S&P 500 and 0.162% for the 60/40 mix (0.07% and 0.30%) | `PortfoliosStructure.commission_i` | SAME (fact) |
| L533 `portfolio_over_time[5]` | "מניות ערך קטנות ... תשואה גבוהה יותר עם מספר שנות שפל מרבי קטן יותר" | yes | 1955–2025 real ILS: SCV 10.7% with 10 underwater years; S&P 7.2% with 14 | `portfolio_summary` defaults | SAME |
| L535 `portfolio_over_time[7]` | "ארה"ב הובילה על העולם המפותח ב-2% בממוצע לשנה ב 40 השנים האחרונות" | 2% (quoted from the discussion) | Our data: 2.6 pp (40 y to 2022), 3.3 pp (to 2025) | `_us_world_levels` | BIG, but it is a quote. Leave it, or add our figure. |
| L541 `global_vs_sp500_heatmap[0]` | "במרבית השנים השקעה רק בארה"ב הייתה הבחירה העדיפה" | most | 61% of cells | heatmap | SAME |
| L542 `global_vs_sp500_heatmap[1]` | "האיזון ... לא הוביל בעבר ליותר שנים של תשואה חיובית ... לא סיפק יותר הגנה מנפילות" | claim | Positive years 45 (S&P) vs 42 (60/40). Worst year −36.5% vs −39.2%. | annual levels | SAME |
| L1133, L1164 `captionLines` | "נתוני MSCI World ex USA מתוך upmyinterest לשנים 1970–2025" | 1970–2025 | Data runs 1970–2025, but 2024–2025 now come from the MSCI factsheet (gross), not upmyinterest | `data_corrections.json` | SMALL (source) |

### Proposed wording

* L1198:
  > לא ממש משנה את התמונה. כיוון שרוב ההשקעה (60%) זהה ובאמריקה - ההבדלים קטנים יותר. אך בנתוני העבר אין יתרון ברור להשקעה מאוזנת בין ארה"ב לשאר העולם. בחלונות של 5 ושל 15 שנים יש יותר שנים בהם השקעה רק באמריקה הייתה מוצלחת יותר מהשקעה גלובלית; בחלון של 10 שנים התמונה כמעט מאוזנת.
* L522 / L1113 (optional, softer and with the figure):
  > בממוצע נע על 15 שנים התמונה נראית שונה: ב-31 מתוך 42 התקופות S&P 500 הוביל. יש עדיפות ברורה להשקעה במניות אמריקאיות על פני שאר העולם המפותח.
* L1109:
  > שוק המניות האמריקאי מהווה, בשווי שוק, כ-60%-65% משוק המניות העולמי ...
* L535 (optional addition after the quote):
  > (בנתונים כאן הפער ב-40 השנים עד 2025 אף גבוה יותר: כ-3.3% לשנה.)
* Captions L1133/L1164: "לשנים 1970–2023, ו-2024–2025 מתוך דף המדד של MSCI".

---

## 6. `scv` (מניות ערך קטנות)

Calls: `c.sp500_scv_rolling(d, window=W, after_tax=False/True)`, `c.sp500_scv_heatmap(d, max_years=20)`,
`c.portfolio_over_time(d, ["S&P 500","US Small Cap Value"], 1969, 2025, False, "cpi_il", 15, True)`.

Pre-tax rolling CAGR, real ILS, ending 1969–2025. SCV leads in 31/57 one-year windows, 44/57 ten-year windows (77%) and 49/57 fifteen-year windows (86%).
S&P led the 15-year windows ending 1998–2000, 2019–2021 and 2024–2025.
After tax (15 y): SCV leads 49/57 (86%). The median after-tax CAGR is 9.3% for SCV and 5.2% for S&P. At 10 y: 42/57.
Heatmap: SCV better in 75% of 1,290 cells. By length: 1 y 55%, 5 y 61%, 10 y 77%, 15 y 87%, 20 y 96%.
1969–2025 cumulative real: S&P ×32.4, SCV ×152.2.

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L557 `portfolio_over_time[0]` | "התשואה שלהן היסטורית הייתה משמעותית גבוהה יותר" | claim | 9.2% vs 6.3% real CAGR 1969–2025 | `portfolio_summary` 1969, no fee | SAME |
| L560 `portfolio_over_time[1]` | "ההבדל בין 10% ל-13% ... עוד 3% בשנה" | illustration | Real ILS 1955–2025: 7.2% vs 10.7% (gap 3.5 pp). From 1952: 9.1% vs 12.6%. | `portfolio_summary` | SAME (works as an illustration) |
| L581 `sp500_scv_rolling[1]` | "יש רצפים שבהם S&P 500 מוביל" | claim | 15-year windows ending 1998–2000, 2019–2021, 2024–2025 | above | SAME |
| L586–588 `sp500_scv_heatmap[4]` | "מופיע בהרבה חלונות זמן, ובמיוחד ככל שאופק ההשקעה מתארך" | claim | 55% at 1 y up to 96% at 20 y | above | SAME |
| L596 `sp500_scv_after_tax[3]` | "גם אחרי שמענישים את SCV במיסוי ... מבטיחה מאוד ברוב התקופות" | claim | 86% of 15-year windows | above | SAME |
| L745 `stories.about` sources list | "MSCI USA Small Cap Value Weighted: מקור עדכון SCV לשנים 2024 ו-2025" | MSCI | **Now upmyinterest (8.8% and 10.7%), the same provider as 1928–2023** | `methodology.md` L106 | MEANING (source changed) |

### Proposed wording

* L745 (About, sources):
  > [Up My Interest - US Small Cap Value](https://www.upmyinterest.com/): מקור עדכון SCV לשנים 2024 ו-2025 (8.8% ו-10.7%), אותו מקור כמו ההיסטוריה. קרנות כמו USSC/ZPRV מוזכרות בטאב ה-SCV כדוגמה לחשיפה מעשית בלבד.

---

## 7. `portfolio-summary` (lazy portfolios)

Call: `c.portfolio_summary(d, c.DEFAULT_PORTFOLIOS, 1955, 2025, True, "cpi_il")`.
CAGR: SCV 10.7%, Mid Cap Value 8.0%, S&P 500 7.2%, five-factor 6.9%, השילוש הקדוש 6.7%, Bogleheads 5.7%, Bernstein and Coffeehouse 5.5%, Swensen 4.2–4.5%, Conservative 3.9%, All Seasons 3.1%.

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L1951 `renderLazyPortfolioShell` | "רוב התיקים העצלים לא מקנים יתרון משמעותי על תיקים מאוד פשוטים" | claim | No composite beats S&P 500 on CAGR. The fix that made "Global ex US" truly ex-US lowered the composites further. | above | SAME |

Side note (not text): the default list still says "Precious Metals". The data renamed it "Gold Miners", and the API accepts both names.

---

## 8. `trinity`

Defaults (UI and API): **portfolio "S&P 500"**, 4%, 30 years, base 4,000,000. Call: `c.trinity(d, portfolio=P)`.

| Portfolio | Periods | Start years | Ran out | Ended above 4M | 1993→2022 end | Median end |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| S&P 500 (default) | 68 | 1929–1996 | 5: 1929, 1930, 1966, 1968, 1969 | 55 (81%) | 14.8M | 15.8M |
| US Small Cap Value | 68 | 1929–1996 | 2: 1929, 1930 | 65 (96%) | 49.2M | 56.1M |

Total withdrawn over 30 years: 30 × 160,000 = 4.8M. The monthly withdrawal is 13,333.

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L663 `afterChart[0].list[0]` | "ברירת המחדל כאן, למשל, היא במניות ערך קטנות" | SCV | The UI and API default is **S&P 500** | `views[trinity].controls`, `DEFAULT_TRINITY_PORTFOLIO` | MEANING |
| L664 | "4,000,000 עימם הגענו לגיל פרישה" | 4,000,000 | 4,000,000 | default | SAME |
| L667 `list[4]` | "אם 4% הם 10,000 שקלים" | 10,000 | Example only. At the default 4M, 4% is 13,333 a month. | 4M × 4% / 12 | SAME as an example (see L682) |
| L679 `paragraphsAfter[0]` | "בשנת 2022 לאחר 30 שנים ... מניות ערך קטנות ... כמעט 50 מליון" | ~50M | 49.2M (SCV); 14.8M with the default S&P 500 | `trinity(portfolio="US Small Cap Value")`, end_year 2022 | SAME for SCV |
| L680 | "בסכום מצטבר של כמעט 5 מליון" | ~5M | 4.8M | 30 × 160k | SAME |
| L681 | "בנתוני ברירת המחדל ... שני מקרים מתוך 65 ... 1928 וב 1929" | 2 of 65; 1928, 1929 | SCV: **2 of 68; 1929 and 1930**. Default S&P 500: **5 of 68**. | above | BIG (SCV); MEANING (default) |
| L682 | "ב 95% מהמקרים יוותר ... יותר כסף משהיה לנו בהתחלה, למרות משיכה של 10,000 בחודש" | 95%; 10,000 | SCV 96%; S&P 81%. Monthly is 13,333. | above | SMALL (SCV) / MEANING (default); BIG (10,000 → 13,333) |
| L689 `afterChart[2]` | "ברירת המחדל היא 100% במניות ערך קטנות" | SCV | S&P 500 | as above | MEANING |

### Proposed wording

The simplest fix is to change the Trinity default to `"US Small Cap Value"` in `views[trinity].controls`
(and optionally `DEFAULT_TRINITY_PORTFOLIO`). Then only these numbers need to change:

* L681:
  > בנתוני ברירת המחדל, למשל, מדובר בשני מקרים מתוך 68 אפשרויות של השקעה בת 30 שנים. שני המקרים הם התחלת השקעה ב-1929 וב-1930, אגב.
* L682:
  > עוד רואים שב-96% מהמקרים יוותר לנו, לירושה, יותר כסף משהיה לנו בהתחלה, למרות משיכה של כ-13,000 בחודש לאורך 30 שנה.

If the default stays S&P 500:

* L663: "במה הכסף מושקע? ברירת המחדל כאן היא S&P 500, אבל שווה לנסות גם מניות ערך קטנות."
* L679: "כך למשל מי שמשך את כספו בשנת 2022 לאחר 30 שנים של השקעה במניות ערך קטנות (בחרו US Small Cap Value) ..." (49M and 4.8M unchanged).
* L681: "בנתוני ברירת המחדל (S&P 500), למשל, מדובר בחמישה מקרים מתוך 68 אפשרויות של השקעה בת 30 שנים: התחלה ב-1929, 1930, 1966, 1968 ו-1969. במניות ערך קטנות - רק שניים, 1929 ו-1930."
* L682: "עוד רואים שב-81% מהמקרים (ובמניות ערך קטנות ב-96%) יוותר לנו, לירושה, יותר כסף משהיה לנו בהתחלה, למרות משיכה של כ-13,000 בחודש לאורך 30 שנה."
* L689: "ראשית, הוא מאפשר לכם לשחק עם סוג ההשקעה, כולל 100% במניות ערך קטנות - שונה מאוד ממה שבדרך כלל מביאים לפנינו."

---

## 9. `intro`, `about` and other text

| Location | Text | Old | New | How computed | Flag |
| --- | --- | --- | --- | --- | --- |
| L272 `intro` | "פוליסת חיסכון ... בערך 1% ... כל שנה" | 1% | Personal fact (0.95% on L371) | n/a | SAME |
| L277 `intro` | "סכומים שיכולים להגיע למאות אלפי שקלים" | claim | 100,000 for 33 y at 0.95% vs 0.07% costs 217,750 real (885,163 − 667,413) | `commission_tax_scenarios` | SAME |
| L737 `about` sources | "YCharts - S&P 500 Monthly Total Return ... לעדכון 2024 ו-2025" | full TR | 2024–2025 monthly is now adjusted like CSPX (15% dividend withholding and 0.07% fee), about 0.3%/y below the index | `methodology.md` L97 | SMALL (source note) |
| L750 `about` sources | "FinanceCharts ... למשל VTI, VGK, VWO, BND, TLT, GLD, QQQ" | these ETFs | 2024–2025 now come from each series' own source: VEURX (Europe), VEIEX (EM), Vanguard Treasury funds, Gold and NASDAQ-100 from upmyinterest, MSCI factsheet, GDX, GSG and others | `data_corrections.json` | MEANING (source list is stale) |
| `stories.portfolio-summary` L489 | "יותר מ 50 דוגמאות" | external | n/a | n/a | not data |

### Proposed wording

* L750:
  > [Portfolio Visualizer / totalrealreturns](https://www.portfoliovisualizer.com/) וקרנות הסל המייצגות שלו: תשואות 2024/2025 לסוגי נכסים, מאותו מקור או קרן ששימשו להיסטוריה של כל סדרה (למשל VEURX, VEIEX, VFISX, GDX, GSG). הפירוט המלא בקובץ המקורות.
* L737: add "(בהתאמה לקרן CSPX: ניכוי מס מקור על דיבידנדים ודמי ניהול 0.07%)".

---

## Screens with no numbers that depend on data

`independent` (עמלות), `ira`, `portfolio-time`, and the reading notes in `chartReadingContent` and
`lazyReadingContent`. Their numbers are labels, window lengths or values computed at run time.
