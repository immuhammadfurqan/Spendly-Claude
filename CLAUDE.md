# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate the virtual environment (Windows)
venv\Scripts\activate

# Run the dev server (port 5001, debug mode on)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_auth.py

# Run a single test by name
pytest -k "test_login"
```

## Architecture

**Spendly** is a Flask-based personal expense tracker built as a step-by-step student project. The codebase is intentionally incomplete — many routes in `app.py` are stubs with "coming in Step X" responses, waiting for students to implement them.

### Entry point

`app.py` is a single-file Flask app. All routes live here. The app runs on port 5001.

### Database (`database/db.py`)

Not yet implemented. The file contains a comment spec for three functions students must write:
- `get_db()` — SQLite connection with `row_factory` and foreign keys enabled
- `init_db()` — creates tables with `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample data for development

### Templates

All templates extend `templates/base.html`, which provides the navbar, footer (with Terms/Privacy links), and block slots: `title`, `head`, `content`, `scripts`.

| Template | Route | Status |
|---|---|---|
| `landing.html` | `/` | Complete — hero, features, CTA, video modal |
| `register.html` | `/register` | Form UI done, POST handler not wired |
| `login.html` | `/login` | Form UI done, POST handler not wired |
| `terms.html` | `/terms` | Complete |
| `privacy.html` | `/privacy` | Complete |

### CSS (`static/css/style.css`)

Single stylesheet for the entire app. Organized into sections:
- **Variables / Reset / Navbar / Footer** — global base styles
- **Hero (old grid)** — kept for reference; overridden by the landing-specific `.hero` flex layout lower in the file
- **Buttons** — `.btn-primary`, `.btn-ghost`, `.btn-submit`
- **Features / CTA** — landing page sections below the hero
- **Auth** — `.auth-section`, `.auth-card`, `.form-group`, `.form-input` used by login and register
- **Legal** — `.legal-section`, `.legal-body` used by terms and privacy
- **Landing hero** — `lhero-*` prefix; overrides `.hero` to centered flex column
- **Landing mockup** — `lmockup-*`, `lstat-*`, `lbar-*` for the app screenshot card
- **Video modal** — `lmodal-*` for the YouTube embed modal

### JavaScript

- `static/js/main.js` — nearly empty; intended for future feature JS
- Landing page video modal logic lives inline in a `{% block scripts %}` block at the bottom of `landing.html` (self-contained IIFE, vanilla JS, no libraries)

### CSS naming convention

Landing-page-specific classes use an `l` prefix (`lhero-`, `lmockup-`, `lmodal-`) to distinguish them from global utility classes and avoid collisions as more pages are added.

### Planned steps (from route stubs)

1. Database setup (`database/db.py`)
2. Register — form POST, password hashing, insert user
3. Login / Logout — session management
4. Profile page
5–6. (TBD)
7. Add expense
8. Edit expense
9. Delete expense
