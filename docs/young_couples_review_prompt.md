# Review prompt: the young-couples section

Copy everything below the line into a new Claude Code session opened in this
worktree (`.claude/worktrees/young-couples`, branch `worktree-young-couples`).

---

Review the "זוגות צעירים" (young couples) section of this site end to end:
calculations, assumptions and data, Hebrew wording, and ease of use. Report
findings; do not change files unless I ask.

## What the section is

An educational Hebrew (RTL) site for young Israeli couples saving for a first
apartment. Seven pages, in menu order:

| View id | Title | Endpoint(s) |
| --- | --- | --- |
| `young-intro` | זוגות צעירים: כסף בתחילת הדרך | (text only) |
| `young-equity` | מה מחיר הדירה שנוכל לקנות? | `affordability` |
| `young-safe` | הפסד בבורסה לפני קניית דירה: למה הוא מתעצם? | `affordability` (mode `drop`) |
| `young-down` | כסף לדירה בשנים הקרובות: כמה ממנו במניות? | `down_payment`, `down_payment_ladder` |
| `young-homes` | האם מניות ודירות יורדות ביחד? | `homes_vs_stocks`, `homes_vs_stocks_episodes` |
| `young-pension` | דמי ניהול בפנסיה: כמה זה עולה? | `pension_fees`, `pension_fees_steps` |
| `young-cash` | החלק הסולידי: קרן כספית, פיקדון או מק"מ? | `cash_vehicles`, `cash_vehicles_inflation` |

Where things are:

- Calculations: `invest_core/calculations.py` (search for the endpoint names).
- Assumptions and warnings shown under each chart: `invest_core/methodology.py`.
- API parsing and validation: `invest_api/app.py` (`_parse_*_args`).
- Page text, controls, metrics and renderers: `invest_api/static/app.js`
  (`stories["young-…"]`, the view definitions with `id: "young-…"`,
  `metric*` functions, `render*` functions); styles in `invest_api/static/app.css`;
  chart engine in `invest_api/static/js/charts.js`.
- Data: `data/young_couples_monthly.parquet`, built by
  `scripts/build_young_couples_data.py` from `data/raw/` (sources and
  splicing in `data/raw/README.md` and the script's docstring).
- Docs: `docs/methodology.md` (per-endpoint rules), `docs/young_couples_plan.md`.
- Tests: `tests/test_calculations.py`, `tests/test_api.py`
  (run `python -m pytest -q`; Python is `/opt/homebrew/opt/python@3.9/bin/python3.9`).
- Run the site: `python -m flask --app invest_api.app run --port 5058` (the
  "young-couples" entry in `.claude/launch.json`), then open
  `http://localhost:5058/#young-intro`.

## What to check

### 1. Calculations

For each endpoint, read the code, recompute at least one result by hand or
with a short independent script, and look for:

- Off-by-one errors in monthly boundaries (the dwelling index and Israeli
  share index for month `d-1` sit at boundary `d`; cash earns month `d`'s rate).
- Tax: 25% of the real gain once at the end, no refund on losses
  (`down_payment`); 15% nominal yearly vs 25% real at the end (`cash_vehicles`).
- `affordability`: the bisection solver, purchase-tax brackets (2026), LTV by
  buyer type, the income (PTI) limit, renovation and costs coming out of equity,
  the "kink" where the binding limit switches, and the `marginal` column.
- `down_payment`: the wait rule (wait only after a 10% fall from the peak,
  until the peak is regained, up to N years, buy in the last month when data
  ends), the glide path, the Israeli-shares dividend add-on, CPI-linked cash.
  Check that every setting covers the same start months.
- `homes_vs_stocks_episodes`: how falls of 20%+ are found and matched with
  dwelling-price changes.
- `pension_fees`: monthly compounding, fee on deposits vs on balance, the
  conversion coefficient, the age-based track if present.
- Edge cases: zero or extreme inputs, very short horizons, the last months of
  data, NaN handling, API validation messages.

### 2. Data and assumptions

- Is each data series what the page says it is? Check the splices: dwelling
  prices before 1994 (CPI owner-occupied housing component), makam yields
  1986–1994 copied from Bank of Israel annual reports (compare a few values with
  the PDFs linked in `data/raw/README.md`), TASE general index rebuilt from the
  real index before 1993-12, TA-125 after 2016-08.
- Are the stated assumptions reasonable and current: Bank of Israel LTV and PTI
  limits, purchase-tax brackets, management fees, the 2.5% dividend yield on
  Israeli shares, the 0.3% money-market spread, pension fee averages and tender
  terms, track returns?
- Do the numbers quoted in the page text match what the calculator returns
  at the default settings? List every mismatch.
- Are the sources in each page's "הנחות ומגבלות הנתונים" box complete and
  enough for someone to reproduce the results?

### 3. Hebrew wording

The readers are young Israelis without a finance background. For every page:

- Flag awkward or unnatural Hebrew, literal translations, and jargon without an
  explanation (for example "מתאם", "ריאלי", "חציון").
- Flag sentences that could mislead: overstatements, claims stronger than the
  data, or wording that implies the bank "finances" the apartment.
- Check consistency of terms across pages: "השקעה סולידית" / "קרן כספית" /
  "צמוד למדד", "ההון העצמי", "מחיר הדירה שאפשר לקנות", "ערך הכסף מול מחירי
  הדירות", page titles in links.
- Suggest a concrete rewrite for each problem, in Hebrew.

### 4. Ease of use

Open each page in a browser at desktop width and at 375px (phone):

- Can a first-time reader tell what to do and what the chart shows within a
  few seconds? Are axis labels, legends, captions and table headers clear?
  Is it clear when higher is better?
- Do controls behave as expected (sliders shared between `young-equity` and
  `young-safe`, URL state, the advanced "שינוי הנחות" panel)?
- Any horizontal overflow, overlapping labels, unreadable text, RTL/LTR
  mix-ups (numbers with %, ₪, arrows), or broken links?
- Is the flow between pages logical, and do the cross-links point to the right
  pages with the current titles?

### 5. Code quality (briefly)

Duplication, dead code left from earlier versions, missing tests for the main
rules, and anything that would make the section hard to change.

## How to report

One list per area above, most important first. For each finding: the page or
file and line, what is wrong, why it matters, and a suggested fix. Mark each as
"bug", "misleading", "wording", "usability" or "nice to have". End with the
five changes you would make first.
