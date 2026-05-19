"""Tests for app/core/config.py — settings parsing and property helpers."""

from app.core.config import Settings


class TestAllowedOriginsList:
    """Test the allowed_origins_list property that parses ALLOWED_ORIGINS."""

    def test_comma_separated_string(self):
        """Comma-separated origins are split into a list."""
        s = Settings(
            SECRET_KEY="x" * 64,
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            ALLOWED_ORIGINS="http://a.com,http://b.com",
        )
        result = s.allowed_origins_list
        assert result == ["http://a.com", "http://b.com"]

    def test_json_array_string(self):
        """JSON array of origins is parsed correctly."""
        s = Settings(
            SECRET_KEY="x" * 64,
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            ALLOWED_ORIGINS='["http://a.com", "http://b.com"]',
        )
        result = s.allowed_origins_list
        assert result == ["http://a.com", "http://b.com"]

    def test_single_origin(self):
        """Single origin string is returned as single-element list."""
        s = Settings(
            SECRET_KEY="x" * 64,
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            ALLOWED_ORIGINS="http://localhost:3000",
        )
        result = s.allowed_origins_list
        assert result == ["http://localhost:3000"]

    def test_empty_string_returns_empty_list(self):
        """Empty string produces empty list."""
        s = Settings(
            SECRET_KEY="x" * 64,
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            ALLOWED_ORIGINS="",
        )
        result = s.allowed_origins_list
        assert result == []

    def test_strips_whitespace(self):
        """Extra whitespace around origins is stripped."""
        s = Settings(
            SECRET_KEY="x" * 64,
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            ALLOWED_ORIGINS="  http://a.com ,  http://b.com  ",
        )
        result = s.allowed_origins_list
        assert result == ["http://a.com", "http://b.com"]
