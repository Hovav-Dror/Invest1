// Responsive SVG charts.
//
// renderChart(target, spec) draws a chart sized to the target's real width,
// so text keeps its size on a phone. Titles, legends and notes are HTML so
// they wrap. One hover layer per chart handles mouse, touch and keyboard:
// it shows a crosshair and all series values at the nearest x.
//
// Chart kinds: line, bars (small multiples), heatmap, scatter, hbars, box, facets.

import { escapeHtml } from "./format.js";

const COMPACT_WIDTH = 560;
const CHAR_WIDTH = 6.6; // approximate width of one 12px character
const instances = new WeakMap();

const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver((entries) => {
  entries.forEach((entry) => {
    const instance = instances.get(entry.target);
    if (!instance || !instance.spec) return;
    const width = Math.round(entry.contentRect.width);
    if (!width || Math.abs(width - instance.width) < 4) return;
    cancelAnimationFrame(instance.frame);
    instance.frame = requestAnimationFrame(() => draw(entry.target, instance));
  });
});

export const PALETTE = ["#145f59", "#c0582b", "#385f9f", "#8a6d12", "#75518b", "#2f7646", "#a23f68", "#55736f", "#1f2f2b", "#d18f00"];

/** Draw ``spec`` into ``target``. Zoom and hidden series survive redraws with the same ``spec.key``. */
export function renderChart(target, spec) {
  let instance = instances.get(target);
  if (!instance) {
    instance = { zoom: null, hidden: new Set(), width: 0, key: undefined, cursor: null };
    instances.set(target, instance);
    attachEvents(target, instance);
    if (resizeObserver) resizeObserver.observe(target);
  }
  if (instance.key !== spec.key) {
    instance.zoom = null;
    instance.hidden = new Set(spec.hidden || []);
    instance.key = spec.key;
  }
  instance.spec = spec;
  draw(target, instance);
}

/** Stop managing ``target`` (its content is about to be replaced by other markup). */
export function releaseChart(target) {
  const instance = instances.get(target);
  if (instance) instance.spec = null;
}

export function chartMessage(target, message) {
  const instance = instances.get(target);
  if (instance) instance.spec = null;
  target.innerHTML = `<div class="chart-empty">${escapeHtml(message)}</div>`;
}

// ---------------------------------------------------------------------------
// Frame
// ---------------------------------------------------------------------------

function draw(target, instance) {
  const spec = instance.spec;
  if (!spec) return;
  const width = Math.max(Math.round(target.clientWidth || target.getBoundingClientRect().width || 640), 280);
  instance.width = width;
  instance.cursor = null;
  const renderer = RENDERERS[spec.kind];
  const result = renderer(spec, instance, width);
  instance.layout = result.layout || null;
  target.innerHTML = frameHtml(spec, instance, result);
  if (result.after) result.after(target);
}

