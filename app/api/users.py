from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, status
from app.schemas.auth import UserResponse
from app.schemas.users import UserUpdateRequest, TeacherVerifyRequest
from app.schemas.search import UserSearchResult
from app.services.user_service import UserService
from app.services.search_service import SearchService
from app.dependencies.auth import get_current_user, get_current_admin

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve profile of the authenticated user."""
    return await UserService.get_user_by_id(current_user["id"])


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    req: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update profile details (Full Name, Avatar URL, Status Message, Teacher Title)."""
    return await UserService.update_profile(current_user["id"], req)


@router.get("/search", response_model=List[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, description="Search query by username, full name (English or Bengali)"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    teachers_only: bool = Query(False, description="Filter only verified teachers"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Intelligent user search with 6-tier ranking:
    1. Exact username
    2. Exact full name
    3. Username prefix
    4. Name prefix
    5. Similar spelling (PostgreSQL pg_trgm similarity)
    6. Partial match
    Supports Bengali and English character sets.
    """
    return await SearchService.search_users(q, limit=limit, offset=offset, teachers_only=teachers_only)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve public profile of a user by UUID."""
    return await UserService.get_user_by_id(user_id)


@router.patch("/{user_id}/verify-teacher", response_model=UserResponse)
async def verify_teacher_account(
    user_id: str,
    req: TeacherVerifyRequest,
    admin_user: Dict[str, Any] = Depends(get_current_admin)
):
    """
    Verify or unverify a teacher account.
    Restricted to system administrators.
    """
    return await UserService.verify_teacher(user_id, req)
