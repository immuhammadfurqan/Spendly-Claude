"""
Tests for Step 06 — Date Filter for Profile Page.

Spec source: .claude/specs/06-date-filter-profile.md

Strategy
--------
- All tests use an isolated in-memory SQLite DB so they never touch spendly.db.
- "Today" is pinned to 2026-05-19 by monkeypatching `app.date` (the `date`
  class imported at the top of app.py).  This makes preset-window assertions
  deterministic regardless of when the test suite runs.
- The seed fixture inserts known expenses across several months so every
  filter window can be asserted precisely.
- No freezegun required — plain monkeypatch is sufficient because the view
  calls `date.today()` and we redirect that call.

Pinned "today": 2026-05-19
Expense seed data (all belong to test user):
  2026-01-10  Food        ₹500   "Jan food"         — year only
  2026-03-15  Transport   ₹200   "Mar transport"    — year only
  2026-04-30  Bills       ₹300   "Apr bills"        — year + 30d (Apr-30 is within [Apr-20..May-19])
  2026-04-20  Health      ₹150   "Apr health"       — year + 30d (Apr-20 is the inclusive start boundary)
  2026-05-01  Shopping    ₹400   "May shopping"     — month + year + 30d (May 19 - 29 = Apr 20, so May-01 >= Apr-20 yes)
  2026-05-10  Food        ₹100   "May food"         — month + year + 30d
  2026-05-19  Other       ₹50    "May other today"  — month + year + 30d + custom

30d window (today=2026-05-19): start = 2026-05-19 - 29 days = 2026-04-20
  => Apr-20, Apr-30, May-01, May-10, May-19 are in the 30d window  (5 expenses)
  Note: Apr-30 is within [Apr-20 .. May-19] so it IS included.

Month window: 2026-05-01 to 2026-05-19
  => May-01, May-10, May-19  (3 expenses)

Year window: 2026-01-01 to 2026-05-19
  => all 7 expenses

Custom range 2026-05-01 to 2026-05-10 (inclusive):
  => May-01, May-10  (2 expenses)

A second user's expense is also seeded to confirm cross-user isolation.
"""

import pytest
from datetime import date as real_date
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import init_db


# ---------------------------------------------------------------------------
# Pinned "today" for deterministic preset assertions
# ---------------------------------------------------------------------------

PINNED_TODAY = real_date(2026, 5, 19)

# Expense data: (amount, category, date_str, description)
SEED_EXPENSES = [
    (500.0,  "Food",      "2026-01-10", "Jan food"),
    (200.0,  "Transport", "2026-03-15", "Mar transport"),
    (300.0,  "Bills",     "2026-04-30", "Apr bills"),
    (150.0,  "Health",    "2026-04-20", "Apr health"),
    (400.0,  "Shopping",  "2026-05-01", "May shopping"),
    (100.0,  "Food",      "2026-05-10", "May food"),
    (50.0,   "Other",     "2026-05-19", "May other today"),
]

# Window membership for quick reference
# 30d window: Apr-20 .. May-19  => Apr-20, Apr-30, May-01, May-10, May-19 = 5 rows
# month window: May-01 .. May-19 => May-01, May-10, May-19 = 3 rows
# year window: Jan-01 .. May-19 => all 7 rows
WINDOW_COUNTS = {
    "all":   7,
    "month": 3,
    "30d":   5,   # Apr-20, Apr-30, May-01, May-10, May-19 all fall within [Apr-20..May-19]
    "year":  7,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Flask app wired to an isolated file-based temp DB (not :memory:) so
    the same connection path works across the app's get_db() calls."""
    db_file = str(tmp_path / "test_spendly.db")

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
        # Override the DB path via an env-style monkeypatch on the module
    })

    import database.db as db_module
    import app as app_module
    original_db_get_db = db_module.get_db
    original_app_get_db = app_module.get_db

    def _patched_get_db():
        import sqlite3
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Patch BOTH bindings: the module attribute AND the name already imported
    # into app.py via `from database.db import get_db`.
    db_module.get_db = _patched_get_db
    app_module.get_db = _patched_get_db

    with flask_app.app_context():
        # Create schema
        conn = _patched_get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                email         TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL    NOT NULL,
                category    TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                description TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

        yield flask_app

    # Restore both bindings
    db_module.get_db = original_db_get_db
    app_module.get_db = original_app_get_db