function frameHtml(spec, instance, result) {
  const head = spec.title || spec.subtitle
    ? `<figcaption class="vchart-head">
        ${[].concat(spec.title || []).map((line) => `<span class="vchart-title">${escapeHtml(line)}</span>`).join("")}
        ${spec.subtitle ? `<span class="vchart-subtitle">${escapeHtml(spec.subtitle)}</span>` : ""}
      </figcaption>`
    : "";
  const notes = (spec.notes || []).filter(Boolean);
  const notesHtml = notes.length
    ? `<ul class="vchart-notes">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
    : "";
  const zoomButton = result.zoomable
    ? `<button type="button" class="vchart-reset" data-vchart-reset ${instance.zoom ? "" : "hidden"}>הצג טווח מלא</button>`
    : "";
  const help = result.help || "";
  const download = spec.download && spec.download.rows && spec.download.rows.length
    ? `<button type="button" class="vchart-download" data-vchart-download>הורדת הנתונים (CSV)</button>`
    : "";
  const notesLink = spec.notesHref
    ? `<a class="vchart-notes-link" href="${escapeHtml(spec.notesHref)}" data-notes-link>הנחות ומגבלות</a>`
    : "";
  return `
    <figure class="vchart vchart-${escapeHtml(spec.kind)}">
      ${head}
      ${result.plot === false ? "" : `<div class="vchart-plot" ${result.interactive === false ? "" : 'tabindex="0"'} dir="ltr">
        ${result.svg}
        <div class="vchart-tip" role="status" aria-live="polite" hidden></div>
      </div>`}
      ${result.html || ""}
      ${result.legend || ""}
      ${notesHtml}
      ${spec.captionHtml ? `<p class="vchart-caption">${spec.captionHtml}</p>` : spec.caption ? `<p class="vchart-caption">${escapeHtml(spec.caption)}</p>` : ""}
      ${spec.footerHtml || ""}
      ${help || zoomButton || download || notesLink ? `<div class="vchart-actions"><span class="vchart-help">${escapeHtml(help)}</span>${zoomButton}${download}${notesLink}</div>` : ""}
    </figure>
  `;
}

function svgOpen(width, height, spec) {
  const label = [[].concat(spec.title || []).join(" "), spec.subtitle, spec.summary].filter(Boolean).join(". ");
  return `<svg class="vchart-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}">`;
}

function touchHelp(zoomable) {
  const touch = typeof matchMedia !== "undefined" && matchMedia("(pointer: coarse)").matches;
  if (touch) return "נגיעה בגרף מציגה ערכים; גרירה לצדדים עוברת בין נקודות.";
  return zoomable
    ? "מעבר עם העכבר מציג ערכים. גרירה על הגרף מתמקדת בטווח, ולחיצה כפולה מחזירה."
    : "מעבר עם העכבר מציג ערכים.";
}

// ---------------------------------------------------------------------------
// Scales and ticks
// ---------------------------------------------------------------------------

export function niceTicks(min, max, count = 6) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const delta = Math.abs(min) || 1;
    return niceTicks(min - delta / 2, max + delta / 2, count);
  }
  const rawStep = (max - min) / Math.max(count, 1);
  const power = 10 ** Math.floor(Math.log10(rawStep));
  const fraction = rawStep / power;
  const step = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
  const ticks = [];
  for (let value = Math.floor(min / step) * step; value <= Math.ceil(max / step) * step + step / 2; value += step) {
    ticks.push(Math.abs(value) < step / 1e6 ? 0 : Number(value.toPrecision(12)));
  }
  return ticks;
}

function integerTicks(min, max, maxCount) {
  const span = Math.max(max - min, 1);
  const steps = [1, 2, 5, 10, 20, 25, 50, 100];
  const step = steps.find((candidate) => span / candidate <= maxCount) || 100;
  const ticks = [];
  for (let value = Math.ceil(min / step) * step; value <= max + 1e-9; value += step) ticks.push(value);
  return ticks;
}

function linear(domainMin, domainMax, rangeMin, rangeMax) {
  const span = domainMax - domainMin || 1;
  const scale = (value) => rangeMin + ((value - domainMin) / span) * (rangeMax - rangeMin);
  scale.invert = (pixel) => domainMin + ((pixel - rangeMin) / (rangeMax - rangeMin || 1)) * span;
  return scale;
}

function textWidth(text, size = 12) {
  return String(text ?? "").replace(/[‎⁦⁩]/g, "").length * CHAR_WIDTH * (size / 12);
}

function f(value) {
  return Number.isFinite(value) ? value.toFixed(1) : "0";
}

/** Spread labels vertically so none overlap. Items need .y; returns them with .labelY. */
function spreadLabels(items, minGap, top, bottom) {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  sorted.forEach((item, index) => {
    item.labelY = Math.max(item.y, index ? sorted[index - 1].labelY + minGap : top);
  });
  for (let index = sorted.length - 1; index >= 0; index -= 1) {
    const limit = index === sorted.length - 1 ? bottom : sorted[index + 1].labelY - minGap;
    sorted[index].labelY = Math.min(sorted[index].labelY, limit);
  }
  return sorted;
}

function bisectNearest(points, x) {
  let low = 0;
  let high = points.length - 1;
  if (high < 0) return -1;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (points[mid].x < x) low = mid;
    else high = mid;
  }
  return Math.abs(points[low].x - x) <= Math.abs(points[high].x - x) ? low : high;
}

function legendHtml(spec, instance) {
  if (spec.legend === false) return "";
  const items = (spec.series || []).filter((series) => series.legend !== false);
  if (items.length < 2 && !spec.legend) return "";
  const toggle = spec.legend !== "static";
  return `<div class="vchart-legend">${items.map((series) => {
    const hidden = instance.hidden.has(series.id);
    const swatch = `<i class="vchart-swatch${series.dash ? " dashed" : ""}" style="--swatch:${series.color}"></i>`;
    const value = series.legendValue ? `<b>${escapeHtml(series.legendValue)}</b>` : "";
    return toggle
      ? `<button type="button" class="vchart-legend-item" data-vchart-series="${escapeHtml(series.id)}" aria-pressed="${hidden ? "false" : "true"}">${swatch}<span>${escapeHtml(series.label)}</span>${value}</button>`
      : `<span class="vchart-legend-item">${swatch}<span>${escapeHtml(series.label)}</span>${value}</span>`;
  }).join("")}</div>`;
}

function tooltipHtml(header, rows) {
  return `
    ${header ? `<div class="vchart-tip-head">${escapeHtml(header)}</div>` : ""}
    ${rows.map((row) => `
      <div class="vchart-tip-row">
        ${row.color ? `<i class="vchart-swatch" style="--swatch:${row.color}"></i>` : ""}
        <span>${escapeHtml(row.label ?? "")}</span>
        ${row.value !== undefined ? `<b>${escapeHtml(row.value)}</b>` : ""}
      </div>
    `).join("")}
  `;
}

// ---------------------------------------------------------------------------
// Line chart
// ---------------------------------------------------------------------------

/*
spec = {
  kind: "line", key, title, subtitle, notes, caption, summary,
  x: { format(v), tick(v), label, integer: true, secondary(v) },
  y: { format(v), tick(v, compact), label, zero: true, domain: [min, max] },
  series: [{ id, label, color, width, dash, area, dots, dotRadius, legend, legendValue, endLabel,
             points: [{ x, y, data }] }],
  refLines: [{ y, label, className }], vLines: [{ x, label }], bands: [{ x0, x1, label }],
  zones: { at: 0, above, below },  // what the areas above and below a line mean, with arrows
  endLabels: true, zoomable: true, aspect: 0.55,
  tooltip(x, hits) -> { header, rows: [{ color, label, value }] }
}
*/
function drawLine(spec, instance, width) {
  const compact = width < COMPACT_WIDTH;
  const allSeries = spec.series.filter((series) => series.points.some((point) => Number.isFinite(point.y)));
  const visible = allSeries.filter((series) => !instance.hidden.has(series.id));
  const legend = legendHtml({ ...spec, series: allSeries }, instance);
  if (!visible.length) {
    return { svg: "", plot: false, html: `<div class="chart-empty">כל הסדרות מוסתרות. לחיצה על המקרא מחזירה סדרה.</div>`, legend };
  }

  const xs = visible.flatMap((series) => series.points.map((point) => point.x));
  const fullMin = Math.min(...xs);
  const fullMax = Math.max(...xs);
  const [xMin, xMax] = instance.zoom || [fullMin, fullMax];
  const inView = (point) => point.x >= xMin - 1e-9 && point.x <= xMax + 1e-9 && Number.isFinite(point.y);
  const ys = visible.flatMap((series) => series.points.filter(inView).map((point) => point.y));
  (spec.refLines || []).filter((line) => line.inDomain !== false).forEach((line) => ys.push(line.y));
  if (spec.y.zero) ys.push(0);
  let yMinRaw = spec.y.domain ? spec.y.domain[0] : Math.min(...ys);
  let yMaxRaw = spec.y.domain ? spec.y.domain[1] : Math.max(...ys);
  if (!spec.y.domain && yMaxRaw > yMinRaw) yMaxRaw += (yMaxRaw - yMinRaw) * 0.03;
  const yTicks = niceTicks(yMinRaw, yMaxRaw, compact ? 4 : 6);
  const yMin = yTicks[0];
  const yMax = yTicks[yTicks.length - 1];
  const yTick = (value) => (spec.y.tick || spec.y.format)(value, compact);

  const height = Math.round(Math.min(Math.max(width * (spec.aspect || 0.56), compact ? 260 : 320), spec.maxHeight || 520));
  const endLabels = spec.endLabels && !compact;
  const endTexts = endLabels ? visible.map((series) => series.endLabel || series.label) : [];
  const tickWidth = Math.max(...yTicks.map((tick) => textWidth(yTick(tick), 11))) + 12;
  const mirror = !compact && !endLabels && spec.y.mirror !== false;
  const pad = {
    top: spec.x.secondary ? 30 : 14,
    right: endLabels ? Math.min(Math.max(...endTexts.map((text) => textWidth(text))) + 18, width * 0.34) : mirror ? tickWidth : 14,
    bottom: 28 + (spec.x.label ? 18 : 0),
    left: tickWidth + (spec.y.label && !compact ? 16 : 0)
  };
  const plotRight = width - pad.right;
  const plotBottom = height - pad.bottom;
  const xScale = linear(xMin, xMax, pad.left, plotRight);
  const yScale = linear(yMin, yMax, plotBottom, pad.top);

  const xTickCount = Math.max(Math.floor((plotRight - pad.left) / (compact ? 64 : 80)), 2);
  const xTicks = spec.x.integer !== false
    ? integerTicks(xMin, xMax, xTickCount)
    : niceTicks(xMin, xMax, xTickCount).filter((tick) => tick >= xMin && tick <= xMax);
  const xTick = spec.x.tick || spec.x.format;

  const grid = yTicks.map((tick) => `
    <line class="vchart-grid" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(yScale(tick))}" y2="${f(yScale(tick))}"></line>
    <text class="vchart-tick" x="${f(pad.left - 6)}" y="${f(yScale(tick))}" text-anchor="end" dominant-baseline="middle">${escapeHtml(yTick(tick))}</text>
    ${mirror ? `<text class="vchart-tick" x="${f(plotRight + 6)}" y="${f(yScale(tick))}" dominant-baseline="middle">${escapeHtml(yTick(tick))}</text>` : ""}
  `).join("") + xTicks.map((tick) => `
    <line class="vchart-grid" x1="${f(xScale(tick))}" x2="${f(xScale(tick))}" y1="${f(pad.top)}" y2="${f(plotBottom)}"></line>
    <text class="vchart-tick" x="${f(xScale(tick))}" y="${f(plotBottom + 17)}" text-anchor="middle">${escapeHtml(xTick(tick))}</text>
    ${spec.x.secondary ? `<text class="vchart-tick vchart-tick-secondary" x="${f(xScale(tick))}" y="${f(pad.top - 10)}" text-anchor="middle">${escapeHtml(spec.x.secondary(tick))}</text>` : ""}
  `).join("");

  const clipId = `clip-${Math.random().toString(36).slice(2, 9)}`;
  const lines = visible.map((series) => {
    const segments = [];
    let current = [];
    series.points.forEach((point) => {
      if (!Number.isFinite(point.y)) {
        if (current.length) segments.push(current);
        current = [];
        return;
      }
      current.push(point);
    });
    if (current.length) segments.push(current);
    return segments.map((segment) => {
      const path = segment.map((point, index) => `${index ? "L" : "M"}${f(xScale(point.x))} ${f(yScale(point.y))}`).join("");
      const area = series.area
        ? `<path d="${path}L${f(xScale(segment[segment.length - 1].x))} ${f(yScale(Math.max(yMin, Math.min(0, yMax))))}L${f(xScale(segment[0].x))} ${f(yScale(Math.max(yMin, Math.min(0, yMax))))}Z" fill="${series.color}" opacity="0.14"></path>`
        : "";
      const dots = series.dots
        ? segment.filter(inView).map((point) => {
          const cx = xScale(point.x);
          const cy = yScale(point.y);
          if (series.marker === "triangle") {
            const r = compact ? 4 : 6;
            return `<path class="vchart-point" d="M${f(cx)} ${f(cy - r)}L${f(cx + r)} ${f(cy + r * 0.8)}L${f(cx - r)} ${f(cy + r * 0.8)}Z" fill="${series.color}"></path>`;
          }
          const radius = series.dotRadius ? (compact ? series.dotRadius * 0.75 : series.dotRadius) : (compact ? 2.5 : 4);
          const ring = series.dotRadius ? ` stroke="#fff" stroke-width="2.5"` : "";
          return `<circle class="vchart-point" cx="${f(cx)}" cy="${f(cy)}" r="${f(radius)}" fill="${series.color}"${ring}></circle>`;
        }).join("")
        : "";
      return `${area}<path d="${path}" fill="none" stroke="${series.color}" stroke-width="${series.width ?? 2}" ${series.dash ? `stroke-dasharray="${series.dash}"` : ""} stroke-linejoin="round" stroke-linecap="round"></path>${dots}`;
    }).join("");
  }).join("");

  // Text placed at data coordinates; only where there is room for it.
  // Notes sharing an x are spread vertically so they never overlap.
  const placedNotes = compact ? [] : (spec.annotations || [])
    .filter((note) => note.x >= xMin && note.x <= xMax && Number.isFinite(note.y) && note.y >= yMin && note.y <= yMax)
    .map((note) => ({ ...note, y: yScale(note.y) + (note.dy || 0) }));
  const byX = new Map();
  placedNotes.forEach((note) => byX.set(note.x, [...(byX.get(note.x) || []), note]));
  const annotations = [...byX.values()].flatMap((group) => spreadLabels(group, 16, pad.top + 10, plotBottom - 4))
    .map((note) => `<text class="vchart-annotation" x="${f(xScale(note.x) + (note.dx || 0))}" y="${f(note.labelY)}" text-anchor="${note.anchor || "start"}" dominant-baseline="middle" fill="${note.color || "#17201d"}">${escapeHtml(note.text)}</text>`)
    .join("");

  const refs = (spec.refLines || []).filter((line) => line.y >= yMin && line.y <= yMax).map((line) => `
    <line class="vchart-ref ${escapeHtml(line.className || "")}" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(yScale(line.y))}" y2="${f(yScale(line.y))}"></line>
    ${line.label ? `<text class="vchart-ref-label" x="${f(pad.left + 6)}" y="${f(yScale(line.y) - 5)}">${escapeHtml(line.label)}</text>` : ""}
  `).join("") + (spec.vLines || []).filter((line) => line.x >= xMin && line.x <= xMax).map((line) => `
    <line class="vchart-ref vchart-ref-v" x1="${f(xScale(line.x))}" x2="${f(xScale(line.x))}" y1="${f(pad.top)}" y2="${f(plotBottom)}"></line>
    ${line.label && !compact ? `<text class="vchart-ref-label" x="${f(xScale(line.x) + 5)}" y="${f(pad.top + 13)}">${escapeHtml(line.label)}</text>` : ""}
  `).join("");

  // "↑ above means..." near the top and "↓ below means..." near the bottom, when the line is in view.
  const zoneAt = spec.zones ? (spec.zones.at ?? 0) : null;
  const zones = spec.zones && zoneAt > yMin && zoneAt < yMax ? [
    spec.zones.above ? `<text class="vchart-zone-label vchart-zone-above" direction="rtl" x="${f(plotRight - 8)}" y="${f(pad.top + 14)}" text-anchor="start">${escapeHtml(`↑ ${spec.zones.above}`)}</text>` : "",
    spec.zones.below ? `<text class="vchart-zone-label vchart-zone-below" direction="rtl" x="${f(plotRight - 8)}" y="${f(plotBottom - 8)}" text-anchor="start">${escapeHtml(`↓ ${spec.zones.below}`)}</text>` : ""
  ].join("") : "";

  let ends = "";
  if (endLabels) {
    const items = visible.map((series) => {
      const last = [...series.points].reverse().find(inView);
      return last ? { series, y: yScale(last.y) } : null;
    }).filter(Boolean);
    ends = spreadLabels(items, 15, pad.top + 6, plotBottom - 2).map((item) => `
      <text class="vchart-end-label" x="${f(plotRight + 8)}" y="${f(item.labelY)}" text-anchor="end" dominant-baseline="middle" fill="${item.series.color}">${escapeHtml(item.series.endLabel || item.series.label)}</text>
    `).join("");
  }

  // Shaded x ranges behind everything else, clipped to the visible range.
  // A label that would overlap the previous one (about 6px a character) is left out.
  let lastLabelEdge = -Infinity;
  const bands = (spec.bands || []).filter((band) => band.x1 >= xMin && band.x0 <= xMax)
    .slice().sort((a, b) => a.x0 - b.x0).map((band) => {
      const x0 = xScale(Math.max(band.x0, xMin));
      const x1 = xScale(Math.min(band.x1, xMax));
      const middle = (x0 + x1) / 2;
      const half = String(band.label || "").length * 3;
      const showLabel = band.label && !compact && middle - half > lastLabelEdge + 4;
      if (showLabel) lastLabelEdge = middle + half;
      return `<rect class="vchart-band" x="${f(Math.min(x0, x1))}" y="${f(pad.top)}" width="${f(Math.abs(x1 - x0))}" height="${f(plotBottom - pad.top)}"></rect>
      ${showLabel ? `<text class="vchart-band-label" x="${f(middle)}" y="${f(plotBottom - 6)}" text-anchor="middle">${escapeHtml(band.label)}</text>` : ""}`;
    }).join("");

  const axisLabels = `
    ${spec.x.label ? `<text class="vchart-axis-label" x="${f((pad.left + plotRight) / 2)}" y="${f(height - 4)}" text-anchor="middle">${escapeHtml(spec.x.label)}</text>` : ""}
    ${spec.y.label && !compact ? `<text class="vchart-axis-label" transform="translate(12 ${f((pad.top + plotBottom) / 2)}) rotate(-90)" text-anchor="middle">${escapeHtml(spec.y.label)}</text>` : ""}
  `;

  const svg = `${svgOpen(width, height, spec)}
    <defs><clipPath id="${clipId}"><rect x="${f(pad.left)}" y="${f(pad.top - 2)}" width="${f(plotRight - pad.left)}" height="${f(plotBottom - pad.top + 4)}"></rect></clipPath></defs>
    ${bands}
    ${grid}
    <line class="vchart-axis" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(plotBottom)}" y2="${f(plotBottom)}"></line>
    ${refs}
    <g clip-path="url(#${clipId})">${lines}</g>
    ${zones}
    ${annotations}
    ${ends}
    ${axisLabels}
    <g class="vchart-cursor" hidden>
      <line class="vchart-crosshair" y1="${f(pad.top)}" y2="${f(plotBottom)}"></line>
    </g>
    <rect class="vchart-zoom" hidden y="${f(pad.top)}" height="${f(plotBottom - pad.top)}"></rect>
  </svg>`;

  const allX = [...new Set(visible.flatMap((series) => series.points.filter(inView).map((point) => point.x)))].sort((a, b) => a - b);
  const locate = (px) => {
    if (!allX.length) return null;
    const domainX = xScale.invert(Math.min(Math.max(px, pad.left), plotRight));
    const nearestX = allX[bisectNearest(allX.map((x) => ({ x })), domainX)];
    const hits = visible.map((series) => {
      const points = series.points.filter((point) => Number.isFinite(point.y));
      const index = bisectNearest(points, nearestX);
      const point = points[index];
      if (!point || Math.abs(point.x - nearestX) > (spec.x.snap ?? 0.6)) return null;
      return { series, point };
    }).filter(Boolean);
    if (!hits.length) return null;
    const content = spec.tooltip
      ? spec.tooltip(nearestX, hits)
      : {
          header: spec.x.format(nearestX),
          rows: [...hits].sort((a, b) => b.point.y - a.point.y).map((hit) => ({ color: hit.series.color, label: hit.series.label, value: spec.y.format(hit.point.y) }))
        };
    return {
      x: xScale(nearestX),
      marks: hits.map((hit) => ({ cx: xScale(hit.point.x), cy: yScale(hit.point.y), color: hit.series.color })),
      html: tooltipHtml(content.header, content.rows),
      index: allX.indexOf(nearestX),
      count: allX.length,
      xAt: (index) => xScale(allX[Math.min(Math.max(index, 0), allX.length - 1)])
    };
  };

  return {
    svg,
    legend,
    zoomable: spec.zoomable !== false,
    help: touchHelp(spec.zoomable !== false),
    layout: { type: "x", locate, plotLeft: pad.left, plotRight, plotTop: pad.top, plotBottom, xScale, zoomable: spec.zoomable !== false }
  };
}

