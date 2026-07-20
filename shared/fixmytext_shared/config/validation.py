"""Startup configuration validation shared across services.

Called from each service's lifespan so a missing security-critical setting
fails the process fast instead of silently degrading a guard to fail-open
(e.g. JWT audience/issuer verification, the session-cookie secret, or the
internal entitlement secret). Dev/test environments are exempt so local runs
stay frictionless.
"""

_DEV_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "ci"})


def is_production_like(environment: str) -> bool:
    """True for any non-dev/test environment (production, staging, preview…)."""
    return (environment or "").strip().lower() not in _DEV_ENVIRONMENTS


def assert_required_in_prod(environment: str, **required: object) -> None:
    """Raise ``RuntimeError`` if any required setting is empty in a non-dev env.

    ``required`` is ``name=value`` pairs; a value is "missing" when falsy
    (empty string, None, 0). No-op in dev/test so local startup is unaffected.
    """
    if not is_production_like(environment):
        return
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise RuntimeError(
            "Refusing to start: missing required production configuration: "
            + ", ".join(missing)
        )
