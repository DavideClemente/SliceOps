import uuid
from datetime import datetime

from pydantic import BaseModel

Plan = str


class ApiKeyData(BaseModel):
    key: str
    owner: str
    plan: str
    active: bool
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    github_username: str
    email: str | None
    plan: str
    created_at: datetime


class ApiKeyResponse(BaseModel):
    key: str
    active: bool
    created_at: datetime