// ---------------------------------------------------------------------------
// Small-multiple bar charts
// ---------------------------------------------------------------------------

/*
spec = {
  kind: "bars", key, title, notes, caption,
  x: { format(v) }, y: { format(v), tick(v) },
  panels: [{ id, label, note, points: [{ x, y, data }] }],
  colors: { positive, negative }, tooltip(panel, point) -> { header, rows }
}
*/
function drawBars(spec, instance, width) {
  const compact = width < COMPACT_WIDTH;
  const panels = spec.panels.filter((panel) => panel.points.length);
  const xs = panels.flatMap((panel) => panel.points.map((point) => point.x));
  const ys = panels.flatMap((panel) => panel.points.map((point) => point.y)).filter(Number.isFinite);
  const maxAbs = Math.max(...ys.map(Math.abs), 0.01);
  const yTicks = niceTicks(-maxAbs, maxAbs, compact ? 2 : 4);
  const yMin = yTicks[0];
  const yMax = yTicks[yTicks.length - 1];
  const yTick = spec.y.tick || spec.y.format;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const panelHeight = compact ? 110 : 140;
  const stripHeight = 22;
  const gap = 18;
  const pad = { left: Math.max(...yTicks.map((tick) => textWidth(yTick(tick), 11))) + 12, right: 10, top: 6, bottom: 24 };
  const height = pad.top + panels.length * (panelHeight + stripHeight + gap) - gap + pad.bottom;
  const plotRight = width - pad.right;
  const band = (plotRight - pad.left) / (xMax - xMin + 1);
  const xScale = (x) => pad.left + (x - xMin + 0.5) * band;
  const xTicks = integerTicks(xMin, xMax, Math.max(Math.floor((plotRight - pad.left) / (compact ? 56 : 72)), 2));
  const colors = spec.colors || { positive: PALETTE[0], negative: PALETTE[1] };

  const panelLayouts = [];
  const body = panels.map((panel, index) => {
    const top = pad.top + index * (panelHeight + stripHeight + gap) + stripHeight;
    const bottom = top + panelHeight;
    const yScale = linear(yMin, yMax, bottom, top);
    panelLayouts.push({ panel, top, bottom, yScale });
    const zero = yScale(0);
    const bars = panel.points.filter((point) => Number.isFinite(point.y)).map((point) => {
      const y = yScale(point.y);
      return `<rect x="${f(xScale(point.x) - band * 0.4)}" width="${f(Math.max(band * 0.8, 1))}" y="${f(Math.min(y, zero))}" height="${f(Math.max(Math.abs(zero - y), 1))}" fill="${point.y >= 0 ? colors.positive : colors.negative}"></rect>`;
    }).join("");
    return `
      <text class="vchart-panel-label" x="${f(plotRight)}" y="${f(top - 7)}" text-anchor="start">${escapeHtml(panel.label)}${panel.note ? ` · ${escapeHtml(panel.note)}` : ""}</text>
      ${yTicks.map((tick) => `
        <line class="vchart-grid" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(yScale(tick))}" y2="${f(yScale(tick))}"></line>
        <text class="vchart-tick" x="${f(pad.left - 6)}" y="${f(yScale(tick))}" text-anchor="end" dominant-baseline="middle">${escapeHtml(yTick(tick))}</text>
      `).join("")}
      ${bars}
      <line class="vchart-axis" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(zero)}" y2="${f(zero)}"></line>
    `;
  }).join("");
  const lastBottom = panelLayouts.length ? panelLayouts[panelLayouts.length - 1].bottom : height - pad.bottom;
  const xAxis = xTicks.map((tick) => `<text class="vchart-tick" x="${f(xScale(tick))}" y="${f(lastBottom + 17)}" text-anchor="middle">${escapeHtml(spec.x.format(tick))}</text>`).join("");

  const svg = `${svgOpen(width, height, spec)}
    ${body}${xAxis}
    <g class="vchart-cursor" hidden><line class="vchart-crosshair" y1="${f(pad.top)}" y2="${f(lastBottom)}"></line></g>
  </svg>`;

  const locate = (px, py) => {
    const layout = panelLayouts.find((item) => py <= item.bottom + gap / 2) || panelLayouts[panelLayouts.length - 1];
    if (!layout) return null;
    const x = Math.round(xMin + (px - pad.left) / band - 0.5);
    const point = layout.panel.points.find((item) => item.x === x && Number.isFinite(item.y));
    if (!point) return null;
    const content = spec.tooltip
      ? spec.tooltip(layout.panel, point)
      : { header: spec.x.format(point.x), rows: [{ label: layout.panel.label, value: spec.y.format(point.y) }] };
    return {
      x: xScale(point.x),
      marks: [],
      html: tooltipHtml(content.header, content.rows),
      index: x - xMin,
      count: xMax - xMin + 1,
      xAt: (index) => xScale(xMin + Math.min(Math.max(index, 0), xMax - xMin)),
      yHint: layout.top
    };
  };

  return { svg, help: touchHelp(false), layout: { type: "x", locate, plotLeft: pad.left, plotRight } };
}

