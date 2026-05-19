"""Tests for ``app.services.email`` — backend selection, senders, and templates.

Email flows (send_verification_email, send_password_reset_email) are now handled
by Keycloak and have been removed from the monolith.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email import get_email_sender
from app.services.email.console_backend import ConsoleEmailSender
from app.services.email.sender import EmailMessage
from app.services.email.smtp_backend import SmtpEmailSender
from app.services.email.templates import password_reset_email, verification_email

# ── get_email_sender selection ────────────────────────────────────────────────


def _reset_sender_cache():
    get_email_sender.cache_clear()


def test_backend_selection_console_explicit():
    _reset_sender_cache()
    with patch("app.services.email.settings") as s:
        s.EMAIL_BACKEND = "console"
        s.SMTP_HOST = "smtp.example.com"  # ignored when backend is forced
        assert isinstance(get_email_sender(), ConsoleEmailSender)
    _reset_sender_cache()


def test_backend_selection_smtp_explicit():
    _reset_sender_cache()
    with patch("app.services.email.settings") as s:
        s.EMAIL_BACKEND = "smtp"
        s.SMTP_HOST = ""
        assert isinstance(get_email_sender(), SmtpEmailSender)
    _reset_sender_cache()


def test_backend_selection_auto_prefers_smtp_when_host_set():
    _reset_sender_cache()
    with patch("app.services.email.settings") as s:
        s.EMAIL_BACKEND = "auto"
        s.SMTP_HOST = "sandbox.smtp.mailtrap.io"
        assert isinstance(get_email_sender(), SmtpEmailSender)
    _reset_sender_cache()


def test_backend_selection_auto_falls_back_to_console():
    _reset_sender_cache()
    with patch("app.services.email.settings") as s:
        s.EMAIL_BACKEND = "auto"
        s.SMTP_HOST = ""
        assert isinstance(get_email_sender(), ConsoleEmailSender)
    _reset_sender_cache()


# ── ConsoleEmailSender ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_console_backend_logs_and_does_not_raise(caplog):
    sender = ConsoleEmailSender()
    msg = EmailMessage(
        to="user@example.com",
        subject="Verify your email",
        html="<p>...</p>",
        text="Click https://app.example.com/verify?token=abc to verify.",
    )
    with caplog.at_level(logging.INFO, logger="app.services.email.console_backend"):
        await sender.send(msg)
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "user@example.com" in joined
    assert "https://app.example.com/verify?token=abc" in joined


# ── SmtpEmailSender ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smtp_backend_sends_via_aiosmtplib():
    sender = SmtpEmailSender()
    msg = EmailMessage(
        to="user@example.com",
        subject="S",
        html="<p>hi</p>",
        text="hi",
    )
    with patch(
        "app.services.email.smtp_backend.aiosmtplib.send", new_callable=AsyncMock
    ) as mock_send:
        await sender.send(msg)
    assert mock_send.await_count == 1
    # First positional arg is the MIME message; kwargs carry the SMTP config.
    args, kwargs = mock_send.call_args
    mime = args[0]
    assert mime["To"] == "user@example.com"
    assert mime["Subject"] == "S"
    assert "hostname" in kwargs
    assert "port" in kwargs


@pytest.mark.asyncio
async def test_smtp_backend_swallows_and_logs_failure(caplog):
    sender = SmtpEmailSender()
    msg = EmailMessage(to="x@y.z", subject="s", html="<p>h</p>", text="h")
    with (
        patch(
            "app.services.email.smtp_backend.aiosmtplib.send",
            new_callable=AsyncMock,
            side_effect=ConnectionError("relay down"),
        ),
        caplog.at_level(logging.ERROR, logger="app.services.email.smtp_backend"),
    ):
        await sender.send(msg)  # must not raise
    assert any("SMTP send failed" in r.getMessage() for r in caplog.records)


# ── Templates ─────────────────────────────────────────────────────────────────


def test_templates_escape_display_name_in_html():
    subject, html_body, text_body = verification_email(
        display_name="<script>alert(1)</script>",
        verify_url="https://app.example.com/verify-email?token=abc",
    )
    assert "Verify" in subject
    # HTML variant must escape the injected tag.
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
    # Plaintext retains the raw string (no interpreter context).
    assert "<script>" in text_body


def test_verification_template_embeds_url():
    _, html_body, text_body = verification_email(
        "Alice", "https://app.example.com/verify-email?token=t1"
    )
    assert "https://app.example.com/verify-email?token=t1" in html_body
    assert "https://app.example.com/verify-email?token=t1" in text_body


def test_password_reset_template_embeds_url():
    _, html_body, text_body = password_reset_email(
        "Bob", "https://app.example.com/reset-password?token=r1"
    )
    assert "https://app.example.com/reset-password?token=r1" in html_body
    assert "https://app.example.com/reset-password?token=r1" in text_body
