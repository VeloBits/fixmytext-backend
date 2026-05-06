"""Keyed digest for *high-entropy random tokens* — explicitly NOT for passwords.

This module exists separately from ``app.core.security`` (which handles
passwords via bcrypt) and from ``app.services.auth_service`` (which holds
password-handling business logic) so that the algorithm choice is unambiguous
to readers and to static analysis:

* Inputs are server-generated 256-bit random strings produced by
  ``secrets.token_urlsafe(32)`` — password-reset tokens and email-verification
  tokens. They are *not* user-chosen secrets.
* For high-entropy randoms, a fast keyed digest (HMAC-SHA256) is the right
  primitive. bcrypt/argon2/scrypt would be wasteful — those defend against
  brute-force on low-entropy human passwords, which is not the threat model
  here.
* The HMAC key is ``settings.SECRET_KEY``, so a leaked database alone (without
  the secret) cannot be used to look up token values offline. This is the
  defense-in-depth bcrypt-for-passwords gives you in the password world.
"""

import hmac

from app.core.config import settings


def hash_token(raw_token: str) -> str:
    """Return the keyed HMAC-SHA256 digest of ``raw_token`` (hex).

    See module docstring for why HMAC-SHA256 is the right primitive here.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(), raw_token.encode(), digestmod="sha256"
    ).hexdigest()