// ---------------------------------------------------------------------------
// Heatmap
// ---------------------------------------------------------------------------

/*
spec = {
  kind: "heatmap", key, title, subtitle, notes, caption,
  cells: [{ x, y, value, data }], x: { label, format }, y: { label, format },
  color(value) -> css, legend: { min, max, minLabel, maxLabel, format }, tooltip(cell) -> { header, rows }
}
*/
function drawHeatmap(spec, instance, width) {
  const compact = width < COMPACT_WIDTH;
  const xValues = [...new Set(spec.cells.map((cell) => cell.x))].sort((a, b) => a - b);
  const yValues = [...new Set(spec.cells.map((cell) => cell.y))].sort((a, b) => a - b);
  const lookup = new Map(spec.cells.map((cell) => [`${cell.x}|${cell.y}`, cell]));
  const pad = { left: 34 + (spec.y.label ? 14 : 0), right: 8, top: 6, bottom: 26 + (spec.x.label ? 16 : 0) };
  const plotWidth = width - pad.left - pad.right;
  const cellWidth = plotWidth / xValues.length;
  const cellHeight = Math.max(Math.min(compact ? 13 : 18, (compact ? 360 : 440) / yValues.length), 6);
  const plotHeight = cellHeight * yValues.length;
  const height = pad.top + plotHeight + pad.bottom;
  const xPos = (index) => pad.left + index * cellWidth;
  const yPos = (index) => pad.top + (yValues.length - index - 1) * cellHeight;

  const cells = [];
  yValues.forEach((y, yIndex) => xValues.forEach((x, xIndex) => {
    const cell = lookup.get(`${x}|${y}`);
    if (!cell) return;
    cells.push(`<rect x="${f(xPos(xIndex))}" y="${f(yPos(yIndex))}" width="${f(cellWidth + 0.5)}" height="${f(cellHeight + 0.5)}" fill="${spec.color(cell.value)}"></rect>`);
  }));
  const xTicks = integerTicks(xValues[0], xValues[xValues.length - 1], Math.max(Math.floor(plotWidth / (compact ? 50 : 64)), 2));
  const yTicks = yValues.filter((value) => value === yValues[0] || value % 5 === 0);

  const svg = `${svgOpen(width, height, spec)}
    <rect x="${f(pad.left)}" y="${f(pad.top)}" width="${f(plotWidth)}" height="${f(plotHeight)}" class="vchart-heat-bg"></rect>
    ${cells.join("")}
    ${xTicks.map((tick) => {
      const index = xValues.indexOf(tick);
      if (index < 0) return "";
      return `<text class="vchart-tick" x="${f(xPos(index) + cellWidth / 2)}" y="${f(pad.top + plotHeight + 16)}" text-anchor="middle">${escapeHtml(spec.x.format(tick))}</text>`;
    }).join("")}
    ${yTicks.map((tick) => {
      const index = yValues.indexOf(tick);
      return `<text class="vchart-tick" x="${f(pad.left - 5)}" y="${f(yPos(index) + cellHeight / 2)}" text-anchor="end" dominant-baseline="middle">${escapeHtml(spec.y.format(tick))}</text>`;
    }).join("")}
    ${spec.x.label ? `<text class="vchart-axis-label" x="${f(pad.left + plotWidth / 2)}" y="${f(height - 3)}" text-anchor="middle">${escapeHtml(spec.x.label)}</text>` : ""}
    ${spec.y.label ? `<text class="vchart-axis-label" transform="translate(11 ${f(pad.top + plotHeight / 2)}) rotate(-90)" text-anchor="middle">${escapeHtml(spec.y.label)}</text>` : ""}
    <g class="vchart-cursor" hidden><rect class="vchart-heat-cursor" width="${f(cellWidth)}" height="${f(cellHeight)}"></rect></g>
  </svg>`;

  const legend = spec.legend ? `
    <div class="vchart-heat-legend">
      <span>${escapeHtml(spec.legend.minLabel)}</span>
      <i style="background:linear-gradient(to left, ${spec.color(spec.legend.min)}, ${spec.color(0)}, ${spec.color(spec.legend.max)})"></i>
      <span>${escapeHtml(spec.legend.maxLabel)}</span>
    </div>` : "";

  const locate = (px, py) => {
    const xIndex = Math.floor((px - pad.left) / cellWidth);
    const yIndex = yValues.length - 1 - Math.floor((py - pad.top) / cellHeight);
    const cell = lookup.get(`${xValues[xIndex]}|${yValues[yIndex]}`);
    if (!cell) return null;
    const content = spec.tooltip(cell);
    return {
      x: xPos(xIndex) + cellWidth / 2,
      cell: { x: xPos(xIndex), y: yPos(yIndex) },
      marks: [],
      html: tooltipHtml(content.header, content.rows),
      yHint: yPos(yIndex)
    };
  };

  return { svg, legend, help: touchHelp(false), layout: { type: "free", locate } };
}

