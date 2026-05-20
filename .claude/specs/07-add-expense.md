# Spec: Add Expense

## Overview
Steps 1–6 stood up authentication, a real profile dashboard, and a date
filter — but every expense the user sees comes from the seed script. This
step gives logged-in users a way to **create** their own expense rows. A
new "Add expense" entry point lives in the navbar and on the profile page;
clicking it opens a dedicated form at `/expenses/add` (amount, category,
date, optional description). Submitting the form validates input, inserts
one row into the `expenses` table scoped to the current `session["user_id"]`,
and redirects back to `/profile` so the new row immediately shows up in the
stats, transactions table, and category breakdown. This is the first
write-path against `expenses` and sets the pattern Steps 8–9 (edit /
delete) will reuse.

## Depends on
- Step 1 — Database setup (`expenses` table exists with `user_id`,
  `amount`, `category`, `date`, `description` columns; `get_db()` available)
- Step 2 — Registration
- Step 3 — Login and Logout (session sets `user_id`)
- Step 4 — Profile page UI
- Step 5 — Profile backend (so the new row is visible after redirect)
- Step 6 — Date filter on profile (the new row honours the active filter
  on return)

## Routes
- `GET  /expenses/add` — render the add-expense form — logged-in only
  (redirect to `/login` if `session.get("user_id")` is missing)
- `POST /expenses/add` — validate and insert one expense for the current
  user, then redirect to `/profile` — logged-in only

The existing `add_expense()` stub in `app.py` is rewritten to accept both
methods. No other routes change.

## Database changes
No database changes. The existing `expenses` table is sufficient:
`expenses(id, user_id, amount, category, date, description, created_at)`.
Verified against `database/db.py`. `user_id` is supplied from
`session["user_id"]`, `created_at` defaults to `datetime('now')`, and
`description` is nullable.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`. Layout:
  - A `expense-form-section` wrapper card centred under the navbar.
  - Heading "Add expense" with a short helper sub-line.
  - A single `<form method="POST" action="{{ url_for('add_expense') }}">`
    containing four `.form-group` blocks reused from the existing auth
    styles:
    1. **Amount** — `<input type="number" name="amount" step="0.01"
       min="0.01" required>` with an inline `₹` adornment.
    2. **Category** — `<select name="category" required>` populated from
       `KNOWN_CATEGORIES` (rendered as title-cased labels: Food,
       Transport, Bills, Health, Entertainment, Shopping, Other). The
       option `value` must be the lowercase slug (matches
       `CATEGORY_ICONS` keys so the profile renders the correct badge
       and icon).
    3. **Date** — `<input type="date" name="date" required>`, defaulting
       to today's date (`date.today().isoformat()`) on first GET.
    4. **Description** — `<input type="text" name="description"
       maxlength="200">` — optional.
  - Submit button labelled "Save expense" using the existing
    `.btn-submit` class.
  - A "Cancel" link back to `/profile`.
  - On validation failure, the view re-renders this template with an
    `error` string shown above the form (same pattern `register.html`
    and `login.html` already use) and echoes the previously submitted
    values back into the inputs so the user does not lose their typing.

- **Modify:** `templates/base.html`
  - In the logged-in branch of the navbar, add an
    `<a href="{{ url_for('add_expense') }}" class="nav-link {% if
    request.endpoint == 'add_expense' %}active{% endif %}">Add
    expense</a>` link **before** the existing Analytics link so the
    primary write action sits to the left.

- **Modify:** `templates/profile.html`
  - Add a single CTA button "Add expense" inside the `profile-hero`
    block (e.g. to the right of `profile-identity`) that links to
    `url_for('add_expense')`. Reuse the existing `.btn-submit` (or
    `.btn-primary`) class — do not introduce a one-off colour.

## Files to change
- `app.py`
  - Rewrite the existing `add_expense()` stub:
    1. Auth guard — `if not session.get("user_id"): return
       redirect(url_for("login"))`.
    2. On `GET`, render `add_expense.html` with the form pre-populated
       (`amount=""`, `category=""`, `date=date.today().isoformat()`,
       `description=""`) and the list of category options passed in as
       context (sourced from `KNOWN_CATEGORIES` / `CATEGORY_ICONS` so
       there is one source of truth).
    3. On `POST`, read `amount`, `category`, `date`, `description` from
       `request.form` and validate (see *Rules*). On any validation
       failure, re-render the form with an `error` string and echo the
       submitted values back; do **not** insert.
    4. On valid input, open `get_db()`, run a parameterised
       `INSERT INTO expenses (user_id, amount, category, date,
       description) VALUES (?, ?, ?, ?, ?)`, commit, close, then
       `redirect(url_for("profile"))`.
  - Keep the `/expenses/<int:id>/edit` and `/expenses/<int:id>/delete`
    stubs untouched — those are Steps 8 and 9.

- `templates/base.html` — see *Templates → Modify*.
- `templates/profile.html` — see *Templates → Modify*.
- `static/css/style.css`
  - Add a clearly-labelled "Add expense form" section at the bottom
    using an `expense-form-` prefix:
    `.expense-form-section`, `.expense-form-card`,
    `.expense-form-title`, `.expense-form-sub`,
    `.expense-form-amount` (for the `₹` adornment wrapper),
    `.expense-form-actions`, `.expense-form-cancel`,
    `.expense-form-error`.
  - All colours must come from the existing CSS variables
    (`--accent`, `--accent-2`, `--paper`, `--ink`, `--muted`, etc.).
    Reuse `.form-group`, `.form-input`, `.btn-submit` from the auth
    styles so the look is consistent. Responsive: the card should
    stretch to the available width with a sensible `max-width`
    (~520px), and inputs stack full-width below 600px.

## Files to create
- `templates/add_expense.html` — described above.

## New dependencies
No new dependencies. Only the standard library (`datetime`) and the
already-imported `sqlite3` + `flask` modules are needed.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`.
- Parameterised queries only — the `INSERT` MUST bind `user_id`,
  `amount`, `category`, `date`, and `description` as parameters. Never
  string-format any user input into the SQL.
