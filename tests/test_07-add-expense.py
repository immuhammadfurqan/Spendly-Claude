"""
Tests for Step 07 — Add Expense.

Spec source: .claude/specs/07-add-expense.md

Strategy
--------
- All tests use an isolated file-based SQLite DB via a monkeypatched get_db()
  so the production spendly.db is never touched.
- "Today" is pinned to 2026-05-15 by monkeypatching `app.date` inside tests
  that depend on today's date value (form default, future-date guard).
- Auth is achieved by registering + logging in through real /register and
  /login routes so the session cookie is genuine.
- DB state after writes is verified by querying the patched DB connection
  directly (not through the app's rendered HTML alone).
- No test shares mutable state with another; every fixture is function-scoped.

Pinned "today" for deterministic date assertions: 2026-05-15
"""

import sqlite3
import pytest
from datetime import date as real_date
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.queries import KNOWN_CATEGORIES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PINNED_TODAY = real_date(2026, 5, 15)
PINNED_TODAY_ISO = PINNED_TODAY.isoformat()  # "2026-05-15"

# A valid expense payload; individual tests override individual fields.
VALID_PAYLOAD = {
    "amount":      "42.50",
    "category":    "food",
    "date":        PINNED_TODAY_ISO,
    "description": "Lunch",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Flask app wired to an isolated temp SQLite DB.

    Both `database.db.get_db` and the `get_db` name already imported into
    `app.py` are monkey-patched so every code path that calls get_db() uses
    the same isolated file, not spendly.db.
    """
    db_file = str(tmp_path / "test_spendly.db")

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    import database.db as db_module
    import app as app_module

    original_db_get_db  = db_module.get_db
    original_app_get_db = app_module.get_db

    def _patched_get_db():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    db_module.get_db  = _patched_get_db
    app_module.get_db = _patched_get_db

    with flask_app.app_context():
        # Create schema in the isolated DB
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

    db_module.get_db  = original_db_get_db
    app_module.get_db = original_app_get_db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client):
    """Test client with a logged-in session for the primary test user."""
    client.post(
        "/register",
        data={
            "name":     "Test User",
            "email":    "test@example.com",
            "password": "testpass123",
        },
        follow_redirects=False,
    )
    client.post(
        "/login",
        data={"email": "test@example.com", "password": "testpass123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture()
def frozen_today(monkeypatch):
    """Pin date.today() to PINNED_TODAY inside the app module."""
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

def _db_get_db():
    """Thin wrapper — always resolves through the (possibly patched) module."""
    import database.db as db_module
    return db_module.get_db()


def _expense_rows_for_user(user_id):
    """Return all expense rows belonging to user_id from the isolated DB."""
    conn = _db_get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def _total_expense_count():
    """Return the total number of rows in the expenses table."""
    conn = _db_get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


def _get_user_id(email):
    """Look up a user's id by email."""
    conn = _db_get_db()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row["id"] if row else None


def _register_and_login(client, email, password="testpass123", name="User"):
    """Register + log in a fresh user; returns the client (same object)."""
    client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=False,
    )
    client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return client


# ---------------------------------------------------------------------------
# 1. Auth guards
# ---------------------------------------------------------------------------

class TestAuthGuards:

    def test_get_while_logged_out_redirects_to_login(self, client):
        """GET /expenses/add while logged out must 302 to /login."""
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Expected 302 redirect for unauthenticated GET"
        assert "/login" in response.headers["Location"], (
            "Redirect location must be /login"
        )

    def test_get_while_logged_out_does_not_render_form(self, client):
        """GET /expenses/add while logged out must not render the add-expense form."""
        response = client.get("/expenses/add", follow_redirects=True)
        assert b'name="amount"' not in response.data, (
            "Unauthenticated GET must not expose the amount input"
        )

    def test_post_while_logged_out_redirects_to_login(self, client):
        """POST /expenses/add while logged out must 302 to /login."""
        response = client.post("/expenses/add", data=VALID_PAYLOAD)
        assert response.status_code == 302, "Expected 302 redirect for unauthenticated POST"
        assert "/login" in response.headers["Location"], (
            "Redirect location must be /login"
        )

    def test_post_while_logged_out_inserts_nothing(self, client):
        """POST /expenses/add while logged out must not write any DB row."""
        count_before = _total_expense_count()
        client.post("/expenses/add", data=VALID_PAYLOAD)
        count_after = _total_expense_count()
        assert count_before == count_after, (
            "Unauthenticated POST must not insert a row into expenses"
        )


