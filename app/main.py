import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config.settings import settings
from app.database.supabase import init_supabase_db, ensure_supabase_db, close_supabase_db
from app.database.mongodb import init_mongodb, ensure_mongodb, close_mongodb
from app.middleware.cors import setup_cors
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.api.router import api_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nodeshare.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Initializing NodeShare backend services...")
    # Initialize database connections
    await init_supabase_db()
    await init_mongodb()
    yield
    logger.info("Shutting down NodeShare backend services...")
    await close_supabase_db()
    await close_mongodb()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Cross-platform private messaging and file-sharing backend for Windows and Android.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# 1. CORS Middleware
setup_cors(app)

# 2. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 3. Sliding Window Rate Limiting Middleware
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def ensure_databases_middleware(request: Request, call_next):
    """Ensure DB pools are initialized on serverless cold starts where lifespan may be skipped or retried."""
    if settings.ENVIRONMENT != "testing" and request.url.path.startswith("/api"):
        await ensure_supabase_db()
        await ensure_mongodb()
    return await call_next(request)


# Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format Pydantic validation errors cleanly."""
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        errors.append({
            "field": field,
            "message": err.get("msg"),
            "type": err.get("type")
        })
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "message": "Invalid request parameters.",
            "details": errors
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions without leaking sensitive tracebacks to clients."""
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Our engineers have been alerted."
        }
    )


# Include main API router
app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root():
    """Welcome endpoint providing service overview and documentation links."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "documentation": "/docs",
        "health_check": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
