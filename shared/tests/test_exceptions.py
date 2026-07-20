"""Tests for shared domain exceptions."""

import pytest

from fixmytext_shared.exceptions import AuthError, ConfigError, RateLimitError


@pytest.mark.parametrize("exc_class", [AuthError, ConfigError, RateLimitError])
def test_is_exception_subclass(exc_class):
    assert issubclass(exc_class, Exception)


@pytest.mark.parametrize("exc_class", [AuthError, ConfigError, RateLimitError])
def test_raisable_with_message(exc_class):
    with pytest.raises(exc_class, match="boom"):
        raise exc_class("boom")