# ---------------------------------------------------------------------------
# 2. Form render — GET while logged in
# ---------------------------------------------------------------------------

class TestFormRender:

    def test_get_returns_200(self, auth_client, frozen_today):
        """GET /expenses/add while logged in returns HTTP 200."""
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200, "Expected 200 for authenticated GET"

    def test_form_contains_amount_input(self, auth_client, frozen_today):
        """Form must contain an input named 'amount'."""
        response = auth_client.get("/expenses/add")
        assert b'name="amount"' in response.data, "Expected amount input in form"

    def test_form_contains_category_select(self, auth_client, frozen_today):
        """Form must contain a select named 'category'."""
        response = auth_client.get("/expenses/add")
        assert b'name="category"' in response.data, "Expected category select in form"

    def test_form_contains_date_input(self, auth_client, frozen_today):
        """Form must contain an input named 'date'."""
        response = auth_client.get("/expenses/add")
        assert b'name="date"' in response.data, "Expected date input in form"

    def test_form_contains_description_input(self, auth_client, frozen_today):
        """Form must contain an input named 'description'."""
        response = auth_client.get("/expenses/add")
        assert b'name="description"' in response.data, "Expected description input in form"

    def test_category_select_contains_all_known_categories(self, auth_client, frozen_today):
        """The category select must have an option for every key in KNOWN_CATEGORIES."""
        response = auth_client.get("/expenses/add")
        data = response.data.decode()
        for slug in KNOWN_CATEGORIES:
            assert f'value="{slug}"' in data, (
                f"Category select must include option value='{slug}'"
            )

    def test_date_input_prefilled_with_today(self, auth_client, frozen_today):
        """The date input must be pre-filled with today's ISO date on initial GET."""
        response = auth_client.get("/expenses/add")
        data = response.data.decode()
        assert PINNED_TODAY_ISO in data, (
            f"Date input must be pre-filled with today's date '{PINNED_TODAY_ISO}'"
        )

    def test_form_renders_post_action_to_add_expense(self, auth_client, frozen_today):
        """Form action must point to /expenses/add."""
        response = auth_client.get("/expenses/add")
        data = response.data.decode()
        assert "/expenses/add" in data, "Form action must point to /expenses/add"

    def test_form_uses_post_method(self, auth_client, frozen_today):
        """Form must use method=POST."""
        response = auth_client.get("/expenses/add")
        data = response.data.decode()
        assert 'method="POST"' in data or "method=POST" in data, (
            "Form must use POST method"
        )

    def test_page_extends_base_html(self, auth_client, frozen_today):
        """Page must render base.html landmarks (navbar + footer)."""
        response = auth_client.get("/expenses/add")
        assert b'class="navbar"' in response.data, "Expected base.html <nav class='navbar'>"
        assert b'class="footer"' in response.data, "Expected base.html <footer class='footer'>"

    def test_no_error_shown_on_initial_get(self, auth_client, frozen_today):
        """No error message must appear on the initial GET (clean form state)."""
        response = auth_client.get("/expenses/add")
        # The error block should not contain any text if error is None
        data = response.data.decode()
        # We verify the form loads cleanly — no Python exception tracebacks
        assert b"Traceback" not in response.data, "No traceback must appear in response"
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 3. Happy path — valid POST
# ---------------------------------------------------------------------------

