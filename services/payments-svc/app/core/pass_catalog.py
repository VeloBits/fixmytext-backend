"""
Pass catalog — all pass definitions, credit packs, regional pricing, and reward tables.

Prices are stored in smallest currency unit: paise (IN), cents (US/EU), pence (GB).
"""

# ── Regional pricing multipliers and currency codes ──────────────────────────

REGIONS = {
    "IN": {"currency": "inr", "symbol": "₹", "multiplier": 1.0},
    "US": {"currency": "usd", "symbol": "$", "multiplier": 1.0},
    "GB": {"currency": "gbp", "symbol": "£", "multiplier": 1.0},
    "EU": {"currency": "eur", "symbol": "€", "multiplier": 1.0},
}

DEFAULT_REGION = "IN"

# ── Pass definitions ─────────────────────────────────────────────────────────
# Each pass: id, name, subtitle, tools_count, uses_per_day, duration_days, prices per region

PASSES = [
    # ── Micro Passes ── (Razorpay: ₹1 minimum)
    {
        "id": "quick_fix",
        "name": "Quick Fix",
        "subtitle": "3 extra uses · 1 tool · today",
        "tools": 1,
        "uses_per_day": 3,
        "duration_days": 1,
        "prices": {"IN": 200, "US": 50, "GB": 40, "EU": 50},
    },
    {
        "id": "tinkerer",
        "name": "Tinkerer",
        "subtitle": "10 uses · 1 tool · today",
        "tools": 1,
        "uses_per_day": 10,
        "duration_days": 1,
        "prices": {"IN": 500, "US": 75, "GB": 60, "EU": 75},
    },
    {
        "id": "double_dip",
        "name": "Double Dip",
        "subtitle": "10 uses · 2 tools · today",
        "tools": 2,
        "uses_per_day": 10,
        "duration_days": 1,
        "prices": {"IN": 800, "US": 99, "GB": 80, "EU": 99},
    },
    # ── Day Passes ──
    {
        "id": "day_single",
        "name": "Day Single",
        "subtitle": "20 uses · 1 tool · 1 day",
        "tools": 1,
        "uses_per_day": 20,
        "duration_days": 1,
        "prices": {"IN": 1000, "US": 149, "GB": 120, "EU": 149},
    },
    {
        "id": "day_triple",
        "name": "Day Triple",
        "subtitle": "20 uses · 3 tools · 1 day",
        "tools": 3,
        "uses_per_day": 20,
        "duration_days": 1,
        "prices": {"IN": 2500, "US": 249, "GB": 200, "EU": 249},
    },
    {
        "id": "day_five",
        "name": "Day Five",
        "subtitle": "30 uses · 5 tools · 1 day",
        "tools": 5,
        "uses_per_day": 30,
        "duration_days": 1,
        "prices": {"IN": 3500, "US": 300, "GB": 250, "EU": 300},
    },
    {
        "id": "day_ten",
        "name": "Day Ten",
        "subtitle": "40 uses · 10 tools · 1 day",
        "tools": 10,
        "uses_per_day": 40,
        "duration_days": 1,
        "prices": {"IN": 5900, "US": 500, "GB": 400, "EU": 500},
    },
    {
        "id": "day_fifteen",
        "name": "Day Fifteen",
        "subtitle": "50 uses · 15 tools · 1 day",
        "tools": 15,
        "uses_per_day": 50,
        "duration_days": 1,
        "prices": {"IN": 7900, "US": 700, "GB": 560, "EU": 700},
    },
    {
        "id": "day_all",
        "name": "Day All",
        "subtitle": "50 uses · all tools · 1 day",
        "tools": -1,
        "uses_per_day": 50,
        "duration_days": 1,
        "prices": {"IN": 9900, "US": 800, "GB": 640, "EU": 800},
    },
    # ── Multi-Day Passes ──
    {
        "id": "sprint_single",
        "name": "Sprint Single",
        "subtitle": "20 uses/day · 1 tool · 5 days",
        "tools": 1,
        "uses_per_day": 20,
        "duration_days": 5,
        "prices": {"IN": 3900, "US": 300, "GB": 250, "EU": 300},
    },
    {
        "id": "sprint_triple",
        "name": "Sprint Triple",
        "subtitle": "25 uses/day · 3 tools · 5 days",
        "tools": 3,
        "uses_per_day": 25,
        "duration_days": 5,
        "prices": {"IN": 8900, "US": 700, "GB": 560, "EU": 700},
    },
    {
        "id": "sprint_five",
        "name": "Sprint Five",
        "subtitle": "30 uses/day · 5 tools · 5 days",
        "tools": 5,
        "uses_per_day": 30,
        "duration_days": 5,
        "prices": {"IN": 12900, "US": 1000, "GB": 800, "EU": 1000},
    },
    {
        "id": "sprint_all",
        "name": "Sprint All",
        "subtitle": "50 uses/day · all tools · 5 days",
        "tools": -1,
        "uses_per_day": 50,
        "duration_days": 5,
        "prices": {"IN": 19900, "US": 1500, "GB": 1200, "EU": 1500},
    },
    {
        "id": "marathon_five",
        "name": "Marathon Five",
        "subtitle": "40 uses/day · 5 tools · 10 days",
        "tools": 5,
        "uses_per_day": 40,
        "duration_days": 10,
        "prices": {"IN": 19900, "US": 1500, "GB": 1200, "EU": 1500},
    },
    {
        "id": "marathon_all",
        "name": "Marathon All",
        "subtitle": "60 uses/day · all tools · 10 days",
        "tools": -1,
        "uses_per_day": 60,
        "duration_days": 10,
        "prices": {"IN": 34900, "US": 2500, "GB": 2000, "EU": 2500},
    },
    {
        "id": "stretch_all",
        "name": "Stretch All",
        "subtitle": "80 uses/day · all tools · 20 days",
        "tools": -1,
        "uses_per_day": 80,
        "duration_days": 20,
        "prices": {"IN": 54900, "US": 4000, "GB": 3200, "EU": 4000},
    },
    # ── Monthly Passes ──
    {
        "id": "monthly_five",
        "name": "Monthly Five",
        "subtitle": "50 uses/day · 5 tools · 30 days",
        "tools": 5,
        "uses_per_day": 50,
        "duration_days": 30,
        "prices": {"IN": 29900, "US": 2000, "GB": 1600, "EU": 2000},
    },
    {
        "id": "monthly_ten",
        "name": "Monthly Ten",
        "subtitle": "75 uses/day · 10 tools · 30 days",
        "tools": 10,
        "uses_per_day": 75,
        "duration_days": 30,
        "prices": {"IN": 49900, "US": 3500, "GB": 2800, "EU": 3500},
    },
    {
        "id": "monthly_all",
        "name": "Monthly All",
        "subtitle": "100 uses/day · all tools · 30 days",
        "tools": -1,
        "uses_per_day": 100,
        "duration_days": 30,
        "prices": {"IN": 79900, "US": 5500, "GB": 4400, "EU": 5500},
    },
    # ── Long-Term Passes ──
    {
        "id": "season_all",
        "name": "Season Pass",
        "subtitle": "150 uses/day · all tools · 90 days",
        "tools": -1,
        "uses_per_day": 150,
        "duration_days": 90,
        "prices": {"IN": 149900, "US": 9900, "GB": 7900, "EU": 9900},
    },
    {
        "id": "half_year",
        "name": "Half Year",
        "subtitle": "200 uses/day · all tools · 180 days",
        "tools": -1,
        "uses_per_day": 200,
        "duration_days": 180,
        "prices": {"IN": 249900, "US": 15000, "GB": 12000, "EU": 15000},
    },
    {
        "id": "annual",
        "name": "Annual",
        "subtitle": "200 uses/day · all tools · 365 days",
        "tools": -1,
        "uses_per_day": 200,
        "duration_days": 365,
        "prices": {"IN": 399900, "US": 20000, "GB": 16000, "EU": 20000},
    },
]

