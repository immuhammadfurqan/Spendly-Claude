# Spec: Backend Routes for Profile Page

## Overview
Step 4 built the profile UI against hardcoded Python dicts. Step 5 replaces
that fake data with real queries against the `users` and `expenses` tables
for the currently logged-in user. The `/profile` route will load the user
record by `session["user_id"]`, fetch their expenses, and compute the same
shape of context (`user`, `stats`, `transactions`, `breakdown`) the existing
template already consumes. The template contract from Step 4 stays
untouched — only `app.py` (and a small DB helper) change. This is the first
step where real per-user data flows from the database into a logged-in view,
establishing the read-query pattern that Steps 7–9 will build on.

## Depends on
- Step 1 — Database setup (`users`, `expenses` tables exist; `get_db()` available)
- Step 2 — Registration (user rows must be insertable)
- Step 3 — Login and Logout (session sets `user_id`)
- Step 4 — Profile page UI (template + CSS already in place)

## Routes
- `GET /profile` — render the profile page with real DB data — logged-in only
  (redirect to `/login` if `session.get("user_id")` is missing)

No new routes. The existing `/profile` view is rewritten to query the DB.

## Database changes
No database changes. The existing `users` and `expenses` tables are
sufficient. Verified against `database/db.py`:
- `users(id, name, email, password_hash, created_at)`
- `expenses(id, user_id, amount, category, date, description, created_at)`

## Templates
- **Create:** none
- **Modify:** none — `templates/profile.html` is consumed as-is. The Python
  context must keep the same keys the template already reads:
  - `user.initial`, `user.name`, `user.email`, `user.member_since`
  - `stats.total_spent`, `stats.tx_count`, `stats.top_category`
  - `transactions[*].date`, `.description`, `.category`, `.category_label`,
    `.icon`, `.amount`
  - `breakdown[*].category_label`, `.amount`, `.percent`, `.bar_class`, `.icon`

## Files to change
- `app.py`
  - Replace the hardcoded `profile()` view (currently lines ~110–172) with:
    1. Auth guard — `if not session.get("user_id"): return redirect(url_for("login"))`
    2. Open DB via `get_db()`; query the user row by id
       (`SELECT id, name, email, created_at FROM users WHERE id = ?`)
    3. If the row is missing (stale session), clear the session and redirect
       to `/login`
    4. Query the user's expenses ordered by date DESC
       (`SELECT amount, category, date, description FROM expenses
       WHERE user_id = ? ORDER BY date DESC, id DESC`)
    5. Build the `user`, `stats`, `transactions`, `breakdown` dicts from the
       query results using helpers from `database/queries.py`
    6. Close the connection, render `profile.html`

- `database/queries.py` (new — see *Files to create*)
  - All formatting and aggregation helpers live here so `app.py` stays
    thin and the logic is unit-testable later.

## Files to create
- `database/queries.py` — pure helpers (no Flask, no I/O beyond the rows
  passed in). Functions:
  - `build_user_context(user_row) -> dict` — returns
    `{"name", "email", "initial", "member_since"}`
    - `initial`: first character of `name`, uppercased; fall back to `"?"`
      if name is empty
    - `member_since`: parse `created_at` (`YYYY-MM-DD HH:MM:SS`) and format
      as `"%b %Y"` (e.g. `"May 2026"`)
  - `build_stats(expense_rows) -> dict` — returns
    `{"total_spent", "tx_count", "top_category"}`
    - `total_spent`: sum of `amount`, rendered as `format_amount(total)`
    - `tx_count`: `len(expense_rows)`
    - `top_category`: the category with the highest summed amount; if there
      are no expenses, use the literal string `"—"`
  - `build_transactions(expense_rows) -> list[dict]` — one dict per row with
    the keys the template expects:
    - `date`: `"%b %d"` formatted (e.g. `"May 01"`)
    - `description`: pass through; if blank, use the category label
    - `category`: lowercase slug for the CSS class (`food`, `transport`,
      `bills`, `health`, `entertainment`, `shopping`, `other`)
    - `category_label`: title-case display name
    - `icon`: lucide icon slug from the `CATEGORY_ICONS` map
    - `amount`: `format_amount(row_amount)`
  - `build_breakdown(expense_rows) -> list[dict]` — one dict per category
    that appears in the user's expenses, sorted by total spent DESC:
    - `category_label`, `amount` (formatted), `icon`
    - `percent`: integer `round(category_total / max_category_total * 100)`,
      clamped to `[0, 100]`; if there are no expenses, return an empty list
    - `bar_class`: cycled from `["lbar-fill--purple", "lbar-fill--orange",
      "lbar-fill--blue"]` by sort-order index
  - `format_amount(value: float) -> str` — `"₹" + f"{int(round(value)):,}"`
    (matches the rendered format Step 4 used — integer rupees with comma
    thousands separators)
  - Module-level constants:
    - `CATEGORY_ICONS = {"food": "utensils", "transport": "car",
      "bills": "zap", "health": "heart-pulse", "entertainment": "film",
      "shopping": "shopping-bag", "other": "more-horizontal"}`
    - `BAR_CLASSES = ("lbar-fill--purple", "lbar-fill--orange", "lbar-fill--blue")`
    - `KNOWN_CATEGORIES = set(CATEGORY_ICONS.keys())` — any expense whose
      stored category is not in this set is bucketed as `"other"` for both
      `category` and `icon`, with the original string used as the
      `category_label`

