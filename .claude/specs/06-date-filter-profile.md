# Spec: Date Filter for Profile Page

## Overview
The profile page currently shows every expense the logged-in user has ever
recorded — stats, transactions, and the category breakdown all aggregate the
full history. This step adds a date-range filter at the top of `/profile` so
users can narrow the view to a specific window (e.g. "this month", "last 30
days", or a custom `start`–`end` range). The filter is driven by GET query
parameters (`start` and `end` as `YYYY-MM-DD`), keeps the page bookmarkable
and shareable, and feeds the same `build_stats` / `build_transactions` /
`build_breakdown` helpers from Step 5 — only the SQL `WHERE` clause and a
small context block change. This is the first step that introduces
user-controlled query parameters on a logged-in view and sets the pattern
Steps 7–9 will reuse for expense CRUD filtering.

## Depends on
- Step 1 — Database setup (`expenses.date` column exists)
- Step 2 — Registration
- Step 3 — Login and Logout (session sets `user_id`)
- Step 4 — Profile page UI
- Step 5 — Profile backend (real DB queries + `database/queries.py` helpers)

## Routes
- `GET /profile?start=YYYY-MM-DD&end=YYYY-MM-DD&preset=<key>` — render the
  profile page filtered to the given date window — logged-in only
  (redirect to `/login` if `session.get("user_id")` is missing)

No new routes. The existing `/profile` view is extended to read query params
and apply them to the expense query.

## Database changes
No database changes. The existing `expenses.date` column (stored as
`TEXT` in `YYYY-MM-DD`) supports lexicographic range comparisons.
Verified against `database/db.py`.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Insert a new `<form>` filter bar directly above the `profile-stats`
    block (after `profile-hero`). The form posts via `GET` to
    `url_for('profile')` so the active range lives in the URL.
  - Filter bar contains:
    - A row of preset buttons (links): **All time**, **This month**,
      **Last 30 days**, **This year**. Each is a plain `<a>` pointing to
      `/profile?preset=<key>` so they are bookmarkable and require no JS.
    - Two `<input type="date">` fields named `start` and `end`, pre-filled
      with the currently active range (echoed back from the view context).
    - A submit button labelled **Apply** and a "Clear" link to `/profile`.
  - The active preset link gets a `filter-preset--active` class.
  - Add a small "Showing {N} transactions from {start_display} to
    {end_display}" caption below the form (or "Showing all transactions"
    when no range is active).
  - The three existing `profile-stat-note` spans currently read
    `"this month"` / `"this month"` / `"by spend"` — change the first two
    to render the active range label from context
    (`{{ filter.range_label }}`) so the stats describe the actual window
    instead of a hardcoded string.

## Files to change
- `app.py`
  - Extend the `profile()` view:
    1. Keep the existing auth guard and stale-session redirect.
    2. Read `start`, `end`, and `preset` from `request.args`.
    3. Resolve the active window via a new helper
       `resolve_date_range(args, today)` in `database/queries.py` (see
       *Files to create / change* below). The helper returns a dict with
       `{"start", "end", "preset", "range_label", "start_display",
       "end_display", "is_active", "error"}`. Bad input (malformed dates,
       `start > end`) returns `is_active=False` and an `error` string the
       template can surface; the view treats this as "no filter".
    4. Build the expense query with a parameterised `WHERE` clause:
       `WHERE user_id = ?` plus `AND date >= ?` / `AND date <= ?` only
       when the corresponding bound is set. Always parameterise — never
       string-format the dates into the SQL.
    5. Pass the resolved filter dict to the template as `filter=...`
       alongside the existing `user`, `stats`, `transactions`, `breakdown`.
  - Import `date` from `datetime` (or `datetime.date.today()`) at module
    top.

- `database/queries.py`
  - Add `resolve_date_range(args, today)` — pure function, no Flask, no
    DB. `args` is a `Mapping[str, str]` (works with both `request.args`
    and plain dicts). `today` is a `date` injected by the view so the
    function stays testable.
  - Add module-level constant `DATE_PRESETS` listing preset keys and
    human labels (used to render the preset buttons and to validate the
    `preset` arg). Suggested keys:
    `("all", "All time")`, `("month", "This month")`,
    `("30d", "Last 30 days")`, `("year", "This year")`.

## Files to create
- None. All Python logic lives in `database/queries.py`; all markup
  changes go into `templates/profile.html`; all styling goes into
  `static/css/style.css`.

## New dependencies
No new dependencies. Only `datetime` (already imported in
`database/queries.py`) is needed.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- Parameterised queries only — never string-format SQL, including the
  new `date` bounds
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values. New filter-bar styles
  must reuse the existing palette (`--accent`, `--accent-2`, `--paper`,
  `--ink`, `--muted`, etc.)
- All templates extend `base.html` (no new templates in this step)
- Do **not** add JavaScript for the filter — the form is a plain
  `method="GET"` submit, and the preset buttons are plain `<a>` links.
  Filter state must survive a hard reload via the URL alone.
- Date inputs use `<input type="date">` with `name="start"` / `name="end"`
  — no third-party datepicker library.
