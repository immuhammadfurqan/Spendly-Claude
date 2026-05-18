# Spec: Profile Page

## Overview
This feature replaces the `/profile` stub with a fully designed profile page
showing static, hardcoded data. The goal is to establish the complete UI
layout — user info card, summary stats, transaction history table, and
category breakdown — before any real database queries are wired up in Step 5.
Building the UI first lets the team validate the design in isolation and
ensures the templates are ready for the backend-connection step. The page
sits behind the login wall and introduces the "must be logged in" guard
pattern that later steps will reuse.

## Depends on
- Step 1 — Database setup (schema must exist)
- Step 2 — Registration (user accounts must be creatable)
- Step 3 — Login and Logout (session must be set; `/profile` must be a
  protected route)

## Routes
- `GET /profile` — render the profile page — logged-in only
  (redirect to `/login` if `session.get("user_id")` is missing)

No new routes besides converting the existing stub into a real view.

## Database changes
No database changes. The existing `users` and `expenses` tables are
sufficient and no queries are issued in this step — all data is hardcoded.
Verified against `database/db.py`.

## Templates
- **Create:** `templates/profile.html` — extends `base.html`; contains four
  sections rendered in this order:
  1. **User info card** — circular avatar with the user's first initial,
     name, email, "Member since {Month YYYY}" — all hardcoded
  2. **Summary stats row** — three tiles: total spent (with `₹` prefix
     and thousands separator), number of transactions, top category — hardcoded
  3. **Transaction history table** — recent expenses with columns: date,
     description, category badge, amount — at least 5 hardcoded rows
  4. **Category breakdown** — per-category totals rendered as progress-bar
     rows (label, track, fill, amount) — at least 3 hardcoded categories,
     reusing the `lbar-*` pattern from the landing mockup
- **Modify:** `templates/base.html`
  - Wrap the existing `Hello, {{ session.name }}` span in an anchor pointing
    to `/profile` so the navbar greeting becomes the entry point to the page.
    Keep the same `nav-user` class so styling is unchanged.

## Files to change
- `app.py`
  - Replace the `profile` stub (currently
    `return "Profile page — coming in Step 4"`) with a real view:
    - If `session.get("user_id")` is missing → `redirect(url_for("login"))`.
    - Build hardcoded Python dicts/lists for the context (user info, stats,
      transactions list, category breakdown list).
    - Render `profile.html` with that context.
    - No DB calls in this step.
- `templates/base.html`
  - Change the logged-in branch of the navbar so `Hello, {{ session.name }}`
    is an `<a href="{{ url_for('profile') }}" class="nav-user">…</a>`.
- `static/css/style.css`
  - Append a new "Profile page" section with `profile-` prefixed classes
    (matching the project's `lhero-` / `lmockup-` convention):
    - `.profile-section` — outer wrapper, max-width container, vertical padding
    - `.profile-hero` — card with avatar + identity block
    - `.profile-avatar` — circular initial badge using `--accent` background
      and `--paper` text
    - `.profile-identity` — name (display font), email (muted), member-since
      (faint)
    - `.profile-stats` — three-column grid of stat tiles (reuse `lstat-*`
      classes if they fit; otherwise add `profile-stat-*` analogues)
    - `.profile-table` — transaction history table styling (header row,
      zebra rows or thin row dividers, right-aligned amount column)
    - `.cat-badge` — base category badge (pill shape, small font, padding)
    - `.cat-badge--food`, `.cat-badge--transport`, `.cat-badge--bills`,
      `.cat-badge--health`, `.cat-badge--entertainment`,
      `.cat-badge--shopping`, `.cat-badge--other` — per-category color
      variants using the existing palette variables (`--accent-light` /
      `--accent`, `--accent-2-light` / `--accent-2`, `--danger-light` /
      `--danger`, etc.). No new hex colors.
    - `.profile-breakdown` — wrapper for the category-breakdown section,
      reusing `lbar-row` / `lbar-track` / `lbar-fill` patterns where it
      makes sense
    - Responsive: collapse `.profile-stats` to one column under 600px; allow
      the transaction table to scroll horizontally on narrow screens

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw sqlite3 via `get_db()` if any DB call is
  ever needed (none are in this step)
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- **No inline styles** — every visual property must live in `style.css`
- **Category badges must use a CSS class, not inline color styles** — e.g.
  `<span class="cat-badge cat-badge--food">Food</span>`, never
  `style="background: …"`
- Authentication guard: check `session.get("user_id")`; if absent,
  `redirect(url_for("login"))`. No decorator-based guards — stay consistent
  with the rest of `app.py`.
- All data passed to the template must be hardcoded Python dicts/lists in
  `app.py` — no DB queries in this step (DB wiring lands in Step 5)
- Avatar initial: take the first character of the hardcoded `name` and
  uppercase it
- Currency formatting: render amounts with the `₹` prefix used on the
  landing mock; format with thousands separators (e.g. `₹1,240`)
- Do NOT add a separate "Sign out" form/POST — the navbar already has the
  `GET /logout` link from Step 3

## Definition of done
- [ ] Visiting `/profile` without being logged in redirects to `/login`
- [ ] Visiting `/profile` while logged in returns HTTP 200
- [ ] The page displays a user info card with avatar initial, name, email,
      and "Member since {Month YYYY}"
- [ ] The page displays at least three summary stat values (total spent,
      transaction count, top category)
- [ ] The page displays a transaction history table with at least 5
      hardcoded rows, each showing date, description, a category badge,
      and an amount
- [ ] The page displays a category breakdown section with at least 3
      categories, each rendered as a progress-bar row
- [ ] The navbar "Hello, {name}" greeting is a link to `/profile`
- [ ] The navbar still shows the logged-in state (username + Sign out link)
- [ ] Category badges are styled by CSS class only — no inline `style=`
      attributes anywhere in `profile.html`
- [ ] No hex color values appear in `profile.html` or in the new CSS
      rules — only existing CSS variables
- [ ] Page is responsive: stat tiles collapse to one column below 600px;
      transaction table remains usable on narrow screens
- [ ] App starts without errors