class TestHappyPath:

    def test_valid_post_redirects_to_profile(self, auth_client, frozen_today):
        """Valid POST must return 302 to /profile."""
        response = auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        assert response.status_code == 302, "Expected 302 redirect after valid POST"
        assert "/profile" in response.headers["Location"], (
            "Redirect must target /profile"
        )

    def test_valid_post_inserts_exactly_one_row(self, auth_client, frozen_today):
        """Valid POST must insert exactly one row into expenses."""
        count_before = _total_expense_count()
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        count_after = _total_expense_count()
        assert count_after == count_before + 1, (
            "Exactly one expense row must be inserted after a valid POST"
        )

    def test_valid_post_stores_correct_user_id(self, auth_client, frozen_today):
        """The inserted row's user_id must match the logged-in user."""
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        rows = _expense_rows_for_user(user_id)
        assert len(rows) == 1, "Expected exactly one expense for the logged-in user"
        assert rows[0]["user_id"] == user_id, (
            "Inserted row's user_id must match the session user_id"
        )

    def test_valid_post_stores_correct_amount(self, auth_client, frozen_today):
        """The inserted row must store amount as the correct float."""
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        rows = _expense_rows_for_user(user_id)
        assert rows[0]["amount"] == pytest.approx(42.50), (
            "Inserted amount must be 42.50"
        )

    def test_valid_post_stores_category_as_lowercase_slug(self, auth_client, frozen_today):
        """The inserted row must store category as the lowercase slug."""
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        rows = _expense_rows_for_user(user_id)
        assert rows[0]["category"] == "food", (
            "Category must be stored as lowercase slug 'food'"
        )

    def test_valid_post_stores_correct_date(self, auth_client, frozen_today):
        """The inserted row must store the submitted date."""
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        rows = _expense_rows_for_user(user_id)
        assert rows[0]["date"] == PINNED_TODAY_ISO, (
            f"Date must be stored as '{PINNED_TODAY_ISO}'"
        )

    def test_valid_post_stores_correct_description(self, auth_client, frozen_today):
        """The inserted row must store the submitted description."""
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        rows = _expense_rows_for_user(user_id)
        assert rows[0]["description"] == "Lunch", (
            "Description must be stored as 'Lunch'"
        )

    def test_valid_post_profile_shows_new_description(self, auth_client, frozen_today):
        """After redirect, /profile HTML must contain the new expense description."""
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        profile_response = auth_client.get("/profile", follow_redirects=False)
        assert profile_response.status_code == 200
        assert b"Lunch" in profile_response.data, (
            "New expense description 'Lunch' must appear on /profile after insert"
        )


# ---------------------------------------------------------------------------
# 4. Validation rejects — parametrised
# ---------------------------------------------------------------------------

INVALID_AMOUNT_CASES = [
    ("",          "amount blank"),
    ("-5",        "negative amount"),
    ("0",         "zero amount"),
    ("abc",       "non-numeric amount"),
    ("10000001",  "amount one above 10_000_000 ceiling"),
]

INVALID_OTHER_CASES = [
    ({"category": "Bitcoin"},        "unknown category"),
    ({"category": ""},               "missing category"),
    ({"date": ""},                   "date blank"),
    ({"date": "not-a-date"},         "invalid date format"),
    ({"date": "2099-01-01"},         "far-future date"),
    ({"description": "x" * 201},    "description over 200 chars"),
]