# ── Credit Packs ─────────────────────────────────────────────────────────────

CREDIT_PACKS = [
    {  # ₹1/use
        "id": "credits_5",
        "name": "Ink Drop",
        "credits": 5,
        "prices": {"IN": 500, "US": 99, "GB": 80, "EU": 99},
    },
    {  # ₹0.80/use
        "id": "credits_15",
        "name": "Ink Pot",
        "credits": 15,
        "prices": {"IN": 1200, "US": 249, "GB": 200, "EU": 249},
    },
    {  # ₹0.70/use
        "id": "credits_50",
        "name": "Ink Well",
        "credits": 50,
        "prices": {"IN": 3500, "US": 499, "GB": 400, "EU": 499},
    },
    {  # ₹0.59/use
        "id": "credits_150",
        "name": "Ink Barrel",
        "credits": 150,
        "prices": {"IN": 8900, "US": 799, "GB": 640, "EU": 799},
    },
]

# ── Streak Rewards ───────────────────────────────────────────────────────────

STREAK_REWARDS = {
    3: {"type": "credits", "amount": 3},
    7: {"type": "pass", "pass_id": "quick_fix"},
    14: {"type": "pass", "pass_id": "day_single"},
    21: {"type": "pass", "pass_id": "day_triple"},
    30: {"type": "pass", "pass_id": "day_five"},
    60: {"type": "pass", "pass_id": "day_all"},
    100: {"type": "pass", "pass_id": "sprint_all"},
}

