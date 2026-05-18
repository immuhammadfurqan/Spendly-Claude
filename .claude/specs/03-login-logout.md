# Spec: Login and Logout

## Overview
Wire up the `POST /login` and `GET /logout` routes so users can authenticate
and end their session. The login form UI in `login.html` is already complete.
This step adds the server-side handler that verifies the email/password pair
against the database, stores the user's `id` and `name` in the Flask session
on success, and clears the session on logout. It also updates the navbar in
`base.html` to show contextual links (Sign in / Get started when logged out;
the user's name and a Sign out link when logged in).

## Depends on
- Step 1 — Database setup (`database/db.py`, `users` table)
- Step 2 — Registration (users exist in the database with hashed passwords)

## Routes
- `POST /login` — receives email + password, starts session on success — public
- `GET /logout` — clears the session, redirects to `/` — logged-in

## Database changes
No database changes. The `users` table already has all required columns.

## Templates
- **Modify:** `templates/login.html`
  - Add a `value="{{ email }}"` sticky-field attribute to the email input so
    the value is preserved when the form is re-rendered after a failed login.
- **Modify:** `templates/base.html`
  - Replace the static nav links with a conditional block:
    - Logged out: show "Sign in" and "Get started" (current behaviour)
    - Logged in: show "Hello, {{ session.name }}" (plain text) and a
      "Sign out" link pointing to `/logout`

## Files to change
- `app.py`
  - Add `session` and `check_password_hash` to imports.
  - Convert the `login` view from GET-only to `methods=["GET", "POST"]`.
  - On GET: if the user is already logged in (`session.get("user_id")`),
    redirect to `/profile`; otherwise render `login.html` with `email=""`.
  - On POST: validate email and password are non-empty, look up the user by
    email, call `check_password_hash`, store `session["user_id"]` and
    `session["name"]` on success, redirect to `/profile`.
  - On failure: re-render `login.html` with `error=` and the submitted `email`.
  - Implement the `logout` view: call `session.clear()`, redirect to `/`.
- `templates/login.html`
  - Add `value="{{ email }}"` to the email input.
- `templates/base.html`
  - Update `nav-links` div with a Jinja2 conditional for logged-in vs
    logged-out nav items.

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already
available via the installed `werkzeug` package.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Never reveal whether the email or the password was wrong — always use a
  generic message: `"Invalid email or password."`
- Validation order: email non-empty → password non-empty → DB lookup →
  password check
- On successful login: `redirect(url_for('profile'))` (the stub route is fine
  for now; it will be implemented in Step 4)
- On logout: `session.clear()` then `redirect(url_for('landing'))`
- The `secret_key` is already set in `app.py`; do not change it

## Definition of done
- [ ] Submitting correct credentials stores `user_id` and `name` in the session
      and redirects to `/profile`
- [ ] Submitting a wrong password shows "Invalid email or password." and
      re-renders the form with the email value preserved
- [ ] Submitting an unknown email shows "Invalid email or password."
- [ ] Submitting with a blank email or blank password shows a validation error
      without hitting the database
- [ ] Visiting `/login` while already logged in redirects to `/profile`
- [ ] Visiting `/logout` clears the session and redirects to `/`
- [ ] The navbar shows "Sign in" and "Get started" when logged out
- [ ] The navbar shows the user's name and a "Sign out" link when logged in
- [ ] App starts without errors
