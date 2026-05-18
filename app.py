import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

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

    user = {
        "name":         "Demo User",
        "email":        "demo@spendly.com",
        "initial":      "D",
        "member_since": "May 2026",
    }

    stats = {
        "total_spent":  "₹18,240",
        "tx_count":     8,
        "top_category": "Bills",
    }

    transactions = [
        {"date": "May 16", "description": "Miscellaneous",
         "category": "other",         "category_label": "Other",
         "icon": "more-horizontal", "amount": "₹15"},
        {"date": "May 14", "description": "Coffee and snacks",
         "category": "food",          "category_label": "Food",
         "icon": "utensils", "amount": "₹9"},
        {"date": "May 12", "description": "Clothing",
         "category": "shopping",      "category_label": "Shopping",
         "icon": "shopping-bag", "amount": "₹90"},
        {"date": "May 10", "description": "Movie tickets",
         "category": "entertainment", "category_label": "Entertainment",
         "icon": "film", "amount": "₹25"},
        {"date": "May 08", "description": "Pharmacy",
         "category": "health",        "category_label": "Health",
         "icon": "heart-pulse", "amount": "₹45"},
        {"date": "May 05", "description": "Electricity bill",
         "category": "bills",         "category_label": "Bills",
         "icon": "zap", "amount": "₹120"},
        {"date": "May 03", "description": "Uber rides",
         "category": "transport",     "category_label": "Transport",
         "icon": "car", "amount": "₹35"},
        {"date": "May 01", "description": "Lunch at cafe",
         "category": "food",          "category_label": "Food",
         "icon": "utensils", "amount": "₹13"},
    ]

    breakdown = [
        {"category_label": "Bills",         "amount": "₹120",
         "percent": 75, "bar_class": "lbar-fill--purple", "icon": "zap"},
        {"category_label": "Shopping",      "amount": "₹90",
         "percent": 56, "bar_class": "lbar-fill--orange", "icon": "shopping-bag"},
        {"category_label": "Health",        "amount": "₹45",
         "percent": 28, "bar_class": "lbar-fill--blue",   "icon": "heart-pulse"},
        {"category_label": "Transport",     "amount": "₹35",
         "percent": 22, "bar_class": "lbar-fill--orange", "icon": "car"},
        {"category_label": "Entertainment", "amount": "₹25",
         "percent": 16, "bar_class": "lbar-fill--purple", "icon": "film"},
        {"category_label": "Food",          "amount": "₹22",
         "percent": 14, "bar_class": "lbar-fill--blue",   "icon": "utensils"},
    ]

    return render_template("profile.html",
                           user=user, stats=stats,
                           transactions=transactions, breakdown=breakdown)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
