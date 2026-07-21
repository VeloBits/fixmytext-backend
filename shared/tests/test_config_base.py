"""Tests for BaseSharedSettings (allowed_origins_list parsing)."""

from fixmytext_shared.config.base import BaseSharedSettings


class TestAllowedOriginsList:
    def test_parses_comma_separated_string(self):
        settings = BaseSharedSettings(ALLOWED_ORIGINS="http://a.com,http://b.com")
        assert settings.allowed_origins_list == ["http://a.com", "http://b.com"]

    def test_strips_whitespace_and_drops_empties(self):
        settings = BaseSharedSettings(ALLOWED_ORIGINS=" http://a.com , ,http://b.com ,")
        assert settings.allowed_origins_list == ["http://a.com", "http://b.com"]

    def test_parses_json_list(self):
        settings = BaseSharedSettings(
            ALLOWED_ORIGINS='["https://a.com", "https://b.com"]'
        )
        assert settings.allowed_origins_list == ["https://a.com", "https://b.com"]

    def test_json_non_list_falls_back_to_csv_parsing(self):
        settings = BaseSharedSettings(ALLOWED_ORIGINS='{"not": "a list"}')
        assert settings.allowed_origins_list == ['{"not": "a list"}']

    def test_single_origin(self):
        settings = BaseSharedSettings(ALLOWED_ORIGINS="https://app.fixmytext.com")
        assert settings.allowed_origins_list == ["https://app.fixmytext.com"]