// ---------------------------------------------------------------------------
// Scatter
// ---------------------------------------------------------------------------

/*
spec = {
  kind: "scatter", key, title, subtitle, notes, caption,
  points: [{ x, y, r, label, highlight, data }],
  x: { format, tick, label }, y: { format, tick, label }, tooltip(point) -> { header, rows }
}
*/
function drawScatter(spec, instance, width) {
  const compact = width < COMPACT_WIDTH;
  const points = spec.points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  const xTicks = niceTicks(Math.min(0, ...points.map((point) => point.x)), Math.max(...points.map((point) => point.x)) * 1.05, compact ? 4 : 7);
  const yTicks = niceTicks(Math.min(0, ...points.map((point) => point.y)), Math.max(...points.map((point) => point.y)) * 1.05, compact ? 5 : 7);
  const yTick = spec.y.tick || spec.y.format;
  const xTick = spec.x.tick || spec.x.format;
  const height = Math.round(Math.min(Math.max(width * 0.62, compact ? 300 : 360), 560));
  const pad = {
    left: Math.max(...yTicks.map((tick) => textWidth(yTick(tick), 11))) + 12 + (spec.y.label ? 16 : 0),
    right: 16,
    top: 12,
    bottom: 28 + (spec.x.label ? 18 : 0)
  };
  const plotRight = width - pad.right;
  const plotBottom = height - pad.bottom;
  const xScale = linear(xTicks[0], xTicks[xTicks.length - 1], pad.left, plotRight);
  const yScale = linear(yTicks[0], yTicks[yTicks.length - 1], plotBottom, pad.top);
  const radius = (point) => (point.r || 5) * (compact ? 0.75 : 1);

  // Greedy label placement: try four positions, skip when it would overlap.
  const placed = [];
  const overlaps = (box) => placed.some((other) => box.x1 < other.x2 && box.x2 > other.x1 && box.y1 < other.y2 && box.y2 > other.y1);
  const ordered = [...points].sort((a, b) => Number(Boolean(b.highlight)) - Number(Boolean(a.highlight)));
  points.forEach((point) => placed.push({ x1: xScale(point.x) - radius(point), x2: xScale(point.x) + radius(point), y1: yScale(point.y) - radius(point), y2: yScale(point.y) + radius(point) }));
  const labels = ordered.map((point) => {
    if (compact && !point.highlight && points.length > 8) return "";
    const cx = xScale(point.x);
    const cy = yScale(point.y);
    const w = textWidth(point.label, 12.5);
    const r = radius(point) + 3;
    const options = [
      { x: cx + r, y: cy + 4, anchor: "start" },
      { x: cx - r, y: cy + 4, anchor: "end" },
      { x: cx + r, y: cy - r, anchor: "start" },
      { x: cx - r, y: cy - r, anchor: "end" },
      { x: cx + r, y: cy + r + 9, anchor: "start" },
      { x: cx - r, y: cy + r + 9, anchor: "end" },
      { x: cx, y: cy - r - 4, anchor: "middle" },
      { x: cx, y: cy + r + 13, anchor: "middle" },
      { x: cx + r, y: cy - r - 12, anchor: "start" },
      { x: cx - r, y: cy + r + 21, anchor: "end" }
    ];
    for (const option of options) {
      const x1 = option.anchor === "start" ? option.x : option.anchor === "middle" ? option.x - w / 2 : option.x - w;
      const box = { x1, x2: x1 + w, y1: option.y - 10, y2: option.y + 2 };
      if (box.x1 < pad.left || box.x2 > plotRight || box.y1 < pad.top || overlaps(box)) continue;
      placed.push(box);
      return `<text class="vchart-point-label${point.highlight ? " highlight" : ""}" x="${f(option.x)}" y="${f(option.y)}" text-anchor="${option.anchor}">${escapeHtml(point.label)}</text>`;
    }
    return "";
  }).join("");

  const svg = `${svgOpen(width, height, spec)}
    ${yTicks.map((tick) => `
      <line class="vchart-grid" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(yScale(tick))}" y2="${f(yScale(tick))}"></line>
      <text class="vchart-tick" x="${f(pad.left - 6)}" y="${f(yScale(tick))}" text-anchor="end" dominant-baseline="middle">${escapeHtml(yTick(tick))}</text>
    `).join("")}
    ${xTicks.map((tick) => `
      <line class="vchart-grid" x1="${f(xScale(tick))}" x2="${f(xScale(tick))}" y1="${f(pad.top)}" y2="${f(plotBottom)}"></line>
      <text class="vchart-tick" x="${f(xScale(tick))}" y="${f(plotBottom + 17)}" text-anchor="middle">${escapeHtml(xTick(tick))}</text>
    `).join("")}
    <line class="vchart-axis" x1="${f(pad.left)}" x2="${f(plotRight)}" y1="${f(plotBottom)}" y2="${f(plotBottom)}"></line>
    ${points.map((point) => `<circle class="vchart-dot${point.highlight ? " highlight" : ""}" cx="${f(xScale(point.x))}" cy="${f(yScale(point.y))}" r="${f(radius(point))}"></circle>`).join("")}
    ${labels}
    ${spec.x.label ? `<text class="vchart-axis-label" x="${f((pad.left + plotRight) / 2)}" y="${f(height - 4)}" text-anchor="middle">${escapeHtml(spec.x.label)}</text>` : ""}
    ${spec.y.label ? `<text class="vchart-axis-label" transform="translate(12 ${f((pad.top + plotBottom) / 2)}) rotate(-90)" text-anchor="middle">${escapeHtml(spec.y.label)}</text>` : ""}
    <g class="vchart-cursor" hidden></g>
  </svg>`;

  const locate = (px, py) => {
    let best = null;
    let bestDistance = Infinity;
    points.forEach((point) => {
      const distance = Math.hypot(xScale(point.x) - px, yScale(point.y) - py);
      if (distance < bestDistance) {
        best = point;
        bestDistance = distance;
      }
    });
    if (!best || bestDistance > 40) return null;
    const content = spec.tooltip(best);
    return {
      x: xScale(best.x),
      marks: [{ cx: xScale(best.x), cy: yScale(best.y), color: "#17201d", r: radius(best) + 3, ring: true }],
      html: tooltipHtml(content.header, content.rows),
      yHint: yScale(best.y)
    };
  };

  return { svg, help: touchHelp(false), layout: { type: "free", locate } };
}

