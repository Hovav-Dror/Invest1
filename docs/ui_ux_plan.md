# UI/UX Review and Numbered Plan

This plan is written so each item can be referenced later by number, for example: "do 1.2" or "start with 4.1".

## Quick Opinion

The app is already useful and thoughtful. The strongest parts are the Hebrew RTL layout, the clear educational tone, the many chart views, the loading skeletons, and the fact that charts already support tooltips, zoom, legends, and explanatory text.

The biggest weakness is not the calculations. It is that the screen can feel heavy: long text, many controls, charts, metrics, and tables all compete for attention. A non-professional user may understand each part separately, but still feel unsure what to look at first.

The right direction is to make the app feel more guided: clear first takeaway, simpler controls at first glance, easier navigation, shareable links, better chart/table export, and better mobile behavior.

## What In The Existing Review Is Right

### R1. Long Story Text Can Be Too Much

Correct. Many views have long explanation sections before and after the chart. This is valuable content, but it can make the page feel like an article before the user reaches the tool.

Simple meaning: the app explains well, but sometimes explains too much at once.

### R2. Mobile Navigation Is Cramped

Correct. On small screens the sidebar becomes a horizontal scrolling menu. With many views, users may not notice that more items are hidden off-screen.

Simple meaning: on phone, the menu can feel like a strip you need to chase.

### R3. URL Sharing Is Missing

Correct. The current hash stores only the view, not the selected parameters. Sharing or refreshing a page loses the exact setup.

Simple meaning: if you build an interesting comparison, you cannot send someone the same comparison.

### R4. Tables Need Export And Better Signals

Correct. The table is capped and there is no CSV download. The note that only some rows/columns are shown is quiet.

Simple meaning: people who want to inspect the numbers need a better way to take the data with them.

### R5. Chart Accessibility Needs Work

Correct. The charts are visual SVGs. A screen reader user needs a text summary of what the chart shows.

Simple meaning: the chart should also explain itself in words for people who cannot use the visual chart well.

### R6. Tooltip Position Can Clip

Correct. Tooltip position is currently based on cursor + fixed offset. On small screens it can go outside the visible screen.

Simple meaning: the little hover box can partly disappear.

### R7. Visual Hierarchy Can Improve

Correct. Metrics, chart colors, story emphasis, and table notes can do a better job telling the user what matters most.

Simple meaning: the page has the information, but not always a strong "look here first" signal.

## What In The Existing Review Is Not Quite Right

### N1. The App Does Not Appear To Have 14 Top-Level Views

The current code has 12 top-level navigation views. Some views contain multiple charts or sub-sections, so it may feel like more than 12, but the top-level count is not 14.

### N2. The "חשב" Button Comment Looks Outdated

The review says every change requires pressing "חשב". In the current code, the controls already auto-run after input/change with a short delay. I did not find an inline "חשב" submit button in the main control rendering path.

So the right plan is not "add auto-run from scratch". The right plan is "make auto-run clearer, avoid too many runs while typing, and show when a result is updating".

### N3. The Review Says Chart Help May Be Missing, But It Exists

The code already renders chart help text in several chart types, and there is also chart reading content. The problem is not total absence. The problem is discoverability and density.

Simple meaning: help exists, but it could be easier to notice and less text-heavy.

### N4. The Palette Criticism Is Only Partly True

The main palette already starts with the site colors. Some specific chart areas still use custom colors like orange or purple. The plan should be to standardize the exceptions, not repaint everything.

### N5. Dark Theme Is Nice, But Not A First Priority

A dark theme would be good, but it is not as important as shareable links, simpler reading, better controls, export, and mobile navigation.

## Numbered UI/UX Plan

## 1. Make Every View Easier To Understand First

### 1.1 Add A Short Takeaway At The Top Of Each View

Add one short sentence near the title that says the main point of the view.

Example: "אירועי מס חוזרים יכולים להקטין את התוצאה הסופית בצורה גדולה לאורך זמן."

Why: users should know what question the page answers before touching controls.

### 1.2 Collapse Long Story Sections

Show only the first 2-3 paragraphs by default. Add a "קרא עוד" button to expand the full explanation.

Why: keeps the depth, but makes the first screen lighter.

### 1.3 Pull "בשורה התחתונה" Into A Highlight Box

