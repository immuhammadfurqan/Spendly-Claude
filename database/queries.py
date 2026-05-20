"""Helpers that turn raw expense / user rows into the context the
profile.html template renders. Pure functions — no Flask, no I/O."""

from datetime import datetime, timedelta


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

# Ordered (slug, label) pairs for rendering the add-expense category select.
# Derived from CATEGORY_ICONS so the option list stays in lockstep with the
# canonical category set — no second source to drift out of sync.
CATEGORY_OPTIONS = [(slug, slug.title()) for slug in CATEGORY_ICONS]

DATE_PRESETS = (
    ("all",   "All time"),
    ("month", "This month"),
    ("30d",   "Last 30 days"),
    ("year",  "This year"),
)
_PRESET_LABELS = dict(DATE_PRESETS)


def _parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _display(d):
    return d.strftime("%b %d, %Y") if d else ""


def resolve_date_range(args, today):
    """Resolve query-string filter params into an inclusive date window.

    Bounds are inclusive: date >= start AND date <= end.
    Returns dict with start/end as 'YYYY-MM-DD' strings (or None),
    preset key, range_label, start/end_display, is_active flag, and an
    optional error message for the template.
    """
    start_raw = (args.get("start") or "").strip()
    end_raw   = (args.get("end") or "").strip()
    preset_raw = (args.get("preset") or "").strip()

    inactive = {
        "start": None, "end": None, "preset": None,
        "range_label": "all time",
        "start_display": "", "end_display": "",
        "is_active": False, "error": None,
    }

    # Explicit start/end wins over preset
    if start_raw or end_raw:
        start_date = end_date = None
        try:
            if start_raw:
                start_date = _parse_iso(start_raw)
            if end_raw:
                end_date = _parse_iso(end_raw)
        except ValueError:
            return {
                **inactive,
                "error": "Invalid date — showing all transactions.",
            }

        if start_date and end_date and start_date > end_date:
            return {
                **inactive,
                "error": "Start date must be on or before end date.",
            }

        start_display = _display(start_date)
        end_display   = _display(end_date)
        if start_date and end_date:
            range_label = f"{start_display} – {end_display}"
        elif start_date:
            range_label = f"from {start_display}"
        else:
            range_label = f"up to {end_display}"

        return {
            "start": start_date.isoformat() if start_date else None,
            "end":   end_date.isoformat()   if end_date   else None,
            "preset": None,
            "range_label": range_label,
            "start_display": start_display,
            "end_display":   end_display,
            "is_active": True,
            "error": None,
        }

    if preset_raw == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif preset_raw == "30d":
        start_date = today - timedelta(days=29)
        end_date = today
    elif preset_raw == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    else:
        # 'all', empty, or unknown — no filter
        return {**inactive, "preset": preset_raw if preset_raw == "all" else None}

    return {
        "start": start_date.isoformat(),
        "end":   end_date.isoformat(),
        "preset": preset_raw,
        "range_label": _PRESET_LABELS[preset_raw],
        "start_display": _display(start_date),
        "end_display":   _display(end_date),
        "is_active": True,
        "error": None,
    }


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
