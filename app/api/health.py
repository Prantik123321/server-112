from fastapi import APIRouter
from app.config.settings import settings
from app.database.supabase import check_supabase_health
from app.database.mongodb import check_mongodb_health

router = APIRouter(prefix="/health", tags=["System Health"])


@router.get("")
async def health_check():
    """
    Health check endpoint reporting application status and database connectivity
    for Supabase PostgreSQL and MongoDB Atlas.
    """
    supabase_status = await check_supabase_health()
    mongo_status = await check_mongodb_health()

    overall = "healthy"
    statuses = {supabase_status.get("status"), mongo_status.get("status")}
    if "unhealthy" in statuses or "disconnected" in statuses:
        overall = "degraded"
    elif "unconfigured" in statuses:
        overall = "pending_configuration"

    return {
        "status": overall,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "databases": {
            "supabase_postgresql": supabase_status,
            "mongodb_atlas": mongo_status
        }
    }
