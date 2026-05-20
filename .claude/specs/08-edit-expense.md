# Spec: Edit Expense

## Overview
Step 7 gave logged-in users a write-path into the `expenses` table via
`/expenses/add`. Step 8 closes the obvious gap: once a row has been
created, the user must be able to **fix mistakes** (wrong amount, wrong
category, typo in the description, wrong date) without deleting and
re-adding the row. This step wires the existing
`/expenses/<int:id>/edit` stub into a real GET/POST handler that loads
the expense, renders a pre-filled form, validates the same fields as
add-expense, and `UPDATE`s the row in place. An "Edit" affordance is
added to every row in the profile transactions table so the user can
get into the form with one click. This reuses the add-expense template
layout, validation rules, and CSS — Step 8 is intentionally a small
delta on top of Step 7 and is the second of two write-paths (with
Step 9 — Delete — being the third).

## Depends on
- Step 1 — Database setup (`expenses` table; `get_db()`)
- Step 2 — Registration
- Step 3 — Login and Logout (session sets `user_id`)
- Step 4 — Profile page UI (transactions table layout)
- Step 5 — Profile backend (`build_transactions` produces the rows
  rendered in the table — extended in this step to include the row id)
- Step 6 — Date filter on profile (the edited row honours the active
  filter on return)
- Step 7 — Add expense (template, CSS, validation pattern reused)

## Routes
- `GET  /expenses/<int:id>/edit` — render the edit form pre-filled with
  the existing expense's values — logged-in only (redirect to `/login`
  if `session.get("user_id")` is missing). If the row does not exist or
  belongs to a different user, redirect to `/profile` (no 404 leak).
- `POST /expenses/<int:id>/edit` — validate the submitted fields and
  `UPDATE` the row scoped to `(id, user_id)`, then redirect to
  `/profile` — logged-in only. Same ownership + existence guard as the
  GET.

The existing `edit_expense(id)` stub in `app.py` is rewritten to accept
both methods. No other routes change. The `/expenses/<int:id>/delete`
stub stays untouched (Step 9).

