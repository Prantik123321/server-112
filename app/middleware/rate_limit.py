import time
from typing import Dict, Tuple, List
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config.settings import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiting middleware.
    Tracks client requests by IP address with special strict limits on authentication endpoints.
    """

    def __init__(self, app):
        super().__init__(app)
        # Dictionary storing IP -> list of timestamps
        self.request_history: Dict[str, List[float]] = defaultdict(list)
        # Dedicated dictionary for login attempts
        self.login_history: Dict[str, List[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        # Check standard reverse proxy headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Client IP is the first address in comma-separated list
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def _is_rate_limited(self, store: Dict[str, List[float]], client_ip: str, max_requests: int, window_seconds: float = 60.0) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        # Periodic bound check to prevent unbounded memory growth on long-lived serverless containers
        if len(store) > 5000:
            stale_ips = [ip for ip, ts in store.items() if not ts or ts[-1] < cutoff]
            for ip in stale_ips:
                del store[ip]

        history = store[client_ip]
        # Remove timestamps older than window
        while history and history[0] < cutoff:
            history.pop(0)

        if len(history) >= max_requests:
            return True

        history.append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        # Bypass rate limiting in test environment
        if settings.ENVIRONMENT == "testing":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        path = request.url.path

        # 1. Strict limit for authentication endpoints
        if path.startswith("/api/auth/login") or path.startswith("/api/auth/register"):
            if self._is_rate_limited(self.login_history, client_ip, settings.LOGIN_RATE_LIMIT_PER_MINUTE, 60.0):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "message": "Too many authentication attempts. Please wait 60 seconds before retrying."
                    },
                    headers={"Retry-After": "60"}
                )

        # 2. General endpoint rate limit
        if self._is_rate_limited(self.request_history, client_ip, settings.RATE_LIMIT_PER_MINUTE, 60.0):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": "Rate limit exceeded. Please slow down."
                },
                headers={"Retry-After": "60"}
            )

        response = await call_next(request)
        return response