// ---------------------------------------------------------------------------
// Horizontal rows: bars (0..1 shares) and box plots
// ---------------------------------------------------------------------------

function rowFrame(spec, width, labels, domain, tickFormat) {
  const compact = width < COMPACT_WIDTH;
  const labelWidth = Math.min(Math.max(...labels.map((label) => textWidth(label, 12))) + 12, width * (compact ? 0.42 : 0.32));
  const rowHeight = compact ? 26 : 28;
  const pad = { left: labelWidth, right: 16, top: 6, bottom: 26 + (spec.x && spec.x.label ? 16 : 0) };
  const height = pad.top + labels.length * rowHeight + pad.bottom;
  const plotRight = width - pad.right;
  const xTicks = niceTicks(domain[0], domain[1], compact ? 4 : 6).filter((tick) => tick >= domain[0] - 1e-9 && tick <= domain[1] + 1e-9);
  const xScale = linear(xTicks[0], xTicks[xTicks.length - 1], pad.left, plotRight);
  const plotBottom = pad.top + labels.length * rowHeight;
  const grid = xTicks.map((tick) => `
    <line class="vchart-grid" x1="${f(xScale(tick))}" x2="${f(xScale(tick))}" y1="${f(pad.top)}" y2="${f(plotBottom)}"></line>
    <text class="vchart-tick" x="${f(xScale(tick))}" y="${f(plotBottom + 16)}" text-anchor="middle">${escapeHtml(tickFormat(tick))}</text>
  `).join("");
  const labelText = labels.map((label, index) => `
    <text class="vchart-row-label" x="${f(pad.left - 8)}" y="${f(pad.top + index * rowHeight + rowHeight / 2)}" text-anchor="end" dominant-baseline="middle">${escapeHtml(label)}</text>
  `).join("");
  const axisLabel = spec.x && spec.x.label ? `<text class="vchart-axis-label" x="${f((pad.left + plotRight) / 2)}" y="${f(height - 3)}" text-anchor="middle">${escapeHtml(spec.x.label)}</text>` : "";
  const rowAt = (py) => Math.floor((py - pad.top) / rowHeight);
  return { pad, height, rowHeight, xScale, grid, labelText, axisLabel, plotBottom, rowAt };
}

