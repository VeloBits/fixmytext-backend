"""Tests for app/core/pass_catalog.py — catalog lookups and pricing helpers."""

from app.core.pass_catalog import (
    ALWAYS_FREE_TOOL_IDS,
    CREDIT_PACKS,
    DEFAULT_REGION,
    PASSES,
    REGIONS,
    get_credit_pack,
    get_currency,
    get_pass,
    get_price,
    get_symbol,
)


class TestGetPass:
    """Test pass lookup."""

    def test_known_pass(self):
        """Known pass ID returns a dict."""
        result = get_pass("quick_fix")
        assert result is not None
        assert result["id"] == "quick_fix"

    def test_unknown_pass(self):
        """Unknown pass ID returns None."""
        assert get_pass("nonexistent") is None


class TestGetCreditPack:
    """Test credit pack lookup."""

    def test_known_pack(self):
        """Known credit pack ID returns a dict."""
        result = get_credit_pack("credits_5")
        assert result is not None
        assert result["credits"] == 5

    def test_unknown_pack(self):
        """Unknown credit pack ID returns None."""
        assert get_credit_pack("nonexistent") is None


class TestGetPrice:
    """Test regional pricing."""

    def test_pass_price_in(self):
        """Pass price in INR returns correct value."""
        price = get_price("quick_fix", "IN")
        assert price == 200

    def test_pass_price_us(self):
        """Pass price in USD returns correct value."""
        price = get_price("quick_fix", "US")
        assert price == 50

    def test_credit_pack_price(self):
        """Credit pack price returns correct value."""
        price = get_price("credits_5", "IN")
        assert price == 500

    def test_unknown_item_returns_zero(self):
        """Unknown item ID returns 0."""
        assert get_price("nonexistent", "IN") == 0

    def test_unknown_region_falls_back_to_default(self):
        """Unknown region falls back to default region price."""
        price = get_price("quick_fix", "ZZ")
        default_price = get_price("quick_fix", DEFAULT_REGION)
        assert price == default_price


class TestGetCurrency:
    """Test currency lookups."""

    def test_india(self):
        """IN region returns inr."""
        assert get_currency("IN") == "inr"

    def test_us(self):
        """US region returns usd."""
        assert get_currency("US") == "usd"

    def test_unknown_region_falls_back(self):
        """Unknown region falls back to default."""
        result = get_currency("ZZ")
        assert result == REGIONS[DEFAULT_REGION]["currency"]


class TestGetSymbol:
    """Test symbol lookups."""

    def test_india(self):
        """IN region returns rupee symbol."""
        assert get_symbol("IN") == "\u20b9"

    def test_us(self):
        """US region returns dollar symbol."""
        assert get_symbol("US") == "$"

    def test_unknown_region_falls_back(self):
        """Unknown region falls back to default."""
        result = get_symbol("ZZ")
        assert result == REGIONS[DEFAULT_REGION]["symbol"]


class TestCatalogIntegrity:
    """Test catalog data integrity."""

    def test_all_passes_have_required_keys(self):
        """Every pass has required keys."""
        for p in PASSES:
            assert "id" in p
            assert "name" in p
            assert "prices" in p
            assert "uses_per_day" in p
            assert "duration_days" in p

    def test_all_credit_packs_have_required_keys(self):
        """Every credit pack has required keys."""
        for c in CREDIT_PACKS:
            assert "id" in c
            assert "name" in c
            assert "credits" in c
            assert "prices" in c

    def test_all_regions_have_prices(self):
        """Every pass has prices for all defined regions."""
        for p in PASSES:
            for region in REGIONS:
                assert region in p["prices"], (
                    f"Pass {p['id']} missing price for {region}"
                )

    def test_always_free_tools_is_set(self):
        """ALWAYS_FREE_TOOL_IDS is a set with expected tools."""
        assert isinstance(ALWAYS_FREE_TOOL_IDS, set)
        assert "find_replace" in ALWAYS_FREE_TOOL_IDS