@pytest.fixture()
def seeded_db(app):
    """Seed the isolated DB with one test user + known expenses + one other user."""
    import database.db as db_module
    conn = db_module.get_db()

    # Primary test user
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", generate_password_hash("password123")),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Seed known expenses
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, dt, desc) for amt, cat, dt, desc in SEED_EXPENSES],
    )

    # Second user with one expense — must never appear in primary user's profile
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Other User", "other@example.com", generate_password_hash("password123")),
    )
    other_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (other_id, 9999.0, "Bills", "2026-05-10", "Other user expense"),
    )

    conn.commit()
    conn.close()
    return user_id


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client, seeded_db):
    """Client already logged in as the primary test user."""
    client.post(
        "/login",
        data={"email": "test@example.com", "password": "password123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture()
def frozen_today(monkeypatch):
    """Pin date.today() to PINNED_TODAY inside the app module.

    app.py imports `date` from datetime and calls `date.today()` directly.
    We replace the `date` name in the app module's namespace with a subclass
    that overrides `today()`.
    """
    import app as app_module

    class FrozenDate(real_date):
        @classmethod
        def today(cls):
            return PINNED_TODAY

    monkeypatch.setattr(app_module, "date", FrozenDate)
    return PINNED_TODAY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expense_count(app):
    """Return total number of expense rows in the isolated DB."""
    import database.db as db_module
    conn = db_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


def _get_profile(auth_client, **params):
    """GET /profile with optional query params; returns response."""
    qs = "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
    url = "/profile?" + qs if qs else "/profile"
    return auth_client.get(url)


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:

    def test_unauthenticated_get_redirects_to_login(self, client, seeded_db):
        """GET /profile while logged out must redirect to /login (302)."""
        response = client.get("/profile")
        assert response.status_code == 302, "Expected redirect for unauthenticated user"
        assert "/login" in response.headers["Location"], (
            "Redirect target should be /login"
        )

    def test_unauthenticated_get_does_not_return_200(self, client, seeded_db):
        """GET /profile while logged out must not leak profile content."""
        response = client.get("/profile", follow_redirects=True)
        assert b"filter-bar" not in response.data, (
            "Unauthenticated response must not contain the filter bar"
        )


# ---------------------------------------------------------------------------
# 2. No-filter happy path (all expenses shown)
# ---------------------------------------------------------------------------

class TestNoFilterHappyPath:

    def test_no_filter_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile with no query string returns 200."""
        response = _get_profile(auth_client)
        assert response.status_code == 200, "Expected 200 for authenticated profile"

    def test_no_filter_shows_all_user_expenses(self, auth_client, seeded_db, frozen_today):
        """GET /profile with no params shows all 7 seeded expenses."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        # The filter-caption includes the transaction count
        assert "7 transactions" in data or "7 transaction" in data, (
            "Expected 7 transactions (all time) when no filter is active"
        )

    def test_no_filter_range_label_is_all_time(self, auth_client, seeded_db, frozen_today):
        """GET /profile with no filter renders 'all time' in stat notes."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        assert "all time" in data, (
            "Expected 'all time' range_label when no filter is active"
        )

    def test_no_filter_all_time_preset_link_is_active(self, auth_client, seeded_db, frozen_today):
        """'All time' preset link must carry filter-preset--active class when no filter."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        assert "filter-preset--active" in data, "Expected some preset to be marked active"
        # The 'All time' link should be the active one
        # It appears before 'This month' in the rendered HTML
        active_idx = data.index("filter-preset--active")
        all_time_idx = data.index("All time")
        this_month_idx = data.index("This month")
        assert active_idx < this_month_idx, (
            "'All time' active class should appear before 'This month' in HTML"
        )

    def test_no_filter_does_not_show_other_user_expenses(self, auth_client, seeded_db, frozen_today):
        """Profile must never leak another user's expense amounts."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        # Other user has ₹9999 — must not appear
        assert "9,999" not in data, "Other user's expense must not appear on profile"
        assert "Other user expense" not in data, (
            "Other user's expense description must not appear on profile"
        )


# ---------------------------------------------------------------------------
# 3. Filter bar structure
# ---------------------------------------------------------------------------

class TestFilterBarStructure:

    def test_filter_bar_present_on_page(self, auth_client, seeded_db, frozen_today):
        """Profile page must render a filter-bar form."""
        response = _get_profile(auth_client)
        assert b"filter-bar" in response.data, "Expected filter-bar element"

    def test_filter_bar_method_is_get(self, auth_client, seeded_db, frozen_today):
        """Filter form must use method=GET so filter state survives reload via URL."""
        response = _get_profile(auth_client)
        assert b'method="GET"' in response.data or b"method=GET" in response.data, (
            "Filter form must use GET method for bookmarkable URLs"
        )

    def test_preset_links_present(self, auth_client, seeded_db, frozen_today):
        """All four preset labels must appear as links in the filter bar."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        for label in ("All time", "This month", "Last 30 days", "This year"):
            assert label in data, f"Expected preset label '{label}' in filter bar"

    def test_date_inputs_present(self, auth_client, seeded_db, frozen_today):
        """Two <input type='date'> fields named start and end must exist."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        assert 'name="start"' in data, "Expected start date input"
        assert 'name="end"' in data, "Expected end date input"

    def test_apply_button_present(self, auth_client, seeded_db, frozen_today):
        """An Apply submit button must be in the filter bar."""
        response = _get_profile(auth_client)
        assert b"Apply" in response.data, "Expected Apply button in filter bar"

    def test_clear_link_points_to_profile(self, auth_client, seeded_db, frozen_today):
        """A Clear link must point to /profile (no query string)."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        assert "Clear" in data, "Expected Clear link"
        # Clear link href must be /profile without params
        assert 'href="/profile"' in data, (
            "Clear link must href to /profile with no query params"
        )

    def test_filter_caption_present(self, auth_client, seeded_db, frozen_today):
        """A filter-caption element must appear below the filter bar."""
        response = _get_profile(auth_client)
        assert b"filter-caption" in response.data, "Expected filter-caption on page"

    def test_profile_extends_base_template(self, auth_client, seeded_db, frozen_today):
        """Profile page must contain base.html landmarks (navbar, footer)."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        # base.html renders the Spendly brand in the nav
        assert "Spendly" in data, "Expected base.html navbar brand"


# ---------------------------------------------------------------------------
# 4. Preset: month
# ---------------------------------------------------------------------------

class TestPresetMonth:

    def test_preset_month_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?preset=month returns 200."""
        response = _get_profile(auth_client, preset="month")
        assert response.status_code == 200

    def test_preset_month_shows_only_current_month_expenses(
        self, auth_client, seeded_db, frozen_today
    ):
        """preset=month restricts to 3 expenses (May-01, May-10, May-19)."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        count = WINDOW_COUNTS["month"]
        assert f"{count} transaction" in data, (
            f"Expected {count} transactions for month preset"
        )

    def test_preset_month_excludes_earlier_expenses(self, auth_client, seeded_db, frozen_today):
        """Jan and Mar and Apr expenses must not appear when preset=month."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        assert "Jan food" not in data, "Jan expense must be excluded with month preset"
        assert "Mar transport" not in data, "Mar expense must be excluded with month preset"
        assert "Apr bills" not in data, "Apr expense must be excluded with month preset"

    def test_preset_month_this_month_link_is_active(self, auth_client, seeded_db, frozen_today):
        """'This month' preset link must have filter-preset--active class."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        # Find position of 'filter-preset--active' and confirm 'This month' is nearby
        assert "filter-preset--active" in data, "Expected active preset class"
        active_pos = data.index("filter-preset--active")
        this_month_pos = data.index("This month")
        # The active class and 'This month' label must be in the same anchor block
        # Active class appears before the label text (class attribute before content)
        assert active_pos < this_month_pos < active_pos + 200, (
            "'This month' should be the active preset link"
        )

    def test_preset_month_range_label_in_stat_notes(self, auth_client, seeded_db, frozen_today):
        """Stat notes must render 'This month' as range_label."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        assert "This month" in data, "Expected 'This month' range_label in stat notes"

    def test_preset_month_stat_note_spans_contain_range_label(
        self, auth_client, seeded_db, frozen_today
    ):
        """profile-stat-note spans must render the active range_label, not hardcoded text."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        # The template uses {{ filter.range_label }} in profile-stat-note spans
        # 'all time' (hardcoded old value) must NOT appear when preset=month
        # 'This month' must appear at least twice (two stat-note spans)
        count = data.count("This month")
        assert count >= 2, (
            f"Expected 'This month' to appear at least twice in stat notes, found {count}"
        )


# ---------------------------------------------------------------------------
# 5. Preset: 30d
# ---------------------------------------------------------------------------

class TestPreset30d:

    def test_preset_30d_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?preset=30d returns 200."""
        response = _get_profile(auth_client, preset="30d")
        assert response.status_code == 200

    def test_preset_30d_shows_correct_expense_count(self, auth_client, seeded_db, frozen_today):
        """preset=30d restricts to 5 expenses (Apr-20, Apr-30, May-01, May-10, May-19)."""
        response = _get_profile(auth_client, preset="30d")
        data = response.data.decode()
        count = WINDOW_COUNTS["30d"]
        assert f"{count} transaction" in data, (
            f"Expected {count} transactions for 30d preset"
        )

    def test_preset_30d_includes_boundary_start_expense(
        self, auth_client, seeded_db, frozen_today
    ):
        """Expense on Apr-20 (the 30d start boundary) must be included."""
        response = _get_profile(auth_client, preset="30d")
        data = response.data.decode()
        assert "Apr health" in data, (
            "Apr-20 expense must be included (inclusive lower bound)"
        )

    def test_preset_30d_excludes_expenses_before_window(
        self, auth_client, seeded_db, frozen_today
    ):
        """Expenses before Apr-20 must be excluded; expenses on/after Apr-20 included."""
        response = _get_profile(auth_client, preset="30d")
        data = response.data.decode()
        assert "Jan food" not in data, "Jan-10 expense must be excluded with 30d preset"
        assert "Mar transport" not in data, "Mar-15 expense must be excluded with 30d preset"
        # Apr-30 IS within the 30d window [Apr-20 .. May-19]; it must be included
        assert "Apr bills" in data, "Apr-30 expense must be INCLUDED in the 30d window"

    def test_preset_30d_this_month_link_not_active(self, auth_client, seeded_db, frozen_today):
        """'This month' preset link must NOT be active when preset=30d."""
        response = _get_profile(auth_client, preset="30d")
        data = response.data.decode()
        # 'Last 30 days' should be active, not 'This month'
        # Check: the active class appears in the '30d' anchor, not the 'month' anchor
        active_pos = data.index("filter-preset--active") if "filter-preset--active" in data else -1
        this_month_pos = data.index("This month") if "This month" in data else -1
        last30_pos = data.index("Last 30 days") if "Last 30 days" in data else -1
        assert last30_pos > 0 and this_month_pos > 0, "Both preset labels must appear"
        # The active class must be closer to 'Last 30 days' than to 'This month'
        if active_pos >= 0:
            dist_to_month = abs(active_pos - this_month_pos)
            dist_to_30d = abs(active_pos - last30_pos)
            assert dist_to_30d < dist_to_month, (
                "'Last 30 days' should be the active preset, not 'This month'"
            )

    def test_preset_30d_range_label(self, auth_client, seeded_db, frozen_today):
        """Stat notes must render 'Last 30 days' as range_label."""
        response = _get_profile(auth_client, preset="30d")
        data = response.data.decode()
        assert "Last 30 days" in data, "Expected 'Last 30 days' range_label"


# ---------------------------------------------------------------------------
# 6. Preset: year
# ---------------------------------------------------------------------------

class TestPresetYear:

    def test_preset_year_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?preset=year returns 200."""
        response = _get_profile(auth_client, preset="year")
        assert response.status_code == 200

    def test_preset_year_shows_all_current_year_expenses(
        self, auth_client, seeded_db, frozen_today
    ):
        """preset=year shows all 7 expenses (all seeded within 2026)."""
        response = _get_profile(auth_client, preset="year")
        data = response.data.decode()
        count = WINDOW_COUNTS["year"]
        assert f"{count} transaction" in data, (
            f"Expected {count} transactions for year preset"
        )

    def test_preset_year_this_year_link_is_active(self, auth_client, seeded_db, frozen_today):
        """'This year' preset link must have filter-preset--active class."""
        response = _get_profile(auth_client, preset="year")
        data = response.data.decode()
        assert "filter-preset--active" in data, "Expected active preset class"
        active_pos = data.index("filter-preset--active")
        this_year_pos = data.index("This year")
        assert active_pos < this_year_pos < active_pos + 300, (
            "'This year' should be the active preset link"
        )

    def test_preset_year_range_label(self, auth_client, seeded_db, frozen_today):
        """Stat notes must render 'This year' as range_label."""
        response = _get_profile(auth_client, preset="year")
        data = response.data.decode()
        assert "This year" in data, "Expected 'This year' range_label"


# ---------------------------------------------------------------------------
# 7. Custom date range ?start=...&end=...
# ---------------------------------------------------------------------------

class TestCustomDateRange:

    def test_custom_range_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?start=2026-05-01&end=2026-05-10 returns 200."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        assert response.status_code == 200

    def test_custom_range_inclusive_both_ends(self, auth_client, seeded_db, frozen_today):
        """Both May-01 and May-10 must appear in custom range 2026-05-01 to 2026-05-10."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert "May shopping" in data, "May-01 expense must be included (inclusive start)"
        assert "May food" in data, "May-10 expense must be included (inclusive end)"

    def test_custom_range_excludes_out_of_window_expenses(
        self, auth_client, seeded_db, frozen_today
    ):
        """Expenses outside 2026-05-01 to 2026-05-10 must be excluded."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert "Jan food" not in data, "Jan expense must be excluded"
        assert "Mar transport" not in data, "Mar expense must be excluded"
        assert "Apr bills" not in data, "Apr-30 expense must be excluded (before May-01)"
        assert "Apr health" not in data, "Apr-20 expense must be excluded (before May-01)"
        assert "May other today" not in data, "May-19 expense must be excluded (after May-10)"

    def test_custom_range_shows_correct_transaction_count(
        self, auth_client, seeded_db, frozen_today
    ):
        """Custom range 2026-05-01 to 2026-05-10 yields exactly 2 transactions."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert "2 transaction" in data, "Expected 2 transactions in custom range"

    def test_custom_range_stats_reflect_window_only(self, auth_client, seeded_db, frozen_today):
        """Total spent in custom range (May-01 + May-10) = ₹500, not full total."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        # May-01 ₹400 + May-10 ₹100 = ₹500
        assert "₹500" in data, "Expected ₹500 total for custom range"

    def test_custom_range_no_preset_link_marked_active(
        self, auth_client, seeded_db, frozen_today
    ):
        """No preset link should carry filter-preset--active when custom start/end is set."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        # The active class must NOT appear near any preset label
        # (It should not appear at all, since no preset matches a manual range)
        if "filter-preset--active" in data:
            # If it does appear, it must not be near "This month", "Last 30 days", or "This year"
            active_pos = data.index("filter-preset--active")
            for label in ("This month", "Last 30 days", "This year"):
                label_pos = data.index(label) if label in data else -1
                if label_pos >= 0:
                    assert abs(active_pos - label_pos) > 100, (
                        f"'{label}' must not be active preset when custom range is set"
                    )

    def test_custom_range_range_label_in_stat_notes(self, auth_client, seeded_db, frozen_today):
        """Stat notes must render the custom range label (not 'all time' or a preset name)."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        # range_label for custom range = "May 01, 2026 – May 10, 2026"
        assert "May 01, 2026" in data, "Expected start_display in range_label"
        assert "May 10, 2026" in data, "Expected end_display in range_label"

    def test_custom_start_only_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?start=2026-05-01 (no end) returns 200 and applies only a lower bound."""
        response = _get_profile(auth_client, start="2026-05-01")
        assert response.status_code == 200
        data = response.data.decode()
        # May-01, May-10, May-19 must be present; Jan and Mar must be absent
        assert "May shopping" in data, "May-01 expense must be included"
        assert "Jan food" not in data, "Jan expense must be excluded"

    def test_custom_end_only_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?end=2026-01-31 (no start) returns 200 and applies only an upper bound."""
        response = _get_profile(auth_client, end="2026-01-31")
        assert response.status_code == 200
        data = response.data.decode()
        assert "Jan food" in data, "Jan expense must be included (before Jan-31)"
        assert "Mar transport" not in data, "Mar expense must be excluded (after Jan-31)"


# ---------------------------------------------------------------------------
# 8. Explicit start/end overrides preset when both present
# ---------------------------------------------------------------------------

class TestRangeOverridesPreset:

    def test_explicit_range_wins_over_preset(self, auth_client, seeded_db, frozen_today):
        """When start+end and preset are both in URL, explicit range wins."""
        # preset=year would show all 7; custom May-01..May-10 shows 2
        response = auth_client.get(
            "/profile?preset=year&start=2026-05-01&end=2026-05-10"
        )
        assert response.status_code == 200
        data = response.data.decode()
        # Only 2 transactions should appear, not 7
        assert "2 transaction" in data, (
            "Explicit start/end must override preset=year"
        )
        assert "Jan food" not in data, "Jan expense must be excluded when explicit range wins"

    def test_explicit_range_wins_over_month_preset(self, auth_client, seeded_db, frozen_today):
        """Explicit range covering Jan overrides preset=month."""
        response = auth_client.get(
            "/profile?preset=month&start=2026-01-01&end=2026-01-31"
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "Jan food" in data, "Jan expense must appear when explicit Jan range wins"
        assert "May shopping" not in data, "May expense must be excluded when Jan range wins"


# ---------------------------------------------------------------------------
# 9. Reversed range (start > end)
# ---------------------------------------------------------------------------

class TestReversedRange:

    def test_reversed_range_returns_200_not_500(self, auth_client, seeded_db, frozen_today):
        """Reversed range must return 200, never 500."""
        response = _get_profile(auth_client, start="2026-05-15", end="2026-05-01")
        assert response.status_code == 200, "Reversed range must not cause a 500"

    def test_reversed_range_shows_filter_error(self, auth_client, seeded_db, frozen_today):
        """Reversed range must render a visible filter-error message."""
        response = _get_profile(auth_client, start="2026-05-15", end="2026-05-01")
        assert b"filter-error" in response.data, (
            "Reversed range must show a filter-error element"
        )

    def test_reversed_range_renders_unfiltered(self, auth_client, seeded_db, frozen_today):
        """With a reversed range, all expenses must still appear (no filter applied)."""
        response = _get_profile(auth_client, start="2026-05-15", end="2026-05-01")
        data = response.data.decode()
        assert "7 transaction" in data, (
            "Reversed range must fall back to unfiltered (all 7 expenses)"
        )

    def test_reversed_range_error_message_is_human_readable(
        self, auth_client, seeded_db, frozen_today
    ):
        """The error message for a reversed range must be a readable string."""
        response = _get_profile(auth_client, start="2026-05-15", end="2026-05-01")
        data = response.data.decode()
        # The spec says the error explains the issue — check it contains "date"
        assert "date" in data.lower() or "before" in data.lower() or "start" in data.lower(), (
            "Error message should mention 'date', 'before', or 'start'"
        )


# ---------------------------------------------------------------------------
# 10. Malformed date
# ---------------------------------------------------------------------------

class TestMalformedDate:

    def test_malformed_start_returns_200(self, auth_client, seeded_db, frozen_today):
        """?start=not-a-date must return 200, not 500."""
        response = _get_profile(auth_client, start="not-a-date")
        assert response.status_code == 200, "Malformed date must not cause a 500"

    def test_malformed_start_shows_filter_error(self, auth_client, seeded_db, frozen_today):
        """Malformed ?start= must render a filter-error element."""
        response = _get_profile(auth_client, start="not-a-date")
        assert b"filter-error" in response.data, (
            "Malformed date must surface a filter-error message"
        )

    def test_malformed_start_renders_unfiltered(self, auth_client, seeded_db, frozen_today):
        """Malformed date must fall back to no filter — all expenses shown."""
        response = _get_profile(auth_client, start="not-a-date")
        data = response.data.decode()
        assert "7 transaction" in data, (
            "Malformed date should fall back to unfiltered (all 7 expenses)"
        )

    def test_malformed_end_returns_200(self, auth_client, seeded_db, frozen_today):
        """?end=bad-date must return 200."""
        response = _get_profile(auth_client, end="bad-date")
        assert response.status_code == 200

    def test_malformed_end_shows_filter_error(self, auth_client, seeded_db, frozen_today):
        """Malformed ?end= must render a filter-error element."""
        response = _get_profile(auth_client, end="bad-date")
        assert b"filter-error" in response.data

    def test_malformed_both_dates_returns_200(self, auth_client, seeded_db, frozen_today):
        """Both dates malformed must return 200."""
        response = auth_client.get("/profile?start=abc&end=xyz")
        assert response.status_code == 200

    @pytest.mark.parametrize("bad_value", [
        "2026-13-01",   # invalid month
        "2026-00-15",   # month zero
        "2026-02-30",   # Feb 30 doesn't exist
        "20260101",     # wrong format (no hyphens)
        "01/01/2026",   # US format
    ])
    def test_various_malformed_dates_return_200(
        self, auth_client, seeded_db, frozen_today, bad_value
    ):
        """Various malformed date strings must not 500."""
        response = _get_profile(auth_client, start=bad_value)
        assert response.status_code == 200, (
            f"Malformed date '{bad_value}' must not cause a 500"
        )


# ---------------------------------------------------------------------------
# 11. Empty start= and end= strings
# ---------------------------------------------------------------------------

class TestEmptyDateStrings:

    def test_empty_start_and_end_returns_200(self, auth_client, seeded_db, frozen_today):
        """?start=&end= (empty strings) must return 200."""
        response = auth_client.get("/profile?start=&end=")
        assert response.status_code == 200

    def test_empty_start_and_end_shows_no_error(self, auth_client, seeded_db, frozen_today):
        """Empty start/end strings must NOT render a filter-error element."""
        response = auth_client.get("/profile?start=&end=")
        assert b"filter-error" not in response.data, (
            "Empty date strings must not produce an error message"
        )

    def test_empty_start_and_end_shows_all_expenses(self, auth_client, seeded_db, frozen_today):
        """Empty date strings must behave like no filter — show all 7 expenses."""
        response = auth_client.get("/profile?start=&end=")
        data = response.data.decode()
        assert "7 transaction" in data, (
            "Empty date strings must fall back to unfiltered view"
        )


# ---------------------------------------------------------------------------
# 12. Empty-result case
# ---------------------------------------------------------------------------

class TestEmptyResultCase:

    def test_empty_range_returns_200(self, auth_client, seeded_db, frozen_today):
        """A range with no matching expenses must return 200."""
        response = _get_profile(auth_client, start="2025-01-01", end="2025-12-31")
        assert response.status_code == 200, "Empty result range must not 500"

    def test_empty_range_shows_zero_total(self, auth_client, seeded_db, frozen_today):
        """Empty result must show ₹0 total spent."""
        response = _get_profile(auth_client, start="2025-01-01", end="2025-12-31")
        data = response.data.decode()
        assert "₹0" in data, "Expected ₹0 total when no expenses match the filter"

    def test_empty_range_shows_zero_transactions(self, auth_client, seeded_db, frozen_today):
        """Empty result must show 0 transactions."""
        response = _get_profile(auth_client, start="2025-01-01", end="2025-12-31")
        data = response.data.decode()
        assert "0 transaction" in data, "Expected 0 transactions when no expenses match"

    def test_empty_range_shows_dash_top_category(self, auth_client, seeded_db, frozen_today):
        """Empty result must show '—' as top category."""
        response = _get_profile(auth_client, start="2025-01-01", end="2025-12-31")
        data = response.data.decode()
        assert "—" in data, "Expected '—' top category when no expenses match"

    def test_empty_range_no_exception(self, auth_client, seeded_db, frozen_today):
        """Empty result must not raise any exception (no 500, no stack trace)."""
        response = _get_profile(auth_client, start="2020-01-01", end="2020-01-02")
        assert response.status_code == 200, "Empty result must render without exceptions"
        assert b"Traceback" not in response.data, "No traceback must appear in response"
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 13. Filter state survives via URL only (no JS / no session storage)
# ---------------------------------------------------------------------------

class TestFilterStateViaURL:

    def test_filtered_url_with_fresh_login_applies_filter(self, client, seeded_db, frozen_today):
        """A freshly-logged-in session hitting a filtered URL still applies the filter."""
        # Log in fresh
        client.post(
            "/login",
            data={"email": "test@example.com", "password": "password123"},
            follow_redirects=False,
        )
        # Hit a filtered URL directly (no prior visit to /profile without filter)
        response = client.get("/profile?start=2026-05-01&end=2026-05-10")
        assert response.status_code == 200
        data = response.data.decode()
        assert "2 transaction" in data, (
            "Filter must be applied from URL alone without prior navigation"
        )
        assert "Jan food" not in data, "Jan expense must be excluded"

    def test_preset_url_with_fresh_login_applies_preset(self, client, seeded_db, frozen_today):
        """A freshly-logged-in session hitting /profile?preset=month applies the preset."""
        client.post(
            "/login",
            data={"email": "test@example.com", "password": "password123"},
            follow_redirects=False,
        )
        response = client.get("/profile?preset=month")
        assert response.status_code == 200
        data = response.data.decode()
        assert "3 transaction" in data, (
            "Month preset must apply from URL alone"
        )


# ---------------------------------------------------------------------------
# 14. SQL safety — injection sentinel
# ---------------------------------------------------------------------------

class TestSQLSafety:

    def test_sql_injection_in_start_does_not_500(self, auth_client, seeded_db, frozen_today):
        """SQL injection attempt in ?start= must be treated as malformed — no 500."""
        response = auth_client.get("/profile?start=2026-01-01%27%20OR%20%271%27%3D%271")
        assert response.status_code == 200, "SQL injection in start must not cause 500"

    def test_sql_injection_in_start_shows_error_or_unfiltered(
        self, auth_client, seeded_db, frozen_today
    ):
        """SQL injection sentinel is malformed — page must show error or unfiltered results."""
        response = auth_client.get("/profile?start=2026-01-01%27%20OR%20%271%27%3D%271")
        data = response.data.decode()
        # Either a filter-error is shown OR all 7 rows appear (no extra rows from injection)
        has_error = "filter-error" in data
        has_all_rows = "7 transaction" in data
        assert has_error or has_all_rows, (
            "SQL injection sentinel must result in error message or unfiltered safe response"
        )

    def test_sql_injection_does_not_return_extra_rows(
        self, auth_client, seeded_db, frozen_today
    ):
        """SQL injection must not return more rows than the total seed count."""
        response = auth_client.get(
            "/profile?start=2026-01-01' OR '1'='1&end=2026-12-31"
        )
        assert response.status_code == 200, "Must not 500 on injection attempt"
        data = response.data.decode()
        # The other user has ₹9999 — injection must not leak it
        assert "9,999" not in data, "SQL injection must not leak other user's data"
        assert "Other user expense" not in data, (
            "SQL injection must not expose other user's expense description"
        )


# ---------------------------------------------------------------------------
# 15. DB side effects — profile page is read-only
# ---------------------------------------------------------------------------

class TestDBSideEffects:

    def test_profile_get_does_not_alter_expense_count(
        self, auth_client, seeded_db, frozen_today, app
    ):
        """GET /profile must not insert or delete any expense rows."""
        count_before = _expense_count(app)
        _get_profile(auth_client)
        count_after = _expense_count(app)
        assert count_before == count_after, (
            "GET /profile must not modify the expenses table"
        )

    def test_filtered_profile_does_not_alter_expense_count(
        self, auth_client, seeded_db, frozen_today, app
    ):
        """GET /profile?preset=month must not insert or delete any expense rows."""
        count_before = _expense_count(app)
        _get_profile(auth_client, preset="month")
        count_after = _expense_count(app)
        assert count_before == count_after, (
            "Filtered GET /profile must not modify the expenses table"
        )

    def test_error_path_does_not_alter_expense_count(
        self, auth_client, seeded_db, frozen_today, app
    ):
        """Even the malformed-date error path must not modify the expenses table."""
        count_before = _expense_count(app)
        _get_profile(auth_client, start="not-a-date")
        count_after = _expense_count(app)
        assert count_before == count_after, (
            "Malformed-date error path must not modify the expenses table"
        )


# ---------------------------------------------------------------------------
# 16. Stat-note captions render filter.range_label
# ---------------------------------------------------------------------------

class TestStatNoteCaption:

    def test_no_filter_stat_notes_read_all_time(self, auth_client, seeded_db, frozen_today):
        """With no filter, both editable stat-note spans must read 'all time'."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        count = data.count("all time")
        assert count >= 2, (
            f"Expected 'all time' in at least 2 stat-note spans, found {count}"
        )

    def test_preset_year_stat_notes_read_this_year(self, auth_client, seeded_db, frozen_today):
        """With preset=year, both editable stat-note spans must read 'This year'."""
        response = _get_profile(auth_client, preset="year")
        data = response.data.decode()
        count = data.count("This year")
        assert count >= 2, (
            f"Expected 'This year' in at least 2 stat-note spans, found {count}"
        )

    def test_custom_range_stat_notes_show_formatted_dates(
        self, auth_client, seeded_db, frozen_today
    ):
        """Custom range stat notes must show 'May 01, 2026 – May 10, 2026'."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert "May 01, 2026" in data, "start_display must appear in range_label"
        assert "May 10, 2026" in data, "end_display must appear in range_label"

    def test_filter_caption_reflects_transaction_count(
        self, auth_client, seeded_db, frozen_today
    ):
        """filter-caption must show the correct count for the active window."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        # Month window has 3 expenses
        assert "3 transaction" in data, "filter-caption must show 3 for month preset"

    def test_filter_caption_reflects_range_label(self, auth_client, seeded_db, frozen_today):
        """filter-caption must include the active range_label text."""
        response = _get_profile(auth_client, preset="month")
        data = response.data.decode()
        assert "This month" in data, "filter-caption must include 'This month' range_label"

    def test_filter_caption_no_filter_says_all_time(self, auth_client, seeded_db, frozen_today):
        """filter-caption without active filter must say 'all time'."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        assert "all time" in data, "filter-caption must contain 'all time' with no filter"


# ---------------------------------------------------------------------------
# 17. Preset=all explicitly → no filter
# ---------------------------------------------------------------------------

class TestPresetAll:

    def test_preset_all_returns_200(self, auth_client, seeded_db, frozen_today):
        """GET /profile?preset=all returns 200."""
        response = _get_profile(auth_client, preset="all")
        assert response.status_code == 200

    def test_preset_all_shows_all_expenses(self, auth_client, seeded_db, frozen_today):
        """preset=all is equivalent to no filter — shows all 7 expenses."""
        response = _get_profile(auth_client, preset="all")
        data = response.data.decode()
        assert "7 transaction" in data, "preset=all must show all expenses"

    def test_preset_all_range_label_is_all_time(self, auth_client, seeded_db, frozen_today):
        """preset=all must render 'all time' as range_label (is_active=False)."""
        response = _get_profile(auth_client, preset="all")
        data = response.data.decode()
        assert "all time" in data, "preset=all must produce 'all time' range_label"

    def test_preset_all_link_is_active(self, auth_client, seeded_db, frozen_today):
        """'All time' preset link must be marked active with preset=all."""
        response = _get_profile(auth_client, preset="all")
        data = response.data.decode()
        assert "filter-preset--active" in data, "Expected active preset class"


# ---------------------------------------------------------------------------
# 18. Input pre-fill — date inputs echo back the active range
# ---------------------------------------------------------------------------

class TestDateInputPrefill:

    def test_start_input_prefilled_with_active_start(self, auth_client, seeded_db, frozen_today):
        """Start date input must be pre-filled with the active start value."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert 'value="2026-05-01"' in data, "Start input must be pre-filled with 2026-05-01"

    def test_end_input_prefilled_with_active_end(self, auth_client, seeded_db, frozen_today):
        """End date input must be pre-filled with the active end value."""
        response = _get_profile(auth_client, start="2026-05-01", end="2026-05-10")
        data = response.data.decode()
        assert 'value="2026-05-10"' in data, "End input must be pre-filled with 2026-05-10"

    def test_no_filter_inputs_are_empty(self, auth_client, seeded_db, frozen_today):
        """With no filter, start and end inputs must have empty value attributes."""
        response = _get_profile(auth_client)
        data = response.data.decode()
        # The template renders: value="{{ filter.start or '' }}"
        # With no filter, filter.start is None → value=""
        assert 'value=""' in data, "Inputs must have empty value when no filter is active"