/*
spec = { kind: "hbars", rows: [{ label, value, data, highlight }], x: { format, label, domain }, tooltip(row) }
*/
function drawHBars(spec, instance, width) {
  const frame = rowFrame(spec, width, spec.rows.map((row) => row.label), spec.x.domain || [0, Math.max(...spec.rows.map((row) => row.value))], spec.x.format);
  const bars = spec.rows.map((row, index) => {
    const y = frame.pad.top + index * frame.rowHeight + 4;
    const x2 = frame.xScale(row.value);
    return `
      <rect class="vchart-hbar${row.highlight ? " highlight" : ""}" x="${f(frame.pad.left)}" y="${f(y)}" width="${f(Math.max(x2 - frame.pad.left, 1))}" height="${f(frame.rowHeight - 8)}"></rect>
      <text class="vchart-hbar-value" x="${f(x2 + 4)}" y="${f(y + (frame.rowHeight - 8) / 2)}" dominant-baseline="middle">${escapeHtml(spec.x.format(row.value))}</text>
    `;
  }).join("");
  const svg = `${svgOpen(width, frame.height, spec)}${frame.grid}${frame.labelText}${bars}${frame.axisLabel}<g class="vchart-cursor" hidden></g></svg>`;
  const locate = (px, py) => {
    const row = spec.rows[frame.rowAt(py)];
    if (!row) return null;
    const content = spec.tooltip(row);
    return { x: px, marks: [], html: tooltipHtml(content.header, content.rows), yHint: py };
  };
  return { svg, help: touchHelp(false), layout: { type: "free", locate } };
}

/*
spec = { kind: "box", rows: [{ label, min, q1, median, q3, max, highlight }], x: { format, label }, tooltip(row) }
*/
function drawBox(spec, instance, width) {
  const min = Math.min(0, ...spec.rows.map((row) => row.min));
  const max = Math.max(...spec.rows.map((row) => row.max));
  const frame = rowFrame(spec, width, spec.rows.map((row) => row.label), [min, max], spec.x.format);
  const boxes = spec.rows.map((row, index) => {
    const cy = frame.pad.top + index * frame.rowHeight + frame.rowHeight / 2;
    const color = row.highlight ? PALETTE[1] : PALETTE[4];
    return `
      <line x1="${f(frame.xScale(row.min))}" x2="${f(frame.xScale(row.max))}" y1="${f(cy)}" y2="${f(cy)}" stroke="${color}" stroke-width="1.5"></line>
      <rect x="${f(frame.xScale(row.q1))}" y="${f(cy - 8)}" width="${f(Math.max(frame.xScale(row.q3) - frame.xScale(row.q1), 1))}" height="16" fill="${color}" opacity="0.75"></rect>
      <line x1="${f(frame.xScale(row.median))}" x2="${f(frame.xScale(row.median))}" y1="${f(cy - 10)}" y2="${f(cy + 10)}" stroke="#17201d" stroke-width="2"></line>
    `;
  }).join("");
  const zero = min < 0 ? `<line class="vchart-axis" x1="${f(frame.xScale(0))}" x2="${f(frame.xScale(0))}" y1="${f(frame.pad.top)}" y2="${f(frame.plotBottom)}"></line>` : "";
  const svg = `${svgOpen(width, frame.height, spec)}${frame.grid}${zero}${frame.labelText}${boxes}${frame.axisLabel}<g class="vchart-cursor" hidden></g></svg>`;
  const locate = (px, py) => {
    const row = spec.rows[frame.rowAt(py)];
    if (!row) return null;
    const content = spec.tooltip(row);
    return { x: px, marks: [], html: tooltipHtml(content.header, content.rows), yHint: py };
  };
  return { svg, help: touchHelp(false), layout: { type: "free", locate } };
}

// ---------------------------------------------------------------------------
// Facets: several line charts sharing a y domain
// ---------------------------------------------------------------------------

/*
spec = { kind: "facets", key, title, notes, caption, facets: [{ title, spec }], legendSeries: [...] }
*/
function drawFacets(spec, instance) {
  const ys = spec.facets.flatMap((facet) => facet.spec.series.flatMap((series) => series.points.map((point) => point.y))).filter(Number.isFinite);
  const domain = [Math.min(0, ...ys), Math.max(...ys)];
  const html = `<div class="vchart-facet-grid">${spec.facets.map((facet, index) => `
    <div class="vchart-facet"><div class="vchart-facet-title">${escapeHtml(facet.title)}</div><div data-vchart-facet="${index}"></div></div>
  `).join("")}</div>`;
  const legend = legendHtml({ series: spec.legendSeries, legend: "static" }, instance);
  return {
    svg: "",
    plot: false,
    html,
    legend,
    interactive: false,
    after: (target) => {
      spec.facets.forEach((facet, index) => {
        const child = target.querySelector(`[data-vchart-facet="${index}"]`);
        renderChart(child, { ...facet.spec, key: `${spec.key}:${index}`, y: { ...facet.spec.y, domain }, legend: false, endLabels: false, aspect: 0.75, maxHeight: 340 });
      });
    }
  };
}