When a story section contains a bottom-line sentence, show it as a clear callout above or near the chart.

Why: many users scan. They need the conclusion before the details.

### 1.4 Reduce Warning Red For Normal Emphasis

Use warning red only for real warnings. Use accent green/brown or bold text for normal emphasis.

Why: too much red makes normal educational text feel alarming.

## 2. Improve Navigation And Flow

### 2.1 Add Previous / Next View Buttons

At the bottom of each non-static view, add "הקודם" and "הבא" buttons based on the recommended reading order.

Why: after finishing a view, users should not need to hunt in the menu.

### 2.2 Mark The Recommended Path In The Menu

Add small numbers or badges to the main recommended learning path.

Why: users can understand what to read first and what is optional/reference.

### 2.3 Replace Mobile Horizontal Menu With A Drawer

On phone, use a menu button that opens the full navigation from the right.

Why: 12 views are too many for a horizontal strip.

### 2.4 Update The Browser Title On Navigation

When the user changes view, update `document.title` to include the current view title.

Why: browser history and shared links become easier to understand.

## 3. Make Controls Feel Simpler

### 3.1 Split Controls Into Basic And Advanced

Keep the most important controls visible. Put less common controls under "עוד פרמטרים".

Good first target: the kupat-gemel view, because it has age, start year, pension months, CPI, and fee inputs.

Why: users should not see every possible setting before they understand the page.

### 3.2 Add A Visible Reset To Defaults Button

Add "ברירות מחדל" near the controls.

Why: users can experiment without fear of getting lost.

### 3.3 Make Auto-Run State Clear

When the app is recalculating, show a clear updating state near the controls and chart.

Why: auto-run already exists, but users need to know whether the chart is current or still refreshing.

### 3.4 Avoid Recalculating Too Aggressively While Typing

For text/number fields, run after a pause or when the field loses focus. For sliders and checkboxes, run on change.

Why: smoother feel, fewer unnecessary API calls.

### 3.5 Add Pending-Changes Indicator If Needed

If a field changed but the chart has not updated yet, show a small dot or text such as "מעדכן...".

Why: users should not wonder if the chart matches the controls.

## 4. Improve Date Range Controls

### 4.1 Add Date Inputs Below The Slider

Add two small inputs for start and end date. They should stay synced with the slider.

Why: dragging is good for exploration, typing is better for exact dates.

### 4.2 Add Date Presets

Add chips such as:

- "10 שנים אחרונות"
- "מאז 2000"
- "כל הטווח"

Why: common choices should take one click.

### 4.3 Improve Mobile Label Layout

When labels overlap on small screens, stack the dates under the slider instead of squeezing them above the handles.

Why: prevents cramped and clipped labels.

## 5. Make Charts More Useful

### 5.1 Clamp Tooltip Position To The Screen

Keep the tooltip inside the viewport.

Why: hover text should never disappear outside the screen.

### 5.2 Add Chart Action Menu

Add actions near charts:

- copy share link
- download CSV
- save chart as PNG

Why: this turns the app from a private explorer into something users can share and reuse.

### 5.3 Add Difference Mode Where Useful

For tax and fee views, add a toggle between:

- absolute value
- difference from baseline

Why: the main story is often the gap, not the absolute line.

### 5.4 Improve End Labels

Prevent end-of-line labels from colliding. If needed, show only the hovered label or nudge labels apart.

Why: labels should help, not create visual noise.

### 5.5 Standardize Special Chart Colors

Keep the existing main palette, but replace one-off colors where they clash.

Why: the app should feel like one product.

## 6. Make Results Shareable And Persistent

### 6.1 Save Parameters In The URL

Put the current view parameters in the URL query string or hash query.

Example idea: `#tax-events?start=2000-01-01&end=2026-01-01&adjust_cpi=true`

Why: users can share the exact result they are seeing.

### 6.2 Load Parameters From The URL

When opening a shared link, hydrate controls before the first calculation.

Why: shared links must reproduce the same screen.

### 6.3 Add Local Resume Later

Optionally save last-used settings per view in `localStorage`.

Why: users can come back and continue where they left off.

## 7. Improve Metrics

### 7.1 Highlight The Best Or Most Important Metric

In comparison views, visually mark the better scenario or the main result.

Why: users should not need to compare four similar cards by hand.