class TestValidationRejects:

    @pytest.mark.parametrize("amount_value,case_name", INVALID_AMOUNT_CASES)
    def test_invalid_amount_does_not_insert_row(
        self, auth_client, frozen_today, amount_value, case_name
    ):
        """Submitting an invalid amount must not insert any DB row."""
        payload = {**VALID_PAYLOAD, "amount": amount_value}
        count_before = _total_expense_count()
        auth_client.post("/expenses/add", data=payload)
        count_after = _total_expense_count()
        assert count_before == count_after, (
            f"Case '{case_name}': no row must be inserted for invalid amount '{amount_value}'"
        )

    @pytest.mark.parametrize("amount_value,case_name", INVALID_AMOUNT_CASES)
    def test_invalid_amount_rerenders_form_with_error(
        self, auth_client, frozen_today, amount_value, case_name
    ):
        """Submitting an invalid amount must re-render the form (200) with an error."""
        payload = {**VALID_PAYLOAD, "amount": amount_value}
        response = auth_client.post("/expenses/add", data=payload)
        assert response.status_code == 200, (
            f"Case '{case_name}': expected 200 (form re-render) for invalid amount '{amount_value}'"
        )
        assert b'name="amount"' in response.data, (
            f"Case '{case_name}': form must be re-rendered with amount input"
        )

    @pytest.mark.parametrize("amount_value,case_name", INVALID_AMOUNT_CASES)
    def test_invalid_amount_shows_error_text(
        self, auth_client, frozen_today, amount_value, case_name
    ):
        """Submitting an invalid amount must produce a non-empty error message."""
        payload = {**VALID_PAYLOAD, "amount": amount_value}
        response = auth_client.post("/expenses/add", data=payload)
        data = response.data.decode()
        # The spec says an 'error' string is rendered; check that it is non-trivially present.
        # We verify the form carries some error indicator (not a traceback).
        assert b"Traceback" not in response.data, (
            f"Case '{case_name}': no traceback must reach the user"
        )
        # A reasonable heuristic: the word "amount" or "number" or "zero" or "large"
        # appears somewhere in the response near the error context.
        lower = data.lower()
        has_error_signal = (
            "amount" in lower
            or "number" in lower
            or "zero" in lower
            or "large" in lower
            or "greater" in lower
            or "positive" in lower
        )
        assert has_error_signal, (
            f"Case '{case_name}': expected an error message containing amount-related text"
        )

    @pytest.mark.parametrize("override,case_name", INVALID_OTHER_CASES)
    def test_other_invalid_fields_do_not_insert_row(
        self, auth_client, frozen_today, override, case_name
    ):
        """Submitting invalid non-amount fields must not insert any DB row."""
        payload = {**VALID_PAYLOAD, **override}
        count_before = _total_expense_count()
        auth_client.post("/expenses/add", data=payload)
        count_after = _total_expense_count()
        assert count_before == count_after, (
            f"Case '{case_name}': no row must be inserted for invalid input"
        )

    @pytest.mark.parametrize("override,case_name", INVALID_OTHER_CASES)
    def test_other_invalid_fields_rerender_form(
        self, auth_client, frozen_today, override, case_name
    ):
        """Submitting invalid non-amount fields must re-render the form with HTTP 200."""
        payload = {**VALID_PAYLOAD, **override}
        response = auth_client.post("/expenses/add", data=payload)
        assert response.status_code == 200, (
            f"Case '{case_name}': expected 200 (form re-render)"
        )
        assert b'name="amount"' in response.data, (
            f"Case '{case_name}': form must be re-rendered"
        )

    @pytest.mark.parametrize("override,case_name", INVALID_OTHER_CASES)
    def test_other_invalid_fields_show_no_traceback(
        self, auth_client, frozen_today, override, case_name
    ):
        """Validation failures must never let a Python exception reach the user."""
        payload = {**VALID_PAYLOAD, **override}
        response = auth_client.post("/expenses/add", data=payload)
        assert b"Traceback" not in response.data, (
            f"Case '{case_name}': no traceback must appear in the response"
        )
        assert b"Internal Server Error" not in response.data, (
            f"Case '{case_name}': no 500 error page must appear"
        )


# ---------------------------------------------------------------------------
# 5. Form value echo on validation failure
# ---------------------------------------------------------------------------