- Passwords hashed with werkzeug (no auth changes in this step).
- Use CSS variables — never hardcode hex values. All new styles must
  reuse the existing palette.
- All templates extend `base.html`.
- Auth guard pattern stays consistent with the rest of `app.py`:
  inline `session.get("user_id")` check at the top of the view, no
  decorators.
- The inserted row's `user_id` MUST come from `session["user_id"]` —
  never trust a `user_id` from the form. Do not add a hidden
  `user_id` field.
- Validation rules (all failures re-render the form with an `error`
  string and echo back the submitted values; no exceptions reach the
  user):
  - `amount` required, must parse as a positive `float` (`> 0`), and
    must be `<= 10_000_000` to guard against absurd input.
  - `category` required, must be one of the keys in `KNOWN_CATEGORIES`
    (lowercased for comparison). Reject anything else.
  - `date` required, must parse as `YYYY-MM-DD` via
    `datetime.strptime(value, "%Y-%m-%d")`. Reject future dates more
    than one day ahead of `date.today()` (allow today + 1 day to
    tolerate timezone skew, reject everything beyond).
  - `description` optional, trimmed; if longer than 200 characters,
    reject with a friendly error. If empty after trimming, store
    `NULL` (i.e. pass `None` to the INSERT) — `build_transactions`
    already falls back to the category label.
- Store `category` in the DB as the lowercase slug (e.g. `"food"`)
  so the existing profile rendering picks up the icon and badge
  class without further translation.
- Store `amount` as a `float` (matches the `REAL` column type and
  the seed data).
- Always close the DB connection (`conn.close()`) on every code
  path, including validation-failure early-returns (no connection is
  opened in that case, so just ensure GET/POST paths that DO open
  one close it).
- All currency rendering in templates goes through `format_amount`
  from `database/queries.py` (existing rule from Step 5). The form
  inputs themselves render plain numbers — no `₹` inside the
  `<input>` value.
- No JavaScript is required for this step. The form is a plain
  `method="POST"` submit; the date defaults are set server-side.
- The category `<option>` list is rendered from a Python iterable
  passed in the template context — do not hardcode the labels in
  the template, so the form stays in sync with `KNOWN_CATEGORIES`.

## Definition of done
- [ ] `GET /expenses/add` while logged out redirects to `/login`
- [ ] `POST /expenses/add` while logged out redirects to `/login`
      (no row inserted)
- [ ] `GET /expenses/add` while logged in returns HTTP 200 and
      renders the add-expense form
- [ ] The form's `<select name="category">` lists every key in
      `KNOWN_CATEGORIES` (Food, Transport, Bills, Health,
      Entertainment, Shopping, Other) with values equal to the
      lowercase slugs
- [ ] The date input is pre-filled with today's date on initial GET
- [ ] Submitting a valid form (e.g. amount `42.50`, category
      `food`, today's date, description `"Lunch"`) returns a 302
      redirect to `/profile`
- [ ] After the redirect, the new expense appears in the
      transactions table on `/profile`, with the correct date,
      description, category badge, and `₹` amount
- [ ] `stats.total_spent`, `stats.tx_count`, and `stats.top_category`
      update to reflect the new row immediately
- [ ] The category breakdown bars recompute to include the new row
- [ ] A second logged-in user does NOT see the first user's new
      expense (the row is scoped to `user_id`)
- [ ] Submitting with `amount=""` re-renders the form with a visible
      error and inserts nothing
- [ ] Submitting with `amount="-5"` or `amount="0"` re-renders the
      form with an error and inserts nothing
- [ ] Submitting with `amount="abc"` re-renders the form with an
      error — no `ValueError` reaches the user
- [ ] Submitting with `category="Bitcoin"` (not in
      `KNOWN_CATEGORIES`) re-renders the form with an error and
      inserts nothing
- [ ] Submitting with `date="not-a-date"` re-renders the form with
      an error and inserts nothing
- [ ] Submitting with `date="2099-01-01"` (far future) re-renders
      the form with an error and inserts nothing
- [ ] Submitting with a 250-character description re-renders the
      form with an error and inserts nothing
- [ ] Submitting with `description=""` succeeds and stores `NULL`
      in the DB; the row renders on `/profile` using the category
      label as the description fallback
- [ ] On any validation failure, the form echoes the user's
      previously submitted amount / category / date / description
      so they do not have to retype
- [ ] The navbar shows an "Add expense" link only when logged in,
      and the link gets the `active` class when on `/expenses/add`
- [ ] The profile hero shows an "Add expense" CTA that links to
      `/expenses/add`
- [ ] SQL uses parameterised bindings for every value in the
      `INSERT` — no f-strings or concatenation anywhere in the view
- [ ] The inserted row's `user_id` comes from `session["user_id"]`,
      not from any form field
- [ ] No DB connection leaks — every code path through
      `add_expense()` that opens a connection also closes it
- [ ] `templates/add_expense.html` extends `base.html`; no inline
      styles or hex colors are introduced
- [ ] `static/css/style.css` gains an `expense-form-` prefixed
      section using only existing CSS variables
- [ ] The existing date filter on `/profile` still works after the
      new row is added (e.g. switching to "This month" still
      includes the new row when its date falls in range)
- [ ] App starts without errors; `pytest` exits cleanly (no new
      tests required for this spec)