# ── Quest Completion Rewards (weighted random) ───────────────────────────────

QUEST_REWARDS = [
    {"type": "credits", "amount": 3, "weight": 50},
    {"type": "pass", "pass_id": "quick_fix", "weight": 30},
    {"type": "credits", "amount": 5, "weight": 15},
    {"type": "pass", "pass_id": "tinkerer", "weight": 5},
]

# ── Weekly Spin Rewards (weighted random) ────────────────────────────────────

SPIN_REWARDS = [
    {"type": "credits", "amount": 1, "weight": 35},
    {"type": "credits", "amount": 3, "weight": 25},
    {"type": "pass", "pass_id": "quick_fix", "weight": 20},
    {"type": "pass", "pass_id": "tinkerer", "weight": 12},
    {"type": "pass", "pass_id": "day_single", "weight": 6},
    {"type": "pass", "pass_id": "day_all", "weight": 2},
]

# ── Referral Rewards ────────────────────────────────────────────────────────

REFERRAL_REWARDS = {
    "referrer": {"pass_id": "day_triple", "credits": 5},
    "new_user": {"credits": 10},
}

# ── Always-free tools (no usage tracking) ────────────────────────────────────

ALWAYS_FREE_TOOL_IDS = {
    "find_replace",
    "compare",
    "random_text",
    "password",
    "regex_test",
}

# ── Helper functions ─────────────────────────────────────────────────────────

_PASS_MAP = {p["id"]: p for p in PASSES}
_CREDIT_MAP = {c["id"]: c for c in CREDIT_PACKS}


def get_pass(pass_id: str) -> dict | None:
    return _PASS_MAP.get(pass_id)


def get_credit_pack(pack_id: str) -> dict | None:
    return _CREDIT_MAP.get(pack_id)


def get_price(item_id: str, region: str) -> int:
    """Return price in smallest currency unit for a pass or credit pack."""
    item = _PASS_MAP.get(item_id) or _CREDIT_MAP.get(item_id)
    if not item:
        return 0
    return item["prices"].get(region, item["prices"].get(DEFAULT_REGION, 0))


def get_currency(region: str) -> str:
    return REGIONS.get(region, REGIONS[DEFAULT_REGION])["currency"]


def get_symbol(region: str) -> str:
    return REGIONS.get(region, REGIONS[DEFAULT_REGION])["symbol"]
