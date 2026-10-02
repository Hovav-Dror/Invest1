// Example of the layered screen template:
//   1. the bottom line (one sentence + key numbers, for every reader)
//   2. the chart (for readers who like charts)
//   3. a few basic controls, with the rest folded away
//   4. "go deeper": explanation, assumptions, data
//
// The screen owns its markup and controls; app.js only mounts it, runs it and
// keeps its settings in the URL.

import { renderChart } from "../charts.js";
import { escapeHtml, formatPercent, formatShekel, formatShekelShort, formatMonthYear, toYearValue } from "../format.js";

const SCENARIOS = [
  { key: "tax_at_end", label: "רק בסוף התקופה", short: "רק בסוף", color: "#2457ff" },
  { key: "tax_every_120_months", label: "כל 10 שנים", short: "כל 10 שנים", color: "#2f9e8f" },
  { key: "tax_every_60_months", label: "כל 5 שנים", short: "כל 5 שנים", color: "#d08a00" },
  { key: "tax_every_12_months", label: "כל שנה", short: "כל שנה", color: "#e0532f" },
  { key: "tax_every_month", label: "כל חודש", short: "כל חודש", color: "#2b2f31" }
];

const DEFAULTS = { initial: "100000", start_year: "1993", end_year: "2026", fee: "0", adjust_cpi: "true" };
const FIRST_YEAR = 1952;
const LAST_YEAR = 2026;

function yearOptions(selected, from, to) {
  const options = [];
  for (let year = from; year <= to; year += 1) {
    options.push(`<option value="${year}" ${String(year) === String(selected) ? "selected" : ""}>${year}</option>`);
  }
  return options.join("");
}

function moneyValue(text) {
  const number = Number(String(text).replace(/[,\s₪]/g, ""));
  return Number.isFinite(number) && number > 0 ? number : Number(DEFAULTS.initial);
}