const RENDERERS = {
  line: drawLine,
  bars: drawBars,
  heatmap: drawHeatmap,
  scatter: drawScatter,
  hbars: drawHBars,
  box: drawBox,
  facets: drawFacets
};

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function attachEvents(target, instance) {
  let drag = null;
  let touchActive = false;

  const plotPoint = (event) => {
    const plot = event.target.closest && event.target.closest(".vchart-plot");
    if (!plot) return null;
    const svg = plot.querySelector("svg");
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    return { plot, svg, px: event.clientX - rect.left, py: event.clientY - rect.top, rect };
  };

  const ownsPlot = (plot) => plot && plot.parentElement && plot.parentElement.parentElement === target;

  target.addEventListener("pointermove", (event) => {
    const hit = plotPoint(event);
    if (!hit || !ownsPlot(hit.plot)) return;
    if (drag) {
      updateDrag(hit, drag);
      return;
    }
    if (event.pointerType === "mouse" || touchActive) show(target, instance, hit, event.pointerType);
  });

  target.addEventListener("pointerdown", (event) => {
    const hit = plotPoint(event);
    if (!hit || !ownsPlot(hit.plot)) return;
    if (event.pointerType === "mouse") {
      const layout = instance.layout;
      if (layout && layout.zoomable && event.button === 0 && hit.px >= layout.plotLeft && hit.px <= layout.plotRight) {
        drag = { start: hit.px, svg: hit.svg, layout };
        event.preventDefault();
      }
      return;
    }
    touchActive = true;
    show(target, instance, hit, event.pointerType);
  });

  target.addEventListener("pointerup", (event) => {
    touchActive = false;
    if (!drag) return;
    const hit = plotPoint(event);
    const current = drag;
    drag = null;
    const box = current.svg.querySelector(".vchart-zoom");
    if (box) box.setAttribute("hidden", "");
    if (!hit) return;
    const { layout } = current;
    const a = Math.min(Math.max(current.start, layout.plotLeft), layout.plotRight);
    const b = Math.min(Math.max(hit.px, layout.plotLeft), layout.plotRight);
    if (Math.abs(b - a) < 8) return;
    instance.zoom = [layout.xScale.invert(Math.min(a, b)), layout.xScale.invert(Math.max(a, b))];
    draw(target, instance);
  });

  target.addEventListener("pointercancel", () => {
    touchActive = false;
    drag = null;
  });

  target.addEventListener("pointerleave", (event) => {
    if (event.pointerType === "mouse" && !drag) hide(target);
  });

  target.addEventListener("dblclick", (event) => {
    if (!instance.zoom || !event.target.closest(".vchart-plot")) return;
    instance.zoom = null;
    draw(target, instance);
  });

  target.addEventListener("click", (event) => {
    const legendButton = event.target.closest("[data-vchart-series]");
    if (legendButton && target.contains(legendButton) && legendButton.closest(".vchart").parentElement === target) {
      const id = legendButton.dataset.vchartSeries;
      if (instance.hidden.has(id)) instance.hidden.delete(id);
      else instance.hidden.add(id);
      draw(target, instance);
      return;
    }
    if (event.target.closest("[data-vchart-download]") && instance.spec && instance.spec.download) {
      downloadCsv(instance.spec.download);
      return;
    }
    if (event.target.closest("[data-vchart-reset]")) {
      instance.zoom = null;
      draw(target, instance);
    }
  });

  target.addEventListener("keydown", (event) => {
    const plot = event.target.closest(".vchart-plot");
    if (!plot || !ownsPlot(plot) || !instance.layout || instance.layout.type !== "x") return;
    if (event.key === "Escape") {
      hide(target);
      return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const svg = plot.querySelector("svg");
    const probe = instance.layout.locate(instance.layout.plotLeft, 0);
    if (!probe) return;
    const current = instance.cursor ?? (event.key === "ArrowLeft" ? probe.count : -1);
    let next = current + (event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0);
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = probe.count - 1;
    next = Math.min(Math.max(next, 0), probe.count - 1);
    instance.cursor = next;
    const px = probe.xAt(next);
    show(target, instance, { plot, svg, px, py: instance.layout.plotTop || 0, rect: svg.getBoundingClientRect() }, "keyboard");
  });

  document.addEventListener("pointerdown", (event) => {
    if (!target.contains(event.target)) hide(target);
  });
}

function updateDrag(hit, drag) {
  const box = drag.svg.querySelector(".vchart-zoom");
  if (!box) return;
  const { plotLeft, plotRight } = drag.layout;
  const a = Math.min(Math.max(drag.start, plotLeft), plotRight);
  const b = Math.min(Math.max(hit.px, plotLeft), plotRight);
  box.removeAttribute("hidden");
  box.setAttribute("x", Math.min(a, b));
  box.setAttribute("width", Math.abs(b - a));
}

function show(target, instance, hit, pointerType) {
  const layout = instance.layout;
  if (!layout) return;
  const found = layout.locate(hit.px, hit.py);
  const tip = hit.plot.querySelector(".vchart-tip");
  const cursor = hit.svg.querySelector(".vchart-cursor");
  if (!found) {
    hide(target);
    return;
  }
  if (found.index !== undefined) instance.cursor = found.index;
  if (cursor) {
    const crosshair = cursor.querySelector(".vchart-crosshair");
    if (crosshair) {
      crosshair.setAttribute("x1", found.x);
      crosshair.setAttribute("x2", found.x);
    }
    const heatCursor = cursor.querySelector(".vchart-heat-cursor");
    if (heatCursor && found.cell) {
      heatCursor.setAttribute("x", found.cell.x);
      heatCursor.setAttribute("y", found.cell.y);
    }
    cursor.querySelectorAll(".vchart-mark").forEach((mark) => mark.remove());
    found.marks.forEach((mark) => {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("class", `vchart-mark${mark.ring ? " ring" : ""}`);
      circle.setAttribute("cx", mark.cx);
      circle.setAttribute("cy", mark.cy);
      circle.setAttribute("r", mark.r || 4);
      circle.style.setProperty("--mark", mark.color);
      cursor.appendChild(circle);
    });
    cursor.removeAttribute("hidden");
  }
  if (!tip) return;
  tip.innerHTML = found.html;
  tip.hidden = false;
  const plotWidth = hit.plot.clientWidth;
  const tipWidth = tip.offsetWidth;
  const tipHeight = tip.offsetHeight;
  const anchorY = pointerType === "keyboard" ? (found.yHint ?? 0) : hit.py;
  let left = found.x + 14;
  if (left + tipWidth > plotWidth - 4) left = found.x - tipWidth - 14;
  left = Math.min(Math.max(left, 4), Math.max(plotWidth - tipWidth - 4, 4));
  let top = pointerType === "touch" ? anchorY - tipHeight - 28 : anchorY - tipHeight / 2;
  top = Math.min(Math.max(top, 2), Math.max(hit.plot.clientHeight - tipHeight - 2, 2));
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function hide(target) {
  target.querySelectorAll(":scope > .vchart .vchart-tip").forEach((tip) => { tip.hidden = true; });
  target.querySelectorAll(":scope > .vchart .vchart-cursor").forEach((cursor) => cursor.setAttribute("hidden", ""));
}


// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------

/** Build CSV text. Cells that a spreadsheet would run as a formula are prefixed with '. */
export function toCsv(columns, rows) {
  const cell = (value) => {
    if (value === null || value === undefined) return "";
    let text = String(value);
    if (/^[=+\-@\t\r]/.test(text) && typeof value !== "number") text = `'${text}`;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns.map(cell).join(","), ...rows.map((row) => columns.map((column) => cell(row[column])).join(","))].join("\r\n");
}

function downloadCsv({ filename, columns, rows }) {
  const cols = columns && columns.length ? columns : Object.keys(rows[0] || {});
  // The byte-order mark makes Excel open Hebrew text correctly.
  const blob = new Blob(["\ufeff", toCsv(cols, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filename || "data"}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
