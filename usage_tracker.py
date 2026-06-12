"""
PVMath Usage Tracker
--------------------
Tracks free-tier analysis attempts per user per app.
Limit: 4 free analyses per app (SiteIQ and TopoIQ counted separately).

NOTE: Uses a local JSON file — works for MVP / local hosting.
For Streamlit Cloud production, replace _load/_save with Supabase or
a simple GitHub Gist API call so data persists across app restarts.
"""

import json
import os

# ── Config ────────────────────────────────────────────────────────────────────
FREE_LIMIT   = 4
STRIPE_LINK  = "https://buy.stripe.com/YOUR_LINK_HERE"   # ← replace after Stripe setup
PRICE_LABEL  = "€99 / month"
USAGE_FILE   = os.path.join(os.path.dirname(__file__), "usage_data.json")


# ── Internal helpers ──────────────────────────────────────────────────────────
def _load() -> dict:
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    try:
        with open(USAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass   # fail silently — never crash the app over usage tracking


# ── Public API ────────────────────────────────────────────────────────────────
def get_usage(username: str, app: str) -> int:
    """Return how many analyses this user has run in this app."""
    data = _load()
    return data.get(username, {}).get(app, 0)


def increment_usage(username: str, app: str) -> int:
    """Increment counter and return new total."""
    data = _load()
    user = data.setdefault(username, {})
    user[app] = user.get(app, 0) + 1
    _save(data)
    return user[app]


def is_over_limit(username: str, app: str) -> bool:
    return get_usage(username, app) >= FREE_LIMIT


def remaining(username: str, app: str) -> int:
    return max(0, FREE_LIMIT - get_usage(username, app))