## Database changes
No database changes. The existing `expenses` table is sufficient:
`expenses(id, user_id, amount, category, date, description,
created_at)`. Verified against `database/db.py`. The `UPDATE` will set
`amount`, `category`, `date`, `description` for a row matched by
`(id = ? AND user_id = ?)` — `user_id` is **never** updated, and
`created_at` is left untouched.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`.
  Mirrors the structure of `add_expense.html` so the look stays
  consistent, with these differences:
  - `<title>` and the auth-header title read "Edit expense"; subtitle
    reads "Update this transaction".
  - The `<form>` posts to
    `{{ url_for('edit_expense', id=expense_id) }}`.
  - Inputs are pre-filled from the loaded row's values
    (`amount`, `category`, `date`, `description`) — same template
    variables the add-expense view already passes, so the existing
    `add_expense.html` field markup can be lifted verbatim. The
    category `<select>` reuses the `categories` iterable
    (`CATEGORY_OPTIONS` from `database/queries.py`).
  - The submit button text is "Save changes" (not "Save expense").
  - The "Cancel" link still points back to `/profile` and reuses the
    `.expense-form-cancel` class.
  - On validation failure, re-renders with an `error` string and
    echoes back the submitted values (same pattern as add-expense and
    auth forms).

- **Modify:** `templates/profile.html`
  - The transactions table grows a fifth column (header label
    "Actions", `ta-right` to match the amount column). Each row
    renders a single `<a>` to
    `{{ url_for('edit_expense', id=tx.id) }}` styled as a compact
    text/icon link (lucide `pencil` icon next to the word "Edit"), so
    a click takes the user straight to the edit form. The Actions
    column header is screen-reader friendly (e.g. wrap the visual
    label in a span if needed) — no aria attributes are strictly
    required for this step, but the column must not be empty.
  - The empty-state of the table (when `transactions` is empty) is
    unchanged — no Actions column rows are rendered.

- **Modify:** none of the other templates change. `base.html` already
  has the "Add expense" nav link from Step 7 and does not need a new
  nav entry for edit (the edit form is reached from the transactions
  table, not the navbar).

## Files to change
- `app.py`
  - Rewrite the existing `edit_expense(id)` stub to accept both `GET`
    and `POST`:
    1. Auth guard — `if not session.get("user_id"): return
       redirect(url_for("login"))`.
    2. Load the row with a single parameterised query:
       `SELECT id, amount, category, date, description FROM expenses
       WHERE id = ? AND user_id = ?` using `(id, session["user_id"])`.
       If no row matches, close the connection and
       `redirect(url_for("profile"))`. Do not return a 404 (avoids
       leaking whether the id exists for another user).
    3. On `GET`, render `edit_expense.html` with the form pre-filled
       from the loaded row (`amount=str(row["amount"])`,
       `category=row["category"]`, `date=row["date"]`,
       `description=row["description"] or ""`) and pass
       `categories=CATEGORY_OPTIONS` and `expense_id=id` in context.
    4. On `POST`, read `amount`, `category`, `date`, `description`
       from `request.form` and apply the **same validation rules**
       as add-expense (see *Rules*). On any failure, re-render the
       form with an `error` string and echo back the submitted
       values; do **not** update.
    5. On valid input, run a parameterised
       `UPDATE expenses SET amount = ?, category = ?, date = ?,
       description = ? WHERE id = ? AND user_id = ?` with the new
       values plus `(id, session["user_id"])`. Commit, close, then
       `redirect(url_for("profile"))`.
    6. Always `conn.close()` on every code path that opens a
       connection — wrap the DB work in `try/finally` mirroring the
       `add_expense` view.
  - Leave the `/expenses/<int:id>/delete` stub untouched.

- `database/queries.py`
  - Update `build_transactions(expense_rows)` so each returned dict
    includes the source row's `id`:
    ```python
    transactions.append({
        "id":             row["id"],          # <-- new
        "date":           date_display,
        "description":    description,
        ...
    })
    ```
  - Update the `/profile` query in `app.py` to select `id` alongside
    the existing columns: `SELECT id, amount, category, date,
    description FROM expenses WHERE user_id = ?` (the rest of the
    builder code already accepts row objects, so this is the only
    place the column list widens).
  - No other helper changes. `build_stats` and `build_breakdown` do
    not need the id.

- `templates/profile.html` — see *Templates → Modify*.

- `static/css/style.css`
  - Add a small `expense-table-actions` (or `tx-action-link`) rule set
    for the inline Edit link in the transactions table: muted text
    colour from `--muted`, hover state shifts to `--accent`, icon
    sized via `em` so it stays in line with the label. Use only
    existing CSS variables — no new hex values.
  - No changes to the existing `expense-form-*` rules; the edit
    template reuses them as-is.

## Files to create
- `templates/edit_expense.html` — described above.

## New dependencies
No new dependencies. Only the standard library (`datetime`) and the
already-imported `sqlite3` + `flask` modules are needed.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`.
- Parameterised queries only — the `SELECT` and `UPDATE` MUST bind
  `id`, `user_id`, `amount`, `category`, `date`, and `description` as
  parameters. Never string-format any value (including the URL `id`)
  into the SQL.
- Passwords hashed with werkzeug (no auth changes in this step).
- Use CSS variables — never hardcode hex values. The new Actions
  column link and any new rules must reuse the existing palette.
- All templates extend `base.html`.
- Auth guard pattern stays consistent with the rest of `app.py`:
  inline `session.get("user_id")` check at the top of the view, no
  decorators.