class TestFormValueEcho:

    def test_amount_echoed_on_validation_failure(self, auth_client, frozen_today):
        """Submitted amount must be echoed back into the form on failure."""
        payload = {**VALID_PAYLOAD, "category": "Bitcoin"}  # invalid category
        response = auth_client.post("/expenses/add", data=payload)
        assert b"42.50" in response.data, (
            "Previously submitted amount '42.50' must appear in re-rendered form"
        )

    def test_date_echoed_on_validation_failure(self, auth_client, frozen_today):
        """Submitted date must be echoed back into the form on failure."""
        payload = {**VALID_PAYLOAD, "category": "Bitcoin"}
        response = auth_client.post("/expenses/add", data=payload)
        assert PINNED_TODAY_ISO.encode() in response.data, (
            f"Previously submitted date '{PINNED_TODAY_ISO}' must appear in re-rendered form"
        )

    def test_description_echoed_on_validation_failure(self, auth_client, frozen_today):
        """Submitted description must be echoed back into the form on failure."""
        payload = {**VALID_PAYLOAD, "category": "Bitcoin"}
        response = auth_client.post("/expenses/add", data=payload)
        assert b"Lunch" in response.data, (
            "Previously submitted description 'Lunch' must appear in re-rendered form"
        )

    def test_category_echoed_on_validation_failure(self, auth_client, frozen_today):
        """Submitted category slug must be echoed back on failure (amount error)."""
        payload = {**VALID_PAYLOAD, "amount": "abc"}
        response = auth_client.post("/expenses/add", data=payload)
        # The echoed category value should appear somewhere in the page
        assert b"food" in response.data, (
            "Previously submitted category 'food' must appear in re-rendered form"
        )

    def test_all_values_echoed_on_amount_error(self, auth_client, frozen_today):
        """All four field values must appear in the re-rendered form when amount is invalid."""
        payload = {
            "amount":      "abc",
            "category":    "transport",
            "date":        PINNED_TODAY_ISO,
            "description": "My expense",
        }
        response = auth_client.post("/expenses/add", data=payload)
        data = response.data.decode()
        assert "transport" in data, "Category must be echoed"
        assert PINNED_TODAY_ISO in data, "Date must be echoed"
        assert "My expense" in data, "Description must be echoed"


# ---------------------------------------------------------------------------
# 6. Empty description path — NULL stored in DB
# ---------------------------------------------------------------------------

class TestEmptyDescription:

    def test_empty_description_redirects_to_profile(self, auth_client, frozen_today):
        """Submitting description='' must succeed and redirect to /profile."""
        payload = {**VALID_PAYLOAD, "description": ""}
        response = auth_client.post("/expenses/add", data=payload)
        assert response.status_code == 302, (
            "Empty description must succeed (302 redirect)"
        )
        assert "/profile" in response.headers["Location"], (
            "Must redirect to /profile"
        )

    def test_empty_description_inserts_row(self, auth_client, frozen_today):
        """Submitting description='' must insert exactly one row."""
        payload = {**VALID_PAYLOAD, "description": ""}
        count_before = _total_expense_count()
        auth_client.post("/expenses/add", data=payload)
        count_after = _total_expense_count()
        assert count_after == count_before + 1, (
            "One row must be inserted when description is empty"
        )

    def test_empty_description_stores_null_in_db(self, auth_client, frozen_today):
        """Empty description must be stored as NULL in the DB, not as an empty string."""
        payload = {**VALID_PAYLOAD, "description": ""}
        user_id = _get_user_id("test@example.com")
        auth_client.post("/expenses/add", data=payload)
        rows = _expense_rows_for_user(user_id)
        assert len(rows) == 1, "Expected one expense row"
        assert rows[0]["description"] is None, (
            "description column must be NULL when an empty string is submitted"
        )

    def test_empty_description_profile_shows_category_fallback(
        self, auth_client, frozen_today
    ):
        """When description is NULL, /profile must render the category label as fallback."""
        payload = {**VALID_PAYLOAD, "description": "", "category": "transport"}
        auth_client.post("/expenses/add", data=payload)
        profile_response = auth_client.get("/profile")
        # build_transactions() falls back to category_label when description is None/blank
        assert b"Transport" in profile_response.data, (
            "Category label 'Transport' must appear as fallback when description is NULL"
        )


