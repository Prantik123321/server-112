from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings


def setup_cors(app: FastAPI) -> None:
    """Configure strict CORS policy for NodeShare API."""
    origins = settings.cors_origins_list

    # Ensure wildcard is not used with allow_credentials=True
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins else ["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Idempotency-Key"],
        expose_headers=["Content-Disposition", "Retry-After"],
        max_age=3600,
    )