- The `UPDATE`'s `WHERE` clause MUST include `user_id =
  session["user_id"]` so a user can never edit another user's
  expense even by guessing the id. Do not rely solely on the
  GET-time lookup — the POST handler must re-check ownership in the
  same `UPDATE` statement.
- Do not allow `user_id` to be changed. The `UPDATE` does not touch
  `user_id` or `created_at`. There is no hidden `user_id` field in
  the form.
- If the GET-time lookup returns no row (wrong id, or id belonging
  to a different user), redirect to `/profile` — no 404, no error
  message. This keeps the existence of other users' rows opaque.
- Validation rules — **identical** to add-expense (Step 7). On any
  failure, re-render the edit form with an `error` string and echo
  back the submitted values:
  - `amount` required, must parse as a positive `float` (`> 0`), and
    must be `<= 10_000_000`.
  - `category` required, must be one of the keys in
    `KNOWN_CATEGORIES` (lowercased for comparison).
  - `date` required, must parse as `YYYY-MM-DD` via
    `datetime.strptime(value, "%Y-%m-%d")`. Reject future dates more
    than one day ahead of `date.today()` (allow today + 1 day to
    tolerate timezone skew).
  - `description` optional, trimmed; if longer than 200 characters,
    reject with a friendly error. If empty after trimming, store
    `NULL` (i.e. pass `None` to the UPDATE) — `build_transactions`
    already falls back to the category label.
- Store `category` in the DB as the lowercase slug (e.g. `"food"`),
  matching add-expense. The pre-fill on GET uses the existing
  lowercase slug straight from the row.
- Store `amount` as a `float`. When pre-filling the form, render the
  raw numeric value (e.g. `42.5`) — do **not** apply
  `format_amount` to the form input (no `₹` inside the `<input>`).
- Always close the DB connection (`conn.close()`) on every code
  path that opens one (GET success, GET miss, POST validation
  failure, POST success). Use `try/finally`.
- All currency rendering in templates still goes through
  `format_amount` from `database/queries.py` — applies to the
  transactions table, not the edit form input.
- No JavaScript is required for this step. The edit link in the
  transactions table is a plain `<a>`; the form is a plain
  `method="POST"`.
- `build_transactions` now exposes `tx.id`; nothing else in the
  template context shape changes.
- Do not introduce new icon dependencies. The "Edit" link uses the
  existing lucide setup (`<i data-lucide="pencil"></i>`).

## Definition of done
- [ ] `GET /expenses/1/edit` while logged out redirects to `/login`
- [ ] `POST /expenses/1/edit` while logged out redirects to `/login`
      (no row updated)
- [ ] `GET /expenses/<id>/edit` while logged in for an id that
      belongs to the current user returns HTTP 200 and renders the
      edit form pre-filled with that row's amount, category, date,
      and description
- [ ] `GET /expenses/<id>/edit` for an id that belongs to a
      different user redirects to `/profile` (no 404, no leaked
      detail)
- [ ] `GET /expenses/999999/edit` (nonexistent id) while logged in
      redirects to `/profile`
- [ ] The category `<select>` on the edit form shows the same
      options as add-expense, with the row's current category
      pre-selected
- [ ] The date `<input>` is pre-filled with the row's stored date
      in `YYYY-MM-DD` format
- [ ] Submitting valid changes (e.g. amount `99.99`, category
      `transport`, today's date, description `"Updated"`) returns a
      302 redirect to `/profile`
- [ ] After the redirect, the row on `/profile` reflects the new
      values immediately (amount, category badge + icon, date,
      description)
- [ ] `stats.total_spent`, `stats.tx_count`, and `stats.top_category`
      recompute to reflect the edited row
- [ ] The category breakdown bars recompute to include the edited
      row's new category/amount
- [ ] Submitting `POST /expenses/<id>/edit` where `<id>` belongs to
      another user does NOT update that row, and redirects to
      `/profile`
- [ ] Submitting with `amount=""`, `amount="-5"`, `amount="0"`, or
      `amount="abc"` re-renders the edit form with an error and
      does not update the row
- [ ] Submitting with `category="Bitcoin"` (not in
      `KNOWN_CATEGORIES`) re-renders the form with an error and
      does not update the row
- [ ] Submitting with `date="not-a-date"` or a far-future date
      re-renders the form with an error and does not update the row
- [ ] Submitting with a 250-character description re-renders the
      form with an error and does not update the row
- [ ] Submitting with `description=""` succeeds and stores `NULL`
      in the DB; the row renders on `/profile` using the category
      label as the description fallback
- [ ] On any validation failure, the form echoes the user's
      previously submitted amount / category / date / description
      so they do not have to retype
- [ ] The `UPDATE` never changes `user_id` or `created_at`
- [ ] SQL uses parameterised bindings for `id`, `user_id`,
      `amount`, `category`, `date`, and `description` — no f-strings
      or concatenation anywhere in the view
- [ ] No DB connection leaks — every code path through
      `edit_expense(id)` that opens a connection also closes it
- [ ] The transactions table on `/profile` shows an Actions column
      with an "Edit" link on every row, linking to the correct
      `/expenses/<id>/edit` URL
- [ ] The Actions column does not appear for users with zero
      transactions (or, if it does, no broken empty cells render)
- [ ] `templates/edit_expense.html` extends `base.html`; no inline
      styles or hex colors are introduced
- [ ] The edit form reuses the `expense-form-*` CSS from Step 7
      with no visual regressions on the add-expense page
- [ ] `static/css/style.css` gains only variable-based rules — no
      new hex values
- [ ] The existing date filter on `/profile` still works after a
      row is edited (the edited row appears or disappears from the
      filtered view consistent with its new date)
- [ ] `build_transactions` now exposes `id` on each returned dict;
      `build_stats` and `build_breakdown` continue to work unchanged
- [ ] App starts without errors; `pytest` exits cleanly (no new
      tests required for this spec)
