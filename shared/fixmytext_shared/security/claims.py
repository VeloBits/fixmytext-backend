"""Typed JWT payload schema. B2C-now, B2B-ready (optional org_id)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ClaimSchema:
    """Strongly-typed view of a JWT payload.

    Tokens issued by the legacy HS256 path carry only ``sub``, ``exp``,
    ``iat``, ``type``. Tokens issued by Keycloak (once the auth cutover
    lands) carry ``email``, ``email_verified``, ``roles``, plus standard
    OIDC claims (``iss``, ``aud``). ``org_id`` is the B2B-ready hook —
    None today.
    """

    sub: str
    exp: int
    iat: int
    type: str = "access"
    email: str | None = None
    email_verified: bool = False
    roles: list[str] = field(default_factory=list)
    org_id: str | None = None
    iss: str | None = None
    aud: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ClaimSchema":
        """Build a ClaimSchema from a raw JWT payload dict.

        Unknown extra keys are ignored; missing optional fields use defaults.
        """
        roles = payload.get("roles") or payload.get("realm_access", {}).get("roles", [])
        if not isinstance(roles, list):
            roles = []
        aud = payload.get("aud")
        if isinstance(aud, list):
            aud = aud[0] if aud else None
        return cls(
            sub=str(payload.get("sub", "")),
            exp=int(payload.get("exp", 0)),
            iat=int(payload.get("iat", 0)),
            type=str(payload.get("type", "access")),
            email=payload.get("email"),
            email_verified=bool(payload.get("email_verified", False)),
            roles=list(roles),
            org_id=payload.get("org_id"),
            iss=payload.get("iss"),
            aud=aud,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a dict view (for code paths that still expect raw payload)."""
        return {
            "sub": self.sub,
            "exp": self.exp,
            "iat": self.iat,
            "type": self.type,
            "email": self.email,
            "email_verified": self.email_verified,
            "roles": self.roles,
            "org_id": self.org_id,
            "iss": self.iss,
            "aud": self.aud,
        }
