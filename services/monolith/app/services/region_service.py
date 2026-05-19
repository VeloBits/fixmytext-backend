"""Region detection via IP geolocation."""

import ipaddress
import logging

import httpx

logger = logging.getLogger(__name__)

# Maps country codes to our pricing regions
_COUNTRY_TO_REGION = {
    "IN": "IN",
    "US": "US",
    "CA": "US",
    "AU": "US",
    "GB": "GB",
    # EU countries
    "DE": "EU",
    "FR": "EU",
    "IT": "EU",
    "ES": "EU",
    "NL": "EU",
    "BE": "EU",
    "AT": "EU",
    "PT": "EU",
    "IE": "EU",
    "FI": "EU",
    "GR": "EU",
    "SE": "EU",
    "DK": "EU",
    "PL": "EU",
    "CZ": "EU",
    "RO": "EU",
    "HU": "EU",
    "SK": "EU",
    "HR": "EU",
    "BG": "EU",
    "LT": "EU",
    "LV": "EU",
    "EE": "EU",
    "SI": "EU",
    "LU": "EU",
    "MT": "EU",
    "CY": "EU",
}

DEFAULT_REGION = "US"


def _is_local_ip(ip_address: str) -> bool:
    """Check if IP is local/private (includes Docker 172.16.x range)."""
    if not ip_address or ip_address in {"localhost", "0.0.0.0"}:  # noqa: S104
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        return ip_obj.is_private or ip_obj.is_loopback
    except ValueError:
        return True


async def detect_region(ip_address: str) -> str:
    """Detect pricing region from IP address. Returns region code (IN, US, GB, EU).
    For local/private IPs, detects the server's public IP automatically."""
    is_local = _is_local_ip(ip_address)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if is_local:
                # Local dev — detect region from server's public IP
                resp = await client.get("http://ip-api.com/json/?fields=countryCode")
            else:
                resp = await client.get(
                    f"http://ip-api.com/json/{ip_address}?fields=countryCode"
                )

            if resp.status_code == 200:
                country = resp.json().get("countryCode", "")
                return _COUNTRY_TO_REGION.get(country, DEFAULT_REGION)
    except Exception:
        logger.warning("Region detection failed for %s", ip_address, exc_info=True)

    return DEFAULT_REGION


async def resolve_user_region(
    user,
    request,
    db,
    explicit_region: str = "",
) -> str:
    """Resolve region: explicit param > user.region > IP detection.
    Updates user.region if changed (but does NOT commit — caller controls transaction).
    """
    from app.core.pass_catalog import REGIONS

    if explicit_region and explicit_region in REGIONS:
        region = explicit_region
    elif user and user.region:
        region = user.region
    elif request:
        ip = request.client.host if request.client else ""
        region = await detect_region(ip)
    else:
        region = DEFAULT_REGION

    if region not in REGIONS:
        region = DEFAULT_REGION

    if user and user.region != region:
        user.region = region

    return region
