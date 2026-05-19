"""Transactional email templates.

Stored as Python strings with ``str.format()`` — avoids pulling in Jinja2
for three emails. User-controlled values (``display_name``) run through
``html.escape()`` before interpolation into the HTML variant; the text
variant is plaintext so escaping there is unnecessary.
"""

import html

_HTML_SHELL = """\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f6f8fa;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
      <tr>
        <td style="padding:24px 28px;border-bottom:1px solid #eef0f3;">
          <strong style="font-size:18px;color:#1a1a1a;">FixMyText</strong>
        </td>
      </tr>
      <tr>
        <td style="padding:28px;">
          <h1 style="font-size:20px;margin:0 0 12px;color:#111;">{heading}</h1>
          <p style="font-size:15px;line-height:1.55;margin:0 0 20px;color:#3a3a3a;">{intro}</p>
          <p style="margin:0 0 24px;">
            <a href="{url}" style="display:inline-block;padding:10px 18px;background:#007acc;color:#ffffff;text-decoration:none;font-weight:600;border-radius:4px;">{cta}</a>
          </p>
          <p style="font-size:13px;line-height:1.5;margin:0 0 8px;color:#6b6b6b;">
            Or copy this link into your browser:
          </p>
          <p style="font-size:13px;line-height:1.5;margin:0 0 20px;word-break:break-all;">
            <a href="{url}" style="color:#007acc;">{url}</a>
          </p>
          <p style="font-size:13px;line-height:1.5;margin:0;color:#6b6b6b;">{footer}</p>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

_TEXT_SHELL = """\
{heading}

{intro}

{cta}: {url}

{footer}

— FixMyText
"""


def _render(
    *,
    heading: str,
    intro_plain: str,
    cta: str,
    url: str,
    footer: str,
) -> tuple[str, str]:
    """Return (html, text) for a shell-based message."""
    html_body = _HTML_SHELL.format(
        heading=html.escape(heading),
        intro=html.escape(intro_plain),
        cta=html.escape(cta),
        url=url,  # url is system-generated, already safe; escape would break href
        footer=html.escape(footer),
    )
    text_body = _TEXT_SHELL.format(
        heading=heading, intro=intro_plain, cta=cta, url=url, footer=footer
    )
    return html_body, text_body


def verification_email(
    display_name: str, verify_url: str, expires_hours: int = 24
) -> tuple[str, str, str]:
    """(subject, html, text) for the verify-email message."""
    name = display_name or "there"
    subject = "Verify your FixMyText email address"
    html_body, text_body = _render(
        heading=f"Hi {name}, please verify your email",
        intro_plain=(
            "Thanks for signing up for FixMyText. Confirm your email address "
            f"to unlock all tools. This link expires in {expires_hours} hours."
        ),
        cta="Verify email",
        url=verify_url,
        footer=(
            "If you didn't create a FixMyText account, you can safely ignore "
            "this message."
        ),
    )
    return subject, html_body, text_body


def password_reset_email(
    display_name: str, reset_url: str, expires_minutes: int = 15
) -> tuple[str, str, str]:
    """(subject, html, text) for the password-reset message."""
    name = display_name or "there"
    subject = "Reset your FixMyText password"
    html_body, text_body = _render(
        heading=f"Hi {name}, reset your password",
        intro_plain=(
            "We received a request to reset the password on your FixMyText "
            f"account. This link expires in {expires_minutes} minutes."
        ),
        cta="Reset password",
        url=reset_url,
        footer=(
            "If you didn't request a reset, you can ignore this email — your "
            "password won't change."
        ),
    )
    return subject, html_body, text_body