export function createTaxTimingScreen() {
  let root = null;
  let ctx = null;

  const field = (name) => root.querySelector(`[name="${name}"]`);

  function state() {
    if (!root) return [];
    return [
      ["initial", String(moneyValue(field("initial").value))],
      ["start_year", field("start_year").value],
      ["end_year", field("end_year").value],
      ["fee", field("fee").value || "0"],
      ["adjust_cpi", field("adjust_cpi").checked ? "true" : "false"]
    ];
  }

  function apply(entries) {
    entries.forEach(([name, value]) => {
      const input = field(name);
      if (!input) return;
      if (input.type === "checkbox") input.checked = value === "true";
      else input.value = name === "initial" ? Number(value).toLocaleString("en-US") : value;
    });
  }

  function mount(container, context) {
    ctx = context;
    root = container;
    root.innerHTML = `
      <div class="layered">
        <section class="answer" aria-live="polite">
          <p class="answer-label">השורה התחתונה</p>
          <p class="answer-text" data-answer>מחשב...</p>
          <div class="answer-tiles" data-tiles></div>
        </section>

        <section class="layered-chart">
          <div data-chart></div>
        </section>

        <form class="basic-controls" data-controls>
          <label class="basic-field">
            <span>סכום ההשקעה</span>
            <input name="initial" type="text" inputmode="decimal" value="100,000">
          </label>
          <label class="basic-field">
            <span>משנת</span>
            <select name="start_year">${yearOptions(DEFAULTS.start_year, FIRST_YEAR, LAST_YEAR - 2)}</select>
          </label>
          <label class="basic-field">
            <span>עד שנת</span>
            <select name="end_year">${yearOptions(DEFAULTS.end_year, FIRST_YEAR + 2, LAST_YEAR)}</select>
          </label>
          <details class="more-controls">
            <summary>עוד הגדרות</summary>
            <div class="more-controls-body">
              <label class="basic-field">
                <span>דמי ניהול שנתיים (%)</span>
                <input name="fee" type="number" min="0" max="5" step="0.05" value="0" inputmode="decimal">
              </label>
              <label class="basic-check">
                <input name="adjust_cpi" type="checkbox" checked>
                <span>להציג בערכים ריאליים (אחרי אינפלציה)</span>
              </label>
            </div>
          </details>
        </form>

        <section class="deep">
          <h3 class="deep-title">להעמיק</h3>
          <details>
            <summary>למה מכירה מוקדמת עולה כל כך הרבה?</summary>
            <div class="deep-body">
              <p>כשמוכרים השקעה שהרוויחה, משלמים 25% מס על הרווח הריאלי. מי שמחזיק ולא מוכר, משאיר את המס הזה מושקע. הכסף שהיה הולך למס ממשיך לעבוד, ולאורך עשרות שנים זה מצטבר לסכום גדול.</p>
              <p>זה גם מסביר למה "כל חודש" ו"כל שנה" יוצאים כמעט אותו דבר: הפסדים מקוזזים מול רווחים, ולכן בשני המקרים משלמים בערך את אותו מס על הרווח של כל שנה. מה שבאמת משנה הוא לכמה שנים דוחים את המס.</p>
              <p>החישוב כאן לא כולל עמלות קנייה ומכירה ומרווחים. למי שמזיז כסף לעיתים קרובות הם מוסיפים עוד עלות.</p>
            </div>
          </details>
          <details>
            <summary>הנחות החישוב</summary>
            <div class="deep-body">
              <ul>
                <li>השקעה חד-פעמית במדד S&amp;P 500 כולל דיבידנדים, בשקלים.</li>
                <li>מס של 25% על הרווח הריאלי (אחרי הצמדה למדד המחירים בישראל). אין החזר מס על הפסד; הפסד מקוזז מול רווחים מאוחרים.</li>
                <li>"מימוש" הוא מכירה של הכל, תשלום המס וקנייה מחדש מיד.</li>
                <li>כל נקודה בגרף מראה כמה היה נשאר אילו מכרו הכל באותו רגע ושילמו את המס.</li>
                <li>דמי ניהול, אם נבחרו, נגבים מדי חודש.</li>
              </ul>
            </div>
          </details>
          <details>
            <summary>עוד על הנושא</summary>
            <div class="deep-body">
              <p>למה בכלל לא להתעסק בהשקעות – הפסיכולוגיה, הבדידות והשמות שאנחנו נותנים לדברים – ב<a href="#tax-events">"למה לא להתעסק בזה?"</a>.</p>
            </div>
          </details>
        </section>
      </div>
    `;
    const controls = root.querySelector("[data-controls]");
    controls.addEventListener("submit", (event) => event.preventDefault());
    controls.addEventListener("change", (event) => {
      if (event.target.name === "initial") event.target.value = moneyValue(event.target.value).toLocaleString("en-US");
      ctx.onChange();
    });
    controls.addEventListener("input", (event) => {
      if (event.target.name === "fee") ctx.onChange();
    });
  }

  async function run() {
    const [initial, startYear, endYear, fee, adjustCpi] = state().map(([, value]) => value);
    const from = Math.min(Number(startYear), Number(endYear) - 1);
    const params = new URLSearchParams({
      start: `${from}-01-01`,
      end: `${endYear}-01-01`,
      initial,
      adjust_cpi: adjustCpi,
      commissions: fee
    });
    const chartHost = root.querySelector("[data-chart]");
    chartHost.classList.add("is-updating");
    let payload;
    try {
      payload = await ctx.fetchPayload(`api/commission_tax?${params}`);
    } catch (error) {
      chartHost.classList.remove("is-updating");
      root.querySelector("[data-answer]").textContent = error.message;
      return;
    }
    chartHost.classList.remove("is-updating");
    render(payload, { initial: Number(initial), startYear: from, endYear: Number(endYear), fee: Number(fee), real: adjustCpi === "true" });
  }

  function render(payload, settings) {
    const rows = payload.data || [];
    if (!rows.length) return;
    const last = rows[rows.length - 1];
    const dateText = (date) => {
      const [year, month] = String(date).split("-").map(Number);
      return month === 1 ? `בתחילת ${year}` : `ב${formatMonthYear(toYearValue(date))}`;
    };
    const lastDate = dateText(last.date);
    const firstDate = dateText(rows[0].date);
    const atEnd = last.tax_at_end;
    const yearly = last.tax_every_12_months;
    const money = (value) => formatShekel(value, 0);
    const units = settings.real ? ` (בשקלים של ${settings.startYear}, אחרי אינפלציה)` : "";
    const lessThanEnd = (value) => (atEnd > 0 ? 1 - value / atEnd : 0);

    root.querySelector("[data-answer]").innerHTML = `
      מי שהשקיע <b>${escapeHtml(money(settings.initial))}</b> ב-S&amp;P 500 ${escapeHtml(firstDate)} ולא נגע בכסף,
      נשאר ${escapeHtml(lastDate)} עם <b>${escapeHtml(money(atEnd))}</b> אחרי מס${escapeHtml(units)}.
      מי שמכר וקנה מחדש פעם בשנה נשאר עם <b>${escapeHtml(money(yearly))}</b> –
      <b>${escapeHtml(formatPercent(lessThanEnd(yearly), 0))} פחות</b>, רק בגלל שהקדים את תשלום המס.
    `;
    root.querySelector("[data-tiles]").innerHTML = SCENARIOS.map((scenario) => {
      const value = last[scenario.key];
      const loss = lessThanEnd(value);
      return `
        <div class="answer-tile" style="--tile:${scenario.color}">
          <span class="answer-tile-label">מימוש ${escapeHtml(scenario.short)}</span>
          <b class="answer-tile-value">${escapeHtml(formatShekelShort(value))}</b>
          <span class="answer-tile-note">${scenario.key === "tax_at_end" ? "נקודת ההשוואה" : `${escapeHtml(formatPercent(loss, 0))} פחות`}</span>
        </div>
      `;
    }).join("");

    const series = [
      {
        id: "gross",
        label: settings.fee ? "בלי מס ובלי דמי ניהול" : "בלי מס בכלל",
        color: "#9aa39f",
        width: 1.6,
        dash: "4 4",
        points: rows.map((row) => ({ x: toYearValue(row.date), y: row.SP500_in_NIS, data: row }))
      },
      ...SCENARIOS.map((scenario) => ({
        id: scenario.key,
        label: `מימוש ${scenario.label}`,
        color: scenario.color,
        width: scenario.key === "tax_at_end" ? 2.6 : 2,
        points: rows.map((row) => ({ x: toYearValue(row.date), y: row[scenario.key], data: row })),
        endLabel: `${scenario.short} · ${formatShekelShort(last[scenario.key])}`,
        legendValue: formatShekelShort(last[scenario.key])
      }))
    ];
    renderChart(root.querySelector("[data-chart]"), {
      kind: "line",
      key: "tax-timing",
      title: "כמה נשאר אחרי מס, לפי תדירות המכירה",
      subtitle: `S&P 500 כולל דיבידנדים, בשקלים${settings.fee ? `, דמי ניהול ${settings.fee}% בשנה` : ", בלי דמי ניהול"}`,
      x: { format: formatMonthYear, tick: (value) => String(Math.round(value)), snap: 0.05 },
      y: {
        format: (value) => formatShekel(value, 0),
        tick: (value, compact) => (compact ? formatShekelShort(value) : formatShekel(value, 0)),
        zero: true
      },
      series,
      refLines: [{ y: settings.initial, label: "ההשקעה" }],
      endLabels: true,
      download: { filename: `tax_timing_${settings.startYear}_${settings.endYear}`, columns: payload.columns, rows },
      tooltip: (x, hits) => ({
        header: formatMonthYear(x),
        rows: [...hits].sort((a, b) => b.point.y - a.point.y).map((hit) => ({
          color: hit.series.color,
          label: hit.series.label,
          value: formatShekel(hit.point.y, 0)
        }))
      })
    });
  }

  return { mount, run, state, apply, defaults: () => Object.entries(DEFAULTS) };
}

