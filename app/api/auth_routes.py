import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.models import TokenResponse, UserResponse
from app.auth.oauth import GitHubOAuth
from app.db.engine import get_session_factory
from app.db.models import User

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


async def _get_or_create_user(github_id: int, github_username: str, email: str | None) -> User:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.github_id == github_id))
        user = result.scalar_one_or_none()
        if user is not None:
            user.github_username = github_username
            if email is not None:
                user.email = email
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(user)
            return user

        user = User(
            github_id=github_id,
            github_username=github_username,
            email=email,
            plan="free",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _get_user_by_id(user_id: uuid.UUID) -> User | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


def _require_jwt(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.removeprefix("Bearer ")
    payload = decode_token(token, secret=request.app.state.settings.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


@auth_router.get("/github")
async def github_redirect(request: Request):
    settings = request.app.state.settings
    oauth = GitHubOAuth(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
    )
    redirect_uri = f"{settings.base_url}/auth/callback"
    url = oauth.get_authorization_url(redirect_uri=redirect_uri)
    return {"url": url}


@auth_router.get("/callback")
async def github_callback(request: Request, code: str | None = None):
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    settings = request.app.state.settings
    oauth = GitHubOAuth(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
    )
    redirect_uri = f"{settings.base_url}/auth/callback"

    try:
        access_token = await oauth.exchange_code(code, redirect_uri=redirect_uri)
        user_info = await oauth.get_user_info(access_token)
    except Exception:
        raise HTTPException(status_code=502, detail="Authentication provider error")

    user = await _get_or_create_user(
        github_id=user_info["id"],
        github_username=user_info["login"],
        email=user_info.get("email"),
    )

    jwt_access = create_access_token(
        user_id=user.id,
        plan=user.plan,
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_access_token_minutes,
    )
    jwt_refresh = create_refresh_token(
        user_id=user.id,
        secret=settings.jwt_secret,
        expires_days=settings.jwt_refresh_token_days,
    )

    return TokenResponse(access_token=jwt_access, refresh_token=jwt_refresh)


@auth_router.post("/refresh")
async def refresh_token(request: Request, body: RefreshRequest):
    settings = request.app.state.settings
    payload = decode_token(body.refresh_token, secret=settings.jwt_secret)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await _get_user_by_id(uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    jwt_access = create_access_token(
        user_id=user.id,
        plan=user.plan,
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_access_token_minutes,
    )
    jwt_refresh = create_refresh_token(
        user_id=user.id,
        secret=settings.jwt_secret,
        expires_days=settings.jwt_refresh_token_days,
    )

    return TokenResponse(access_token=jwt_access, refresh_token=jwt_refresh)


@auth_router.get("/me")
async def me(request: Request):
    payload = _require_jwt(request)
    user = await _get_user_by_id(uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return UserResponse(
        id=user.id,
        github_username=user.github_username,
        email=user.email,
        plan=user.plan,
        created_at=user.created_at,
    )
