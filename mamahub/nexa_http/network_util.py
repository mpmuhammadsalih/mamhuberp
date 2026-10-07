"""Small helpers for displaying reachable LAN addresses on startup."""
from __future__ import annotations

import os
import socket


def resolve_lan_ip() -> str:
    """
    Best-effort LAN IPv4 for console URLs.

    Order: ``NEXA_LOCAL_IP`` / ``APP_LOCAL_IP`` env → UDP route trick → hostname lookup → 127.0.0.1.
    """
    override = (os.getenv('NEXA_LOCAL_IP') or os.getenv('APP_LOCAL_IP') or '').strip()
    if override:
        return override

    # Standard trick: pick the interface used to reach the internet (no packets sent).
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            ip = (s.getsockname()[0] or '').strip()
            if ip and not ip.startswith('127.'):
                return ip
    except OSError:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith('127.'):
            return ip
    except OSError:
        pass

    return '127.0.0.1'