- All date parsing and validation lives in `resolve_date_range` in
  `database/queries.py`. The view does no `strftime`/`strptime` and no
  date arithmetic.
- Range semantics are **inclusive** on both bounds: `date >= start AND
  date <= end`. Document this in a one-line comment above the helper.
- An empty / missing / malformed param means "no bound on that side".
  A range with `start > end` is treated as no filter and surfaces a
  friendly `error` message — never raise.
- Explicit `preset=all` and `start`/`end` both empty both map to "no
  filter" (`is_active=False`); only one of `preset` or
  `start`/`end` is honoured per request — if both are present, explicit
  `start`/`end` wins and `preset` is ignored (so manually edited URLs
  behave predictably).
- Preset semantics (computed from the injected `today`):
  - `month` → `start = today.replace(day=1)`, `end = today`
  - `30d`  → `start = today - timedelta(days=29)`, `end = today` (29 so
    the window is exactly 30 days inclusive)
  - `year` → `start = today.replace(month=1, day=1)`, `end = today`
  - `all`  → no bounds
- `range_label` is the human caption shown in the stat notes:
  - active preset → its label from `DATE_PRESETS`
  - custom range → `"{start_display} – {end_display}"`
  - no filter → `"all time"`
- `start_display` / `end_display` are `"%b %d, %Y"` (e.g. `"May 19, 2026"`)
  — the same `datetime` formatting style used elsewhere in `queries.py`.
- Always close the DB connection on every code path (existing rule from
  Step 5 still applies).
- The template contract from Step 5 (`user`, `stats`, `transactions`,
  `breakdown`) is preserved exactly. The only new context key is
  `filter`.
- The empty-result case must render gracefully: applying a range with no
  matching expenses shows `₹0` total, `0` transactions, `"—"` top
  category, empty transactions table, and empty breakdown — exactly the
  behaviour Step 5 already handles for users with no expenses.
- New CSS goes into a clearly-labelled "Profile date filter" section at
  the bottom of `static/css/style.css`, using a `filter-` prefix
  (`.filter-bar`, `.filter-presets`, `.filter-preset`,
  `.filter-preset--active`, `.filter-dates`, `.filter-input`,
  `.filter-actions`, `.filter-caption`, `.filter-error`). Responsive:
  filter bar stacks vertically below 600px so date inputs and preset
  buttons remain tappable.

## Definition of done
- [ ] `GET /profile` (no query string) renders unchanged from Step 5 —
      all expenses shown, stat notes read "all time", no error
- [ ] `GET /profile?preset=month` shows only expenses whose `date` falls
      within the current calendar month (inclusive of today)
- [ ] `GET /profile?preset=30d` shows only expenses in the last 30 days
      (inclusive), and the "This month" preset link is **not** marked
      active
- [ ] `GET /profile?preset=year` shows only expenses in the current
      calendar year
- [ ] `GET /profile?start=2026-05-01&end=2026-05-15` shows only expenses
      whose `date` is between those bounds (inclusive on both ends), and
      no preset link is marked active
- [ ] `GET /profile?start=2026-05-15&end=2026-05-01` (reversed range)
      renders the page with no filter applied and shows a visible
      `filter-error` message explaining the issue — no 500
- [ ] `GET /profile?start=not-a-date` does not raise; the page renders
      unfiltered with an `filter-error` message
- [ ] `GET /profile?start=&end=` (empty strings) renders unfiltered with
      no error
- [ ] When `start` and `end` are both provided in the URL, the `preset`
      query param (if also present) is ignored — explicit range wins
- [ ] `stats.total_spent`, `stats.tx_count`, `stats.top_category`,
      `transactions`, and `breakdown` all reflect only the rows inside
      the active window
- [ ] The two stat notes that previously read "this month" now read the
      active `range_label` (e.g. `"This month"`, `"May 01, 2026 – May
      15, 2026"`, or `"all time"`)
- [ ] The filter bar appears on the page between the profile hero and
      the stat tiles, with: four preset links, two `<input type="date">`
      fields pre-filled with the active range, an Apply submit button,
      and a Clear link to `/profile`
- [ ] The currently-active preset link has the `filter-preset--active`
      class; when a custom `start`/`end` is in effect, no preset link is
      marked active
- [ ] Applying a range with no matching expenses renders the page with
      `₹0` total, `0` transactions, `"—"` top category, empty
      transactions table, and empty breakdown — no exceptions
- [ ] The filter form uses `method="GET"`, so a hard reload preserves
      the active window via the URL alone (no JS, no session storage)
- [ ] SQL uses parameterised bindings for `user_id`, `start`, and `end`
      — no f-strings or concatenation in the query
- [ ] No DB connection leaks — every code path through `profile()`
      closes the connection, including the malformed-input path
- [ ] `templates/profile.html` still extends `base.html`; no inline
      styles or hex colors are introduced
- [ ] `database/queries.py` exposes `resolve_date_range(args, today)`
      and `DATE_PRESETS` at module level
- [ ] `app.py` performs no `strptime` / `strftime` / `timedelta` calls
      — all date logic stays in `queries.py`
- [ ] App starts without errors; `pytest` exits cleanly (no new tests
      required for this spec)