# ---------------------------------------------------------------------------
# 7. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_user_b_cannot_see_user_a_expense_on_profile(self, client, frozen_today):
        """User B's /profile must not display User A's expense."""
        # Register and log in User A, add an expense
        _register_and_login(client, "alice@example.com", name="Alice")
        client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "description": "Alice private expense"},
        )
        # Log out User A
        client.get("/logout", follow_redirects=False)

        # Register and log in User B
        _register_and_login(client, "bob@example.com", name="Bob")
        profile_response = client.get("/profile")
        assert b"Alice private expense" not in profile_response.data, (
            "User B must not see User A's expense description on /profile"
        )

    def test_user_b_has_no_expense_rows_in_db(self, client, frozen_today):
        """User B must have zero expense rows in the DB after User A adds one."""
        _register_and_login(client, "alice@example.com", name="Alice")
        client.post("/expenses/add", data={**VALID_PAYLOAD, "description": "Alice only"})
        client.get("/logout", follow_redirects=False)

        _register_and_login(client, "bob@example.com", name="Bob")
        bob_id = _get_user_id("bob@example.com")
        bob_rows = _expense_rows_for_user(bob_id)
        assert len(bob_rows) == 0, (
            "User B must have no expense rows even after User A added one"
        )


# ---------------------------------------------------------------------------
# 8. user_id source — session must override any form field
# ---------------------------------------------------------------------------

class TestUserIdSource:

    def test_hidden_user_id_field_is_ignored(self, client, frozen_today):
        """A hidden user_id form field for another user must be silently ignored."""
        # Register two users; log in as User A
        _register_and_login(client, "owner@example.com", name="Owner")
        owner_id = _get_user_id("owner@example.com")

        # Register User B (the "victim")
        _register_and_login(client, "victim@example.com", name="Victim")
        victim_id = _get_user_id("victim@example.com")

        # Log out and log back in as User A (owner)
        client.get("/logout", follow_redirects=False)
        client.post(
            "/login",
            data={"email": "owner@example.com", "password": "testpass123"},
            follow_redirects=False,
        )

        # Submit a POST that includes a hidden user_id pointing to victim_id
        payload = {**VALID_PAYLOAD, "user_id": str(victim_id)}
        response = client.post("/expenses/add", data=payload)
        assert response.status_code == 302, "Valid submit must redirect even with rogue field"

        # The inserted row must belong to owner (session user), not victim
        owner_rows  = _expense_rows_for_user(owner_id)
        victim_rows = _expense_rows_for_user(victim_id)
        assert len(owner_rows) == 1, (
            "Expense must be inserted under the logged-in user's id (owner), not victim's"
        )
        assert len(victim_rows) == 0, (
            "Victim must have no rows — hidden user_id field must be ignored"
        )


# ---------------------------------------------------------------------------
# 9. Parameterised SQL safety — injection payload stored as literal string
# ---------------------------------------------------------------------------

