"""Helpers that turn raw expense / user rows into the context the
profile.html template renders. Pure functions — no Flask, no I/O."""

from datetime import datetime


CATEGORY_ICONS = {
    "food":          "utensils",
    "transport":     "car",
    "bills":         "zap",
    "health":        "heart-pulse",
    "entertainment": "film",
    "shopping":      "shopping-bag",
    "other":         "more-horizontal",
}

BAR_CLASSES = ("lbar-fill--purple", "lbar-fill--orange", "lbar-fill--blue")

KNOWN_CATEGORIES = set(CATEGORY_ICONS.keys())


def format_amount(value):
    return "₹" + f"{int(round(value or 0)):,}"


def build_user_context(user_row):
    name = (user_row["name"] or "").strip()
    initial = name[:1].upper() if name else "?"

    created_at = user_row["created_at"] or ""
    try:
        member_since = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S").strftime("%b %Y")
    except ValueError:
        try:
            member_since = datetime.strptime(created_at[:10], "%Y-%m-%d").strftime("%b %Y")
        except ValueError:
            member_since = ""

    return {
        "name":         name,
        "email":        user_row["email"],
        "initial":      initial,
        "member_since": member_since,
    }


# === BUILD_TRANSACTIONS START ===
def build_transactions(expense_rows):
    transactions = []
    for row in expense_rows:
        raw_category = row["category"]
        original_slug = (raw_category or "").strip().lower()
        if original_slug in KNOWN_CATEGORIES:
            bucketed_slug = original_slug
            category_label = original_slug.title()
        else:
            bucketed_slug = "other"
            if raw_category is None or not str(raw_category).strip():
                category_label = "Other"
            else:
                category_label = raw_category

        raw_date = row["date"]
        try:
            date_display = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%b %d")
        except (ValueError, TypeError):
            date_display = raw_date

        description = row["description"]
        if description is None or not str(description).strip():
            description = category_label

        transactions.append({
            "date":           date_display,
            "description":    description,
            "category":       bucketed_slug,
            "category_label": category_label,
            "icon":           CATEGORY_ICONS[bucketed_slug],
            "amount":         format_amount(row["amount"]),
        })
    return transactions
# === BUILD_TRANSACTIONS END ===


# === BUILD_STATS START ===
def build_stats(expense_rows):
    if not expense_rows:
        return {"total_spent": "₹0", "tx_count": 0, "top_category": "—"}

    totals = {}
    labels = {}
    first_seen = {}
    for index, row in enumerate(expense_rows):
        raw_category = row["category"]
        original_slug = (raw_category or "").strip().lower()
        if original_slug in KNOWN_CATEGORIES:
            bucketed_slug = original_slug
            category_label = original_slug.title()
        else:
            bucketed_slug = "other"
            if raw_category is None or not str(raw_category).strip():
                category_label = "Other"
            else:
                category_label = raw_category

        if bucketed_slug not in totals:
            totals[bucketed_slug] = 0
            labels[bucketed_slug] = category_label
            first_seen[bucketed_slug] = index
        totals[bucketed_slug] += row["amount"] or 0

    top_bucket = min(
        totals.keys(),
        key=lambda slug: (-totals[slug], first_seen[slug]),
    )

    return {
        "total_spent": format_amount(sum(row["amount"] for row in expense_rows)),
        "tx_count": len(expense_rows),
        "top_category": labels[top_bucket],
    }
# === BUILD_STATS END ===


# === BUILD_BREAKDOWN START ===
def build_breakdown(expense_rows):
    totals = {}
    labels = {}
    first_seen = {}

    for index, row in enumerate(expense_rows):
        raw_category = row["category"]
        original_slug = (raw_category or "").strip().lower()
        if original_slug in KNOWN_CATEGORIES:
            bucketed_slug = original_slug
            category_label = original_slug.title()
        else:
            bucketed_slug = "other"
            if raw_category is None or not str(raw_category).strip():
                category_label = "Other"
            else:
                category_label = raw_category

        if bucketed_slug not in totals:
            totals[bucketed_slug] = 0
            labels[bucketed_slug] = category_label
            first_seen[bucketed_slug] = index

        totals[bucketed_slug] += row["amount"] or 0

    if not totals:
        return []

    sorted_slugs = sorted(
        totals.keys(),
        key=lambda slug: (-totals[slug], first_seen[slug]),
    )

    max_total = max(totals.values())

    breakdown = []
    for position, slug in enumerate(sorted_slugs):
        category_total = totals[slug]
        if max_total > 0:
            percent = round(category_total / max_total * 100)
            percent = max(0, min(100, percent))
        else:
            percent = 0

        breakdown.append({
            "category_label": labels[slug],
            "amount":         format_amount(category_total),
            "icon":           CATEGORY_ICONS[slug],
            "percent":        percent,
            "bar_class":      BAR_CLASSES[position % len(BAR_CLASSES)],
        })

    return breakdown
# === BUILD_BREAKDOWN END ===
