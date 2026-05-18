# Spec: Registration

## Overview
Wire up the `POST /register` route so new users can create an account.
The form UI in `register.html` is already complete; this step adds the
server-side handler that validates input, hashes the password, inserts the
user into the database, and redirects to the login page on success or
re-renders the form with an error message on failure.

## Depends on
- Step 1 — Database setup (`database/db.py`, `users` table)

## Routes
- `POST /register` — receives form data, creates account — public

## Database changes
No database changes. The `users` table (id, name, email, password_hash,
created_at) already exists from Step 1.

## Templates
- **Modify:** `templates/register.html`
  - The form already posts to `/register` and renders `{{ error }}`.
  - Add a `value="{{ name }}"` and `value="{{ email }}"` sticky-field
    attribute to the name and email inputs so values are preserved on
    validation failure (improves UX, avoids losing user input).

## Files to change
- `app.py` — convert the `register` view to accept GET and POST;
  add `app.secret_key` config (required for future session use in Step 3,
  set it now from an env var or a hard-coded dev value).
- `templates/register.html` — add sticky `value=` attributes to name and
  email inputs.

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security` is already installed.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- On duplicate email, catch the `sqlite3.IntegrityError` and re-render the
  form with `error="An account with that email already exists."`
- Validation order: name required → email required → password min 8 chars →
  DB insert attempt
- On success: `redirect(url_for('login'))` — do not auto-login the user
  (session management is Step 3)
- Import `redirect`, `url_for`, `request` from `flask`

## Definition of done
- [ ] Submitting the form with valid data inserts a new row into `users`
- [ ] The stored password is a bcrypt hash, not plain text
- [ ] Submitting with a duplicate email shows "An account with that email already exists."
- [ ] Submitting with a missing name shows a validation error
- [ ] Submitting with a password shorter than 8 characters shows a validation error
- [ ] Name and email fields retain their values when the form is re-rendered after an error
- [ ] Successful registration redirects to `/login`
- [ ] The GET `/register` route still renders the empty form correctly
- [ ] App starts without errors
