from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Request, status
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    PasswordChangeRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    """
    Register a new user account without requiring email or phone.
    Requires Full Name, Unique Username, Password, and Confirm Password.
    Password hashed with Argon2id.
    """
    token_resp, _ = await AuthService.register_user(req)
    return token_resp


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate user with Username and Password.
    Returns signed JWT access token (15m) and secure refresh token (30d).
    """
    user_agent = request.headers.get("user-agent")
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    return await AuthService.login_user(req, user_agent=user_agent, ip_address=client_ip)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshTokenRequest, request: Request):
    """
    Rotate refresh token and issue a fresh access token.
    Detects revoked token reuse and invalidates compromised token families.
    """
    user_agent = request.headers.get("user-agent")
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    return await AuthService.refresh_token(req.refresh_token, user_agent=user_agent, ip_address=client_ip)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    req: Optional[RefreshTokenRequest] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Log out user, invalidate active session/refresh token, and update presence to offline.
    """
    token_val = req.refresh_token if req else None
    await AuthService.logout_user(current_user["id"], token_val)
    return {"message": "Logged out successfully."}


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    req: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Change user password with Argon2id rehashing and invalidate all existing refresh sessions.
    """
    await AuthService.change_password(current_user["id"], req)
    return {"message": "Password changed successfully. Please log in again with your new password."}