## New dependencies
No new dependencies. Only the Python standard library (`datetime`) and the
existing `sqlite3` + `flask` modules are used.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values (no CSS work in this step)
- All templates extend `base.html` (no template changes in this step)
- Do not modify `templates/profile.html` — the template contract from
  Step 4 must be preserved exactly
- Always close the DB connection (`conn.close()`), including on the
  stale-session early-return path
- Auth guard pattern stays consistent with the rest of `app.py`:
  inline `session.get("user_id")` check, no decorators
- All currency rendering goes through `format_amount` — never inline
  `"₹" + str(...)` in the view
- All date rendering goes through helpers in `queries.py` — no `strftime`
  calls in `app.py`
- Lowercase categories before lookup so legacy seed rows stored as
  `"Food"` / `"Bills"` etc. still map correctly
- Unknown categories must not crash the page — they get bucketed as
  `"other"` with the original label preserved for display
- Empty-expense case must render without errors: `stats.total_spent`
  shows `"₹0"`, `tx_count` is `0`, `top_category` is `"—"`, and the
  transactions / breakdown lists are empty (the template's `{% for %}`
  loops handle empty lists naturally)

## Definition of done
- [ ] `GET /profile` while logged out redirects to `/login`
- [ ] `GET /profile` while logged in returns HTTP 200
- [ ] The user info card shows the **logged-in user's** real name and
      email (not "Demo User" / "demo@spendly.com" unless that is the
      actual logged-in account)
- [ ] The avatar shows the first letter of the logged-in user's name,
      uppercased
- [ ] "Member since {Mon YYYY}" is derived from the user's `created_at`,
      not hardcoded
- [ ] `stats.total_spent` equals the sum of the logged-in user's
      `expenses.amount`, formatted as `₹` + integer rupees with comma
      thousands separators
- [ ] `stats.tx_count` equals the row count of the user's expenses
- [ ] `stats.top_category` is the category with the highest summed amount
      for that user (or `"—"` if they have no expenses)
- [ ] The transactions table renders one row per expense, ordered by
      date DESC, with date formatted as `"Mon DD"` (e.g. `"May 16"`)
- [ ] Each transaction row's category badge uses a lowercase slug class
      (`cat-badge--food`, etc.) that matches the existing CSS
- [ ] The category breakdown section lists every distinct category the
      user has expenses in, sorted by total spend DESC
- [ ] Breakdown bar widths are computed from real data — the largest
      category renders at 100% and others scale proportionally
- [ ] Registering a new user, logging in as them, and visiting `/profile`
      shows zero expenses gracefully (no exceptions, empty table, empty
      breakdown, `₹0` total, `—` top category)
- [ ] A user with a `category` value not in the known set (e.g. `"Misc"`)
      renders without crashing, bucketed visually as "Other" but keeping
      the stored label in the badge
- [ ] No DB connection leaks — every code path through `profile()`
      closes the connection
- [ ] No hardcoded user data (Demo User, ₹18,240, etc.) remains in `app.py`
- [ ] `templates/profile.html` is byte-identical to its Step 4 state
- [ ] App starts without errors and `pytest` (no new tests required) still
      exits cleanly
