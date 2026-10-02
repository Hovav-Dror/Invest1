// The URL hash holds the view and any settings that differ from the defaults,
// for example "#trinity?yearly_draw=5&p1.window=20". Old links ("#trinity")
// keep working.

export function parseHash(hash) {
  const text = String(hash || "").replace(/^#/, "");
  const [viewId, query = ""] = text.split("?");
  return { viewId: decodeURIComponent(viewId || ""), params: new URLSearchParams(query) };
}

/** Entries that differ from ``defaults`` (both are [key, value] lists), as a hash string. */
export function buildHash(viewId, entries, defaults = []) {
  const defaultMap = new Map(defaults);
  const params = new URLSearchParams();
  entries.forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (defaultMap.has(key) && String(defaultMap.get(key)) === String(value)) return;
    params.set(key, String(value));
  });
  const query = params.toString();
  return `#${encodeURIComponent(viewId)}${query ? `?${query}` : ""}`;
}

/** Keys with ``prefix.`` stripped, e.g. scoped("p1", params) for panel 1. */
export function scoped(prefix, params) {
  const result = [];
  params.forEach((value, key) => {
    if (prefix === "" && !key.includes(".")) result.push([key, value]);
    else if (prefix && key.startsWith(`${prefix}.`)) result.push([key.slice(prefix.length + 1), value]);
  });
  return result;
}

export function prefixed(prefix, entries) {
  return entries.map(([key, value]) => [prefix ? `${prefix}.${key}` : key, value]);
}

/** Set form fields inside ``root`` from [name, value] entries. Lists are comma separated. */
export function applyEntries(root, entries) {
  entries.forEach(([name, value]) => {
    const inputs = [...root.querySelectorAll(`[name="${CSS.escape(name)}"]`)];
    if (!inputs.length) return;
    const values = String(value).split(",");
    inputs.forEach((input) => {
      if (input.type === "checkbox") {
        input.checked = inputs.length > 1 ? values.includes(input.value) : String(value) === "true" || String(value) === input.value;
      } else if (input.type === "radio") {
        input.checked = input.value === String(value);
      } else {
        input.value = String(value);
      }
    });
  });
}
