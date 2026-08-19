"""Client IP extraction and allow-list matching helpers."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from app.core.config import get_settings


def get_client_ip(request: Request) -> str:
    """Best-effort client IP, honoring X-Forwarded-For only when configured
    to trust it (i.e. we're behind a reverse proxy/load balancer that sets
    it itself). Otherwise it's trivially spoofable.
    """
    if get_settings().TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_ip_allowed(ip: str, allowed: list[str]) -> bool:
    """Check `ip` against an allow-list of exact IPs and/or CIDR ranges."""
    if not allowed:
        return False
    try:
        candidate = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for entry in allowed:
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if candidate in ipaddress.ip_network(entry, strict=False):
                    return True
            elif candidate == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False
