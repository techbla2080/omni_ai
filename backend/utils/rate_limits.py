"""
#48 — Rate limiting setup.

Uses slowapi with Redis backend for distributed rate limiting that survives
backend restarts.

Key function: identifies users by JWT token hash if present, falls back
to IP address. This means a single user can't dodge limits by clearing
cookies, and an anonymous attacker on a shared IP gets one shared limit.
"""

import os
import hashlib
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    """
    Returns a stable identifier for rate limiting.
    - Authenticated requests: hash of the bearer token (per-user limits)
    - Unauthenticated: client IP (per-IP limits)
    """
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth[7:].strip()
        if token:
            # Hash the token so we don't store secrets in Redis keys
            return 'u:' + hashlib.sha256(token.encode()).hexdigest()[:16]
    return 'ip:' + get_remote_address(request)


# Redis URL from env, with docker compose default
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')


limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=REDIS_URL,
    # Global safety cap — applies to all routes unless overridden
    default_limits=["1000/hour"]
)