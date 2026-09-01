"""CORS allowlist and per-IP rate limiting for the public API.

Both are resolved from environment variables so the same app factory serves
sane defaults locally and a locked-down profile in production without a code
change between the two.
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# The web frontend calls the API same-origin (apps/web/lib/api.ts: /api in
# prod via the Vercel rewrite, localhost:8000 in dev) -- nothing legitimate
# needs a wildcard, which only offered the API as a free cross-origin
# backend to anyone. www redirects 308 to the apex (see docs/seo-audit), but
# is kept in the allowlist for any page load that reaches JS before that
# redirect completes.
DEFAULT_CORS_ORIGINS = (
    "https://esp-atlas.com",
    "https://www.esp-atlas.com",
    "http://localhost:3000",
)

# Vercel's edge network sets this header to the real client IP on every
# request it proxies to the serverless function, and it cannot be forged by
# the caller -- Vercel overwrites it before the function ever sees the
# request. Set ESP_ATLAS_TRUSTED_FORWARDED_HEADER="" to fall back to the
# ASGI-reported remote address (e.g. a bare uvicorn with no proxy in front).
DEFAULT_TRUSTED_FORWARDED_HEADER = "x-forwarded-for"

# Generous: keeps the open read API usable under a normal browsing burst.
DEFAULT_RATE_LIMIT_READ = "120/minute"
# Strict: /intent /build /clarify /wizard -- Groq-backed, real cost per call.
DEFAULT_RATE_LIMIT_LLM = "10/minute"
# Strict: /flash-bin -- bandwidth (streams firmware images) and an
# SSRF-shaped proxy, even though the target is re-checked against an
# allowlist server-side.
DEFAULT_RATE_LIMIT_FLASH = "60/minute"


def resolve_cors_origins():
    raw = os.environ.get("ESP_ATLAS_CORS_ORIGINS")
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def resolve_rate_limits():
    return {
        "read": os.environ.get("ESP_ATLAS_RATE_LIMIT_READ", DEFAULT_RATE_LIMIT_READ),
        "llm": os.environ.get("ESP_ATLAS_RATE_LIMIT_LLM", DEFAULT_RATE_LIMIT_LLM),
        "flash": os.environ.get("ESP_ATLAS_RATE_LIMIT_FLASH", DEFAULT_RATE_LIMIT_FLASH),
    }


def client_ip(request: Request) -> str:
    """The rate-limit key: the first hop of a trusted forwarded header if
    the deploy sets one, else the ASGI-reported remote address."""
    header_name = os.environ.get(
        "ESP_ATLAS_TRUSTED_FORWARDED_HEADER", DEFAULT_TRUSTED_FORWARDED_HEADER
    ).strip()
    if header_name:
        value = request.headers.get(header_name)
        if value:
            return value.split(",")[0].strip()
    return get_remote_address(request)


def build_limiter(rate_limits=None):
    """A Limiter whose *default* (unrouted) limit is the generous read
    limit -- every endpoint gets it for free via SlowAPIMiddleware unless
    explicitly decorated tighter or exempted."""
    limits = rate_limits if rate_limits is not None else resolve_rate_limits()
    return Limiter(key_func=client_ip, default_limits=[limits["read"]])
