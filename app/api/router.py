from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.friends import router as friends_router
from app.api.conversations import router as conversations_router
from app.api.messages import router as messages_router
from app.api.groups import router as groups_router
from app.api.files import router as files_router
from app.api.notifications import router as notifications_router
from app.api.health import router as health_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(friends_router)
api_router.include_router(conversations_router)
api_router.include_router(messages_router)
api_router.include_router(groups_router)
api_router.include_router(files_router)
api_router.include_router(notifications_router)
