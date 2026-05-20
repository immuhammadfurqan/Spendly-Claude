import os
import sqlite3
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db
from database.queries import (
    build_user_context,
    build_stats,
    build_transactions,
    build_breakdown,
    resolve_date_range,
    DATE_PRESETS,
    KNOWN_CATEGORIES,
    CATEGORY_OPTIONS,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", name="", email="")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not name:
        return render_template("register.html", name=name, email=email,
                               error="Full name is required.")
    if not email:
        return render_template("register.html", name=name, email=email,
                               error="Email address is required.")
    if len(password) < 8:
        return render_template("register.html", name=name, email=email,
                               error="Password must be at least 8 characters.")

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template("register.html", name=name, email=email,
                               error="An account with that email already exists.")
    finally:
        conn.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html", email="")

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email:
        return render_template("login.html", email=email,
                               error="Email address is required.")
    if not password:
        return render_template("login.html", email=email,
                               error="Password is required.")

    conn = get_db()
    user = conn.execute(
        "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", email=email,
                               error="Invalid email or password.")

    session["user_id"] = user["id"]
    session["name"]    = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()
    user_row = conn.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if user_row is None:
        conn.close()
        session.clear()
        return redirect(url_for("login"))

    filt = resolve_date_range(request.args, date.today())

    sql = "SELECT amount, category, date, description FROM expenses WHERE user_id = ?"
    params = [user_row["id"]]
    if filt["is_active"]:
        if filt["start"]:
            sql += " AND date >= ?"
            params.append(filt["start"])
        if filt["end"]:
            sql += " AND date <= ?"
            params.append(filt["end"])
    sql += " ORDER BY date DESC, id DESC"

    expense_rows = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        "profile.html",
        user=build_user_context(user_row),
        stats=build_stats(expense_rows),
        transactions=build_transactions(expense_rows),
        breakdown=build_breakdown(expense_rows),
        date_filter=filt,
        date_presets=DATE_PRESETS,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORY_OPTIONS,
            amount="",
            category="",
            date=date.today().isoformat(),
            description="",
            error=None,
        )

    amount_raw      = request.form.get("amount", "").strip()
    category_raw    = request.form.get("category", "").strip().lower()
    date_raw        = request.form.get("date", "").strip()
    description_raw = request.form.get("description", "").strip()

    def fail(msg, *, amount=amount_raw, category=category_raw,
             date=date_raw, description=description_raw):
        return render_template(
            "add_expense.html",
            categories=CATEGORY_OPTIONS,
            amount=amount,
            category=category,
            date=date,
            description=description,
            error=msg,
        )

    try:
        amount = float(amount_raw)
    except ValueError:
        return fail("Amount must be a number.")
    if amount <= 0:
        return fail("Amount must be greater than zero.")
    if amount > 10_000_000:
        return fail("Amount is too large.")

    if category_raw not in KNOWN_CATEGORIES:
        return fail("Please choose a valid category.")

    try:
        parsed_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
    except ValueError:
        return fail("Date must be in YYYY-MM-DD format.")
    if parsed_date > date.today() + timedelta(days=1):
        return fail("Date cannot be in the future.")

    if len(description_raw) > 200:
        return fail("Description must be 200 characters or fewer.")
    description_value = description_raw or None

    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (session["user_id"], amount, category_raw,
             parsed_date.isoformat(), description_value),
        )
        conn.commit()
    finally:
        if conn is not None:
            conn.close()

    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode, port=5001)
