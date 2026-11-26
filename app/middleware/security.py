from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.config.settings import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds essential cybersecurity response headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # CSP restricted for API backend
        headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none';"
        
        if settings.ENVIRONMENT == "production":
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response
