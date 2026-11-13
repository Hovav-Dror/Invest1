// Number, money and text formatting shared by the app and the charts.

export const locale = "he-IL";

const LRM = "‎";

/** A real minus sign (−) instead of the hyphen before a number, as in the rest of the site. */
export function trueMinus(text) {
  return String(text).replace(/-(?=[\d₪.,])/g, "−");
}

export function numericValue(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
  ));
}

/** Wrap left-to-right text (English names, numbers) so it reads correctly inside Hebrew. */
export function ltrText(value) {
  return `⁦${String(value)}⁩`;
}

export function formatPercent(value, digits = 1) {
  if (!Number.isFinite(value)) return "";
  const text = value.toLocaleString(locale, { style: "percent", maximumFractionDigits: digits });
  return value < 0 ? `${LRM}${trueMinus(text)}${LRM}` : text;
}

export function formatShekel(value, digits = 0) {
  if (!Number.isFinite(value)) return "";
  const amount = Math.abs(value).toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return value < 0 ? `${LRM}−₪${amount}${LRM}` : `₪${amount}`;
}

/** Short money for axes: ₪500K, ₪1.2M. */
export function formatShekelShort(value) {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  let text;
  if (abs >= 1e6) text = `${trimNumber(abs / 1e6, abs >= 1e7 ? 0 : 1)}M`;
  else if (abs >= 1e3) text = `${trimNumber(abs / 1e3, abs >= 1e4 ? 0 : 1)}K`;
  else text = trimNumber(abs, 0);
  return `${LRM}${sign}₪${text}${LRM}`;
}

export function formatNumber(value, digits) {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  const maximumFractionDigits = digits ?? (abs >= 1000 ? 0 : abs >= 1 ? 2 : 4);
  const text = value.toLocaleString(locale, { maximumFractionDigits });
  return value < 0 ? `${LRM}${trueMinus(text)}${LRM}` : text;
}

function trimNumber(value, digits) {
  return Number(value.toFixed(digits)).toLocaleString("en-US", { maximumFractionDigits: digits });
}

/** "2024-03-01" -> 2024.1667 (fractional year), numbers pass through. */
export function toYearValue(value) {
  if (typeof value === "number") return value;
  const text = String(value ?? "");
  const match = /^(\d{4})-(\d{2})/.exec(text);
  if (match) return Number(match[1]) + (Number(match[2]) - 1) / 12;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

const MONTHS = ["ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני", "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳"];

/** Fractional year -> "מרץ 2024". */
export function formatMonthYear(yearValue) {
  if (!Number.isFinite(yearValue)) return "";
  const year = Math.floor(yearValue + 1e-6);
  const month = Math.round((yearValue - year) * 12) % 12;
  return `${MONTHS[month]} ${year}`;
}