### 7.2 Show Deltas Against A Baseline

Add labels like "+₪200,000 מול מימוש חודשי" where relevant.

Why: the difference is often easier to understand than the raw value.

### 7.3 Connect Metric Colors To Chart Series

Use the same color dot/accent on metric cards and chart lines.

Why: users can connect number cards to chart lines faster.

## 8. Improve Tables

### 8.1 Make The Row Limit Notice More Visible

Show "מוצגות X מתוך Y שורות" as a stronger badge near the table title.

Why: users should know if they are seeing a partial table.

### 8.2 Add CSV Download

Download the full current table data, not only the visible 250 rows.

Why: serious users will want the data.

### 8.3 Add Column Sorting

Click table headers to sort.

Why: makes the table useful for investigation, not just display.

### 8.4 Consider Search Or Filter Later

Add search/filter only after CSV and sorting.

Why: export and sorting give more value first.

## 9. Accessibility Pass

### 9.1 Add Screen Reader Chart Summaries

Generate hidden text for each chart that explains:

- chart type
- main series
- final values or main result

Why: users who cannot read the visual chart still deserve the result.

### 9.2 Improve Keyboard Access For Chart Controls

Make legend toggles, reset zoom, and chart actions reachable and clear with keyboard.

Why: mouse-only tools exclude some users.

### 9.3 Improve Focus Rings On Custom Sliders

Make sure Chrome, Safari, and Firefox all show a visible focus ring.

Why: keyboard users need to see where they are.

### 9.4 Slightly Darken Muted Text

Move muted text toward stronger contrast.

Why: small grey text can be hard to read.

## 10. Performance And Packaging

### 10.1 Minify JS And CSS For Production

Use a production build step to minify static assets.

Why: faster load, especially on mobile.

### 10.2 Enable Compression

Serve static JS/CSS with gzip or brotli in production.

Why: large files transfer much faster.

### 10.3 Convert Large PNG To WebP

Use WebP for large images, with fallback only if needed.

Why: less download time.

### 10.4 Lazy-Load Story Images

Add `loading="lazy"` to non-critical images.

Why: first page load should focus on the visible content.

## 11. Small Polish

### 11.1 Add Favicon

Use a small chart icon or Hebrew letter.

Why: makes the app feel finished in the browser tab.

### 11.2 Add Noscript Message

Show a simple message if JavaScript is disabled.

Why: the app depends on JavaScript.

### 11.3 Improve Error Display

Use a clearer dismissible error banner or inline error panel.

Why: errors should be noticeable but not feel like the app broke.

### 11.4 Add Keyboard Shortcut Later

Possible shortcuts:

- `?` for help
- arrow keys for previous/next view
- `Cmd/Ctrl+Enter` to force recalculate

Why: useful for repeat users, but not urgent.

## Suggested Order

### Phase 1: Highest Value

1. 6.1 Save parameters in the URL
2. 6.2 Load parameters from the URL
3. 1.1 Add top takeaway
4. 1.2 Collapse long story sections
5. 5.1 Clamp tooltip position
6. 8.2 Add CSV download

### Phase 2: Make The App Feel Guided

1. 2.1 Add previous/next view buttons
2. 2.2 Mark recommended path
3. 3.1 Split controls into basic and advanced
4. 3.2 Add reset to defaults
5. 7.1 Highlight best/important metric
6. 7.2 Show deltas against baseline

### Phase 3: Mobile And Accessibility

1. 2.3 Mobile navigation drawer
2. 4.1 Date inputs below slider
3. 4.2 Date presets
4. 9.1 Screen reader chart summaries
5. 9.3 Custom slider focus rings
6. 9.4 Darken muted text

### Phase 4: Exports, Polish, Performance

1. 5.2 Chart action menu
2. 5.3 Difference mode
3. 8.3 Column sorting
4. 10.1 Minify JS/CSS
5. 10.2 Enable compression
6. 11.1 Add favicon

## My Recommended First Five Tasks

If you want the biggest improvement with the least confusion, start here:

1. 6.1 and 6.2: shareable URLs with parameters.
2. 1.1: one short takeaway at top of each view.
3. 1.2: collapse long story sections.
4. 8.2: CSV download.
5. 5.1: fix tooltip clipping.

These make the app easier to share, easier to understand, and less frustrating without changing the investment logic.