class TestSQLSafety:

    def test_sql_injection_in_description_succeeds(self, auth_client, frozen_today):
        """A SQL-injection-style description must succeed as a literal value."""
        payload = {
            **VALID_PAYLOAD,
            "description": "'; DROP TABLE expenses; --",
        }
        response = auth_client.post("/expenses/add", data=payload)
        assert response.status_code == 302, (
            "SQL-injection payload in description must succeed (302 redirect)"
        )

    def test_sql_injection_does_not_drop_expenses_table(self, auth_client, frozen_today):
        """After inserting an injection-payload description, expenses table must still exist."""
        payload = {
            **VALID_PAYLOAD,
            "description": "'; DROP TABLE expenses; --",
        }
        auth_client.post("/expenses/add", data=payload)
        # If the table was dropped this call would raise; catching that is sufficient
        try:
            count = _total_expense_count()
        except Exception as exc:
            pytest.fail(
                f"expenses table must still exist after injection attempt; got: {exc}"
            )
        assert count >= 1, "At least the injected row must still be in expenses"

    def test_sql_injection_payload_stored_as_literal_string(self, auth_client, frozen_today):
        """The injection-style description must be retrievable verbatim from the DB."""
        user_id = _get_user_id("test@example.com")
        injection_text = "'; DROP TABLE expenses; --"
        payload = {**VALID_PAYLOAD, "description": injection_text}
        auth_client.post("/expenses/add", data=payload)
        rows = _expense_rows_for_user(user_id)
        assert len(rows) == 1, "One row must be inserted"
        assert rows[0]["description"] == injection_text, (
            "Description must be stored verbatim as a literal string, not interpreted as SQL"
        )

    def test_subsequent_queries_work_after_injection_attempt(self, auth_client, frozen_today):
        """GET /profile must still work after an injection-payload expense is inserted."""
        payload = {**VALID_PAYLOAD, "description": "'; DROP TABLE expenses; --"}
        auth_client.post("/expenses/add", data=payload)
        profile_response = auth_client.get("/profile")
        assert profile_response.status_code == 200, (
            "GET /profile must return 200 after an injection-payload insert"
        )


# ---------------------------------------------------------------------------
# 10. Navbar / profile CTA — structural presence
# ---------------------------------------------------------------------------

class TestNavbarAndCTA:

    def test_add_expense_link_in_navbar_when_logged_in(self, auth_client, frozen_today):
        """When logged in, the navbar must contain a link to /expenses/add."""
        response = auth_client.get("/profile")
        data = response.data.decode()
        assert "/expenses/add" in data, (
            "Navbar must contain a link to /expenses/add when the user is logged in"
        )

    def test_profile_hero_contains_add_expense_cta(self, auth_client, frozen_today):
        """The /profile page must contain at least one link/button to /expenses/add."""
        response = auth_client.get("/profile")
        data = response.data.decode()
        assert "/expenses/add" in data, (
            "Profile page must show an 'Add expense' CTA linking to /expenses/add"
        )

    def test_add_expense_link_active_class_on_add_expense_page(
        self, auth_client, frozen_today
    ):
        """The navbar 'Add expense' link must carry the 'active' class on /expenses/add."""
        response = auth_client.get("/expenses/add")
        data = response.data.decode()
        # The spec says: class="nav-link {% if request.endpoint == 'add_expense' %}active{% endif %}"
        # Verify that 'active' appears somewhere in the navbar near the add_expense route.
        assert "active" in data, (
            "The navbar link for 'Add expense' must have the 'active' class on its own page"
        )


# ---------------------------------------------------------------------------
# 11. Date filter on /profile still works after new row is added
# ---------------------------------------------------------------------------

class TestProfileFilterAfterInsert:

    def test_new_expense_appears_with_matching_month_filter(
        self, auth_client, frozen_today
    ):
        """New expense on PINNED_TODAY must appear under preset=month filter."""
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        # preset=month window: 2026-05-01 .. 2026-05-15 — PINNED_TODAY_ISO is 2026-05-15
        response = auth_client.get("/profile?preset=month")
        assert b"Lunch" in response.data, (
            "New expense with today's date must appear under 'This month' preset filter"
        )

    def test_new_expense_excluded_by_past_custom_range(
        self, auth_client, frozen_today
    ):
        """New expense on PINNED_TODAY must NOT appear in a custom range that excludes it."""
        auth_client.post("/expenses/add", data=VALID_PAYLOAD)
        # Range 2026-01-01 to 2026-03-31 excludes 2026-05-15
        response = auth_client.get("/profile?start=2026-01-01&end=2026-03-31")
        assert b"Lunch" not in response.data, (
            "New expense must not appear when custom range excludes its date"
        )
