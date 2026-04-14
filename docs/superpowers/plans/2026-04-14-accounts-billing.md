# User Accounts, API Key Self-Service & Stripe Billing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users sign up with GitHub, self-manage a single API key, and upgrade to a paid plan via Stripe subscriptions.

**Architecture:** GitHub OAuth → JWT sessions → PostgreSQL user/key storage → Stripe Checkout & Billing Portal for plan upgrades. Redis remains for rate limiting, job state, and API key validation caching.

**Tech Stack:** SQLAlchemy async + asyncpg, Alembic, httpx-oauth, PyJWT, stripe SDK

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `app/db/engine.py` | Async SQLAlchemy engine, session factory, lifespan helpers |
| `app/db/models.py` | `User` and `ApiKey` ORM models |
| `app/auth/oauth.py` | GitHub OAuth flow (redirect URL, callback token exchange) |
| `app/auth/jwt.py` | JWT creation, validation, refresh token logic |
| `app/api/auth_routes.py` | `/auth/*` endpoints (GitHub OAuth, refresh, me) |
| `app/api/account_routes.py` | `/account/*` endpoints (key CRUD, billing) |
| `app/api/webhook_routes.py` | `/webhooks/stripe` endpoint |
| `app/billing/service.py` | Stripe checkout session, portal session, webhook event handling |
| `alembic.ini` | Alembic configuration |
| `alembic/env.py` | Alembic migration environment |
| `alembic/versions/001_create_users_and_api_keys.py` | Initial migration |
| `tests/test_jwt.py` | JWT unit tests |
| `tests/test_oauth.py` | OAuth flow tests (mocked GitHub) |
| `tests/test_account_routes.py` | Account endpoint tests |
| `tests/test_billing.py` | Stripe billing tests |
| `tests/test_webhook.py` | Stripe webhook tests |

### Modified Files

| File | Changes |
|---|---|
| `pyproject.toml` | Add new dependencies |
| `app/config.py` | Add database, GitHub, Stripe, JWT settings |
| `app/main.py` | Register new routers, add Postgres lifecycle |
| `app/auth/dependencies.py` | Rewrite key validation: Postgres lookup + Redis cache |
| `app/auth/models.py` | Add JWT/user Pydantic response models |
| `docker-compose.yml` | Add postgres service |
| `tests/conftest.py` | Add DB fixtures, mock JWT helpers |

---

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml:6-18`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

In `pyproject.toml`, add the new packages to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "celery[redis]>=5.4.0",
    "redis>=5.0.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "httpx>=0.27.0",
    "python-multipart>=0.0.9",
    "prometheus-fastapi-instrumentator>=7.0.0",
    "typer>=0.12.0",
    "pyyaml>=6.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "httpx-oauth>=0.15.0",
    "PyJWT>=2.9.0",
    "stripe>=11.0.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: All packages install successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add SQLAlchemy, Alembic, httpx-oauth, PyJWT, stripe dependencies"
```

---

### Task 2: Settings — Add New Config Fields

**Files:**
- Modify: `app/config.py:32-65`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_new.py`:

```python
import os
import pytest
from app.config import Settings


class TestNewSettings:
    def test_database_url_default(self):
        s = Settings()
        assert s.database_url == "postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops"

    def test_github_oauth_fields_exist(self):
        s = Settings()
        assert hasattr(s, "github_client_id")
        assert hasattr(s, "github_client_secret")

    def test_stripe_fields_exist(self):
        s = Settings()
        assert hasattr(s, "stripe_secret_key")
        assert hasattr(s, "stripe_webhook_secret")
        assert hasattr(s, "stripe_pro_price_id")

    def test_jwt_fields_exist(self):
        s = Settings()
        assert hasattr(s, "jwt_secret")
        assert s.jwt_access_token_minutes == 30
        assert s.jwt_refresh_token_days == 30

    def test_base_url_default(self):
        s = Settings()
        assert s.base_url == "http://localhost:8000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_new.py -v`
Expected: FAIL — `database_url` attribute not found

- [ ] **Step 3: Add new settings to config.py**

Add to the `Settings` class in `app/config.py`, after the existing `plans_file` field (line 55):

```python
    # Database
    database_url: str = "postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 30

    # Base URL (for OAuth callback)
    base_url: str = "http://localhost:8000"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_new.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config_new.py
git commit -m "feat: add database, GitHub OAuth, Stripe, and JWT settings"
```

---

### Task 3: Database Engine & ORM Models

**Files:**
- Create: `app/db/__init__.py`
- Create: `app/db/engine.py`
- Create: `app/db/models.py`

- [ ] **Step 1: Create app/db/__init__.py**

Empty file:

```python
```

- [ ] **Step 2: Create app/db/engine.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

_engine = None
_session_factory = None


def get_engine(settings: Settings | None = None):
    global _engine
    if _engine is None:
        if settings is None:
            settings = Settings()
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def close_engine():
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
```

- [ ] **Step 3: Create app/db/models.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    github_username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, server_default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    api_key: Mapped["ApiKey | None"] = relationship(back_populates="user", uselist=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="api_key")
```

- [ ] **Step 4: Verify models import cleanly**

Run: `uv run python -c "from app.db.models import Base, User, ApiKey; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/db/
git commit -m "feat: add SQLAlchemy async engine and User/ApiKey ORM models"
```

---

### Task 4: Alembic Setup & Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (directory)

- [ ] **Step 1: Initialize Alembic**

Run: `cd /Users/davide.clemente/Documents/GitHub/SliceOps && uv run alembic init alembic`

- [ ] **Step 2: Edit alembic.ini — set sqlalchemy.url**

In `alembic.ini`, find the line `sqlalchemy.url = driver://user:pass@localhost/dbname` and replace with:

```ini
sqlalchemy.url = postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops
```

- [ ] **Step 3: Edit alembic/env.py for async support**

Replace the entire content of `alembic/env.py` with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate initial migration**

Run: `uv run alembic revision --autogenerate -m "create users and api_keys tables"`
Expected: A migration file is created in `alembic/versions/`

- [ ] **Step 5: Review the generated migration**

Read the generated file and verify it contains:
- `create_table('users', ...)` with all columns (id, github_id, github_username, email, plan, stripe_customer_id, stripe_subscription_id, created_at, updated_at)
- `create_table('api_keys', ...)` with all columns (id, user_id, key, active, created_at)
- Unique constraints on `users.github_id`, `api_keys.user_id`, `api_keys.key`
- Foreign key from `api_keys.user_id` to `users.id`

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: add Alembic setup with initial users/api_keys migration"
```

---

### Task 5: JWT Module

**Files:**
- Create: `app/auth/jwt.py`
- Create: `tests/test_jwt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jwt.py`:

```python
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.auth.jwt import create_access_token, create_refresh_token, decode_token


class TestCreateAccessToken:
    def test_creates_valid_token(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=30
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_expected_claims(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=30
        )
        payload = decode_token(token, secret="test-secret")
        assert payload["sub"] == str(user_id)
        assert payload["plan"] == "free"
        assert payload["type"] == "access"


class TestCreateRefreshToken:
    def test_creates_valid_token(self):
        user_id = uuid.uuid4()
        token = create_refresh_token(
            user_id=user_id, secret="test-secret", expires_days=30
        )
        payload = decode_token(token, secret="test-secret")
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"


class TestDecodeToken:
    def test_invalid_token_returns_none(self):
        result = decode_token("garbage.token.here", secret="test-secret")
        assert result is None

    def test_wrong_secret_returns_none(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="secret-a", expires_minutes=30
        )
        result = decode_token(token, secret="secret-b")
        assert result is None

    def test_expired_token_returns_none(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=-1
        )
        result = decode_token(token, secret="test-secret")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jwt.py -v`
Expected: FAIL — `cannot import name 'create_access_token' from 'app.auth.jwt'`

- [ ] **Step 3: Implement app/auth/jwt.py**

```python
import uuid
from datetime import datetime, timedelta, timezone

import jwt


def create_access_token(
    user_id: uuid.UUID, plan: str, secret: str, expires_minutes: int = 30
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "plan": plan,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    user_id: uuid.UUID, secret: str, expires_days: int = 30
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jwt.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth/jwt.py tests/test_jwt.py
git commit -m "feat: add JWT creation and validation module"
```

---

### Task 6: GitHub OAuth Module

**Files:**
- Create: `app/auth/oauth.py`
- Create: `tests/test_oauth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oauth.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.auth.oauth import GitHubOAuth


class TestGitHubOAuth:
    def test_get_authorization_url(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")
        url = oauth.get_authorization_url(redirect_uri="http://localhost/callback")
        assert "github.com" in url
        assert "client_id=test-id" in url
        assert "redirect_uri=" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")

        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value={"access_token": "gho_abc123"})
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            token = await oauth.exchange_code("test-code", redirect_uri="http://localhost/callback")
        assert token == "gho_abc123"

    @pytest.mark.asyncio
    async def test_get_user_info(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")

        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value={
            "id": 12345,
            "login": "testuser",
            "email": "test@example.com",
        })
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            user_info = await oauth.get_user_info("gho_abc123")
        assert user_info["id"] == 12345
        assert user_info["login"] == "testuser"
        assert user_info["email"] == "test@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_oauth.py -v`
Expected: FAIL — `cannot import name 'GitHubOAuth'`

- [ ] **Step 3: Implement app/auth/oauth.py**

```python
from urllib.parse import urlencode

import httpx


class GitHubOAuth:
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def get_authorization_url(self, redirect_uri: str, scope: str = "read:user user:email") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            return data["access_token"]

    async def get_user_info(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_oauth.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth/oauth.py tests/test_oauth.py
git commit -m "feat: add GitHub OAuth client module"
```

---

### Task 7: Auth Pydantic Response Models

**Files:**
- Modify: `app/auth/models.py`

- [ ] **Step 1: Add new response models to app/auth/models.py**

Add below the existing `ApiKeyData` class:

```python
import uuid
from datetime import datetime


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


class BillingStatusResponse(BaseModel):
    plan: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from app.auth.models import TokenResponse, UserResponse, ApiKeyResponse, BillingStatusResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/auth/models.py
git commit -m "feat: add Pydantic response models for auth, user, and billing"
```

---

### Task 8: Auth Routes (GitHub OAuth + JWT Endpoints)

**Files:**
- Create: `app/api/auth_routes.py`
- Create: `tests/test_auth_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth_routes.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.jwt import create_access_token, create_refresh_token
from app.db.models import User
from app.main import create_app


@pytest.fixture
def oauth_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def oauth_client(oauth_app):
    transport = ASGITransport(app=oauth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestGitHubRedirect:
    async def test_returns_redirect_url(self, oauth_client, oauth_app):
        oauth_app.state.settings.github_client_id = "test-client-id"
        oauth_app.state.settings.base_url = "http://localhost:8000"
        resp = await oauth_client.get("/auth/github")
        assert resp.status_code == 200
        body = resp.json()
        assert "url" in body
        assert "github.com" in body["url"]
        assert "test-client-id" in body["url"]


class TestGitHubCallback:
    async def test_callback_creates_user_and_returns_tokens(self, oauth_client, oauth_app):
        oauth_app.state.settings.github_client_id = "test-id"
        oauth_app.state.settings.github_client_secret = "test-secret"
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        oauth_app.state.settings.base_url = "http://localhost:8000"

        mock_user = User(
            id=uuid.uuid4(),
            github_id=12345,
            github_username="testuser",
            email="test@example.com",
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes.GitHubOAuth") as MockOAuth:
            mock_oauth = AsyncMock()
            mock_oauth.exchange_code.return_value = "gho_abc123"
            mock_oauth.get_user_info.return_value = {
                "id": 12345,
                "login": "testuser",
                "email": "test@example.com",
            }
            MockOAuth.return_value = mock_oauth

            with patch("app.api.auth_routes._get_or_create_user", return_value=mock_user):
                resp = await oauth_client.get("/auth/callback?code=test-code")

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_callback_missing_code_returns_400(self, oauth_client):
        resp = await oauth_client.get("/auth/callback")
        assert resp.status_code == 400


class TestRefreshToken:
    async def test_refresh_returns_new_access_token(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"

        user_id = uuid.uuid4()
        refresh = create_refresh_token(user_id=user_id, secret="test-jwt-secret", expires_days=30)

        mock_user = User(
            id=user_id,
            github_id=12345,
            github_username="testuser",
            email=None,
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes._get_user_by_id", return_value=mock_user):
            resp = await oauth_client.post(
                "/auth/refresh",
                json={"refresh_token": refresh},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    async def test_refresh_with_invalid_token_returns_401(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        resp = await oauth_client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert resp.status_code == 401


class TestMeEndpoint:
    async def test_me_returns_user_info(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-jwt-secret", expires_minutes=30
        )

        mock_user = User(
            id=user_id,
            github_id=12345,
            github_username="testuser",
            email="test@example.com",
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes._get_user_by_id", return_value=mock_user):
            resp = await oauth_client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["github_username"] == "testuser"
        assert body["plan"] == "free"

    async def test_me_without_token_returns_401(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        resp = await oauth_client.get("/auth/me")
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auth_routes.py -v`
Expected: FAIL — `cannot import name 'auth_routes'`

- [ ] **Step 3: Implement app/api/auth_routes.py**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

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
```

- [ ] **Step 4: Register auth_router in app/main.py**

Add to `create_app()` in `app/main.py`, after the admin_router import (line 76):

```python
    from app.api.auth_routes import auth_router
    app.include_router(auth_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth_routes.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/auth_routes.py app/main.py tests/test_auth_routes.py
git commit -m "feat: add GitHub OAuth and JWT auth endpoints"
```

---

### Task 9: Account Routes (API Key Self-Service)

**Files:**
- Create: `app/api/account_routes.py`
- Create: `tests/test_account_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_account_routes.py`:

```python
import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.jwt import create_access_token
from app.db.models import ApiKey, User
from app.main import create_app


@pytest.fixture
def account_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    settings.jwt_secret = "test-jwt-secret"
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def account_client(account_app):
    transport = ASGITransport(app=account_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_token(user_id: uuid.UUID, plan: str = "free") -> str:
    return create_access_token(
        user_id=user_id, plan=plan, secret="test-jwt-secret", expires_minutes=30
    )


def _make_user(user_id: uuid.UUID) -> User:
    user = User(
        id=user_id,
        github_id=12345,
        github_username="testuser",
        email="test@example.com",
        plan="free",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return user


def _make_api_key(user_id: uuid.UUID) -> ApiKey:
    return ApiKey(
        id=uuid.uuid4(),
        user_id=user_id,
        key="so_live_" + secrets.token_urlsafe(32),
        active=True,
        created_at=datetime.now(timezone.utc),
    )


class TestGetKey:
    async def test_no_key_returns_empty(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            resp = await account_client.get(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["key"] is None

    async def test_returns_existing_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            resp = await account_client.get(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == api_key.key
        assert body["active"] is True


class TestCreateKey:
    async def test_creates_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            with patch("app.api.account_routes._create_api_key", return_value=api_key):
                resp = await account_client.post(
                    "/account/keys",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 201
        assert resp.json()["key"] == api_key.key

    async def test_conflict_if_key_exists(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            resp = await account_client.post(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 409


class TestDeleteKey:
    async def test_deletes_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            with patch("app.api.account_routes._revoke_api_key", return_value=True):
                resp = await account_client.delete(
                    "/account/keys",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200

    async def test_404_if_no_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            resp = await account_client.delete(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404


class TestUnauthorized:
    async def test_no_token_returns_401(self, account_client):
        resp = await account_client.get("/account/keys")
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_account_routes.py -v`
Expected: FAIL — cannot import `account_routes`

- [ ] **Step 3: Implement app/api/account_routes.py**

```python
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.auth_routes import _require_jwt
from app.auth.models import ApiKeyResponse
from app.db.engine import get_session_factory
from app.db.models import ApiKey

account_router = APIRouter(prefix="/account", tags=["account"])


async def _get_user_api_key(user_id: uuid.UUID) -> ApiKey | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.active.is_(True))
        )
        return result.scalar_one_or_none()


async def _create_api_key(user_id: uuid.UUID) -> ApiKey:
    key_value = "so_live_" + secrets.token_urlsafe(32)
    session_factory = get_session_factory()
    async with session_factory() as session:
        api_key = ApiKey(user_id=user_id, key=key_value)
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
        return api_key


async def _revoke_api_key(api_key: ApiKey) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as session:
        api_key = await session.get(ApiKey, api_key.id)
        if api_key is None:
            return False
        api_key.active = False
        await session.commit()
        return True


@account_router.get("/keys")
async def get_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    api_key = await _get_user_api_key(user_id)
    if api_key is None:
        return {"key": None, "active": None, "created_at": None}
    return ApiKeyResponse(key=api_key.key, active=api_key.active, created_at=api_key.created_at)


@account_router.post("/keys", status_code=201)
async def create_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    existing = await _get_user_api_key(user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="API key already exists. Revoke it first to generate a new one.")
    api_key = await _create_api_key(user_id)
    return ApiKeyResponse(key=api_key.key, active=api_key.active, created_at=api_key.created_at)


@account_router.delete("/keys")
async def delete_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    api_key = await _get_user_api_key(user_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail="No active API key found")
    await _revoke_api_key(api_key)
    return {"status": "revoked"}
```

- [ ] **Step 4: Register account_router in app/main.py**

Add to `create_app()` in `app/main.py`, after the auth_router import:

```python
    from app.api.account_routes import account_router
    app.include_router(account_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_account_routes.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/account_routes.py app/main.py tests/test_account_routes.py
git commit -m "feat: add self-service API key management endpoints"
```

---

### Task 10: Billing Service (Stripe)

**Files:**
- Create: `app/billing/__init__.py`
- Create: `app/billing/service.py`
- Create: `tests/test_billing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_billing.py`:

```python
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.billing.service import BillingService


class TestCreateCheckoutSession:
    def test_creates_session_and_returns_url(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            url = svc.create_checkout_session(
                user_id=uuid.uuid4(),
                customer_email="test@example.com",
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
            )
        assert url == "https://checkout.stripe.com/pay/cs_test_abc"
        mock_create.assert_called_once()

    def test_uses_existing_customer_id(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            svc.create_checkout_session(
                user_id=uuid.uuid4(),
                customer_email="test@example.com",
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
                stripe_customer_id="cus_existing",
            )
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["customer"] == "cus_existing"
        assert "customer_email" not in call_kwargs


class TestCreatePortalSession:
    def test_creates_portal_session(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/p/session/test"

        with patch("stripe.billing_portal.Session.create", return_value=mock_session):
            url = svc.create_portal_session(
                customer_id="cus_123",
                return_url="http://localhost/account",
            )
        assert url == "https://billing.stripe.com/p/session/test"


class TestVerifyWebhook:
    def test_valid_signature(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            pro_price_id="price_123",
        )
        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"

        with patch("stripe.Webhook.construct_event", return_value=mock_event):
            event = svc.verify_webhook(payload=b"body", sig_header="sig", webhook_secret="whsec_test")
        assert event.type == "checkout.session.completed"

    def test_invalid_signature_raises(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            pro_price_id="price_123",
        )
        import stripe
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig"),
        ):
            with pytest.raises(ValueError):
                svc.verify_webhook(payload=b"body", sig_header="sig", webhook_secret="whsec_test")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_billing.py -v`
Expected: FAIL — `cannot import name 'BillingService'`

- [ ] **Step 3: Create app/billing/__init__.py**

Empty file.

- [ ] **Step 4: Implement app/billing/service.py**

```python
import uuid

import stripe


class BillingService:
    def __init__(self, secret_key: str, webhook_secret: str, pro_price_id: str) -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.pro_price_id = pro_price_id
        stripe.api_key = secret_key

    def create_checkout_session(
        self,
        user_id: uuid.UUID,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        params: dict = {
            "mode": "subscription",
            "line_items": [{"price": self.pro_price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"user_id": str(user_id)},
        }
        if stripe_customer_id:
            params["customer"] = stripe_customer_id
        else:
            params["customer_email"] = customer_email

        session = stripe.checkout.Session.create(**params)
        return session.url

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def verify_webhook(self, payload: bytes, sig_header: str, webhook_secret: str):
        try:
            return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f"Invalid webhook signature: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_billing.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/billing/ tests/test_billing.py
git commit -m "feat: add Stripe billing service (checkout, portal, webhook verification)"
```

---

### Task 11: Billing & Webhook Routes

**Files:**
- Create: `app/api/webhook_routes.py`
- Modify: `app/api/account_routes.py` (add billing endpoints)
- Create: `tests/test_webhook.py`

- [ ] **Step 1: Write the failing webhook tests**

Create `tests/test_webhook.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.db.models import User
from app.main import create_app


@pytest.fixture
def webhook_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    settings.stripe_secret_key = "sk_test_123"
    settings.stripe_webhook_secret = "whsec_test"
    settings.stripe_pro_price_id = "price_123"
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def webhook_client(webhook_app):
    transport = ASGITransport(app=webhook_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestStripeWebhook:
    async def test_checkout_completed_upgrades_user(self, webhook_client, webhook_app):
        user_id = uuid.uuid4()

        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"
        mock_event.data.object = {
            "metadata": {"user_id": str(user_id)},
            "customer": "cus_123",
            "subscription": "sub_123",
        }

        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.return_value = mock_event
            MockBilling.return_value = mock_billing

            with patch("app.api.webhook_routes._update_user_plan") as mock_update:
                mock_update.return_value = None
                resp = await webhook_client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "checkout.session.completed"}',
                    headers={"stripe-signature": "test-sig"},
                )

        assert resp.status_code == 200
        mock_update.assert_called_once_with(
            user_id=user_id,
            plan="pro",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
        )

    async def test_subscription_deleted_downgrades_user(self, webhook_client, webhook_app):
        user_id = uuid.uuid4()

        mock_event = MagicMock()
        mock_event.type = "customer.subscription.deleted"
        mock_event.data.object = {
            "metadata": {"user_id": str(user_id)},
            "customer": "cus_123",
        }

        mock_user = User(
            id=user_id,
            github_id=123,
            github_username="test",
            plan="pro",
            stripe_customer_id="cus_123",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.return_value = mock_event
            MockBilling.return_value = mock_billing

            with patch("app.api.webhook_routes._get_user_by_stripe_customer", return_value=mock_user):
                with patch("app.api.webhook_routes._update_user_plan") as mock_update:
                    mock_update.return_value = None
                    resp = await webhook_client.post(
                        "/webhooks/stripe",
                        content=b'{"type": "customer.subscription.deleted"}',
                        headers={"stripe-signature": "test-sig"},
                    )

        assert resp.status_code == 200

    async def test_invalid_signature_returns_400(self, webhook_client, webhook_app):
        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.side_effect = ValueError("bad sig")
            MockBilling.return_value = mock_billing

            resp = await webhook_client.post(
                "/webhooks/stripe",
                content=b"bad",
                headers={"stripe-signature": "bad-sig"},
            )
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webhook.py -v`
Expected: FAIL — cannot import `webhook_routes`

- [ ] **Step 3: Implement app/api/webhook_routes.py**

```python
import uuid
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.billing.service import BillingService
from app.db.engine import get_session_factory
from app.db.models import User

logger = logging.getLogger("sliceops.webhooks")

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _update_user_plan(
    user_id: uuid.UUID,
    plan: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            logger.warning("Webhook: user not found", extra={"user_id": str(user_id)})
            return
        user.plan = plan
        if stripe_customer_id:
            user.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            user.stripe_subscription_id = stripe_subscription_id
        await session.commit()


async def _get_user_by_stripe_customer(customer_id: str) -> User | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        return result.scalar_one_or_none()


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    settings = request.app.state.settings
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )

    try:
        event = billing.verify_webhook(
            payload=payload,
            sig_header=sig_header,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.type
    data = event.data.object

    if event_type == "checkout.session.completed":
        user_id_str = data.get("metadata", {}).get("user_id")
        if user_id_str:
            await _update_user_plan(
                user_id=uuid.UUID(user_id_str),
                plan="pro",
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )
            logger.info("User upgraded to pro", extra={"user_id": user_id_str})

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            user = await _get_user_by_stripe_customer(customer_id)
            if user:
                await _update_user_plan(
                    user_id=user.id,
                    plan="free",
                    stripe_subscription_id=None,
                )
                logger.info("User downgraded to free", extra={"user_id": str(user.id)})

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        if customer_id:
            user = await _get_user_by_stripe_customer(customer_id)
            if user:
                logger.info("Subscription updated", extra={"user_id": str(user.id)})

    return {"status": "ok"}
```

- [ ] **Step 4: Add billing endpoints to app/api/account_routes.py**

Append to `app/api/account_routes.py`:

```python
from app.auth.models import BillingStatusResponse
from app.billing.service import BillingService
from app.db.models import User


async def _get_user(user_id: uuid.UUID) -> User | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()


@account_router.get("/billing")
async def get_billing(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return BillingStatusResponse(
        plan=user.plan,
        stripe_customer_id=user.stripe_customer_id,
        stripe_subscription_id=user.stripe_subscription_id,
    )


@account_router.post("/billing/checkout")
async def create_checkout(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.plan == "pro":
        raise HTTPException(status_code=400, detail="Already on Pro plan. Use billing portal to manage subscription.")

    settings = request.app.state.settings
    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )
    url = billing.create_checkout_session(
        user_id=user.id,
        customer_email=user.email or "",
        success_url=f"{settings.base_url}/account/billing?success=true",
        cancel_url=f"{settings.base_url}/account/billing?cancelled=true",
        stripe_customer_id=user.stripe_customer_id,
    )
    return {"checkout_url": url}


@account_router.post("/billing/portal")
async def create_portal(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Subscribe to Pro first.")

    settings = request.app.state.settings
    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )
    url = billing.create_portal_session(
        customer_id=user.stripe_customer_id,
        return_url=f"{settings.base_url}/account/billing",
    )
    return {"portal_url": url}
```

Add the additional import at the top of `app/api/account_routes.py`:

```python
from app.db.models import ApiKey, User
```

- [ ] **Step 5: Register webhook_router in app/main.py**

Add to `create_app()` in `app/main.py`:

```python
    from app.api.webhook_routes import webhook_router
    app.include_router(webhook_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_webhook.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/api/webhook_routes.py app/api/account_routes.py app/main.py tests/test_webhook.py
git commit -m "feat: add Stripe webhook handler and billing account endpoints"
```

---

### Task 12: Update API Key Validation (Postgres + Redis Cache)

**Files:**
- Modify: `app/auth/dependencies.py`
- Modify: `app/auth/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_key_validation.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.models import ApiKeyData
from app.db.models import ApiKey, User
from app.main import create_app


@pytest.fixture
def key_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    import os
    os.environ["SLICEOPS_AUTH_ENABLED"] = "true"
    application = create_app()
    settings = Settings()
    settings.auth_enabled = True
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = None
    application.state.redis = mock_redis

    os.environ["SLICEOPS_AUTH_ENABLED"] = "false"
    return application


@pytest.fixture
async def key_client(key_app):
    transport = ASGITransport(app=key_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestKeyValidationWithPostgres:
    async def test_valid_key_from_db(self, key_client, key_app):
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            github_id=123,
            github_username="test",
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        api_key = ApiKey(
            id=uuid.uuid4(),
            user_id=user_id,
            key="so_live_testkey",
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        api_key.user = user

        with patch("app.auth.dependencies._lookup_key_in_db", return_value=api_key):
            resp = await key_client.get(
                "/api/v1/health",
                headers={"X-API-Key": "so_live_testkey"},
            )
        # Health doesn't require auth, but this validates the key path doesn't crash
        assert resp.status_code == 200

    async def test_missing_key_returns_401(self, key_client):
        resp = await key_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
        )
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_key_validation.py -v`
Expected: FAIL — `_lookup_key_in_db` not found

- [ ] **Step 3: Rewrite app/auth/dependencies.py**

Replace the entire content of `app/auth/dependencies.py`:

```python
import json

from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.auth.models import ApiKeyData
from app.config import Settings
from app.db.engine import get_session_factory
from app.db.models import ApiKey


CACHE_TTL = 60  # seconds


async def _lookup_key_in_db(key: str) -> ApiKey | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiKey).options(joinedload(ApiKey.user)).where(ApiKey.key == key)
        )
        return result.scalar_one_or_none()


async def get_api_key(request: Request) -> ApiKeyData:
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return ApiKeyData(
            key="disabled",
            owner="anonymous",
            plan="paid",
            active=True,
            created_at="",
        )

    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    redis = request.app.state.redis

    # Check Redis cache first
    cache_key = f"sliceops:keycache:{key}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        if not data["active"]:
            raise HTTPException(status_code=403, detail="API key has been revoked")
        return ApiKeyData(**data)

    # Fallback to Postgres
    api_key = await _lookup_key_in_db(key)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not api_key.active:
        raise HTTPException(status_code=403, detail="API key has been revoked")

    key_data = ApiKeyData(
        key=api_key.key,
        owner=api_key.user.github_username,
        plan=api_key.user.plan,
        active=api_key.active,
        created_at=api_key.created_at.isoformat(),
    )

    # Cache in Redis
    await redis.setex(cache_key, CACHE_TTL, key_data.model_dump_json())

    return key_data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_key_validation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run existing tests to make sure nothing broke**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still PASS (existing tests use `SLICEOPS_AUTH_ENABLED=false` which bypasses the new code path)

- [ ] **Step 6: Commit**

```bash
git add app/auth/dependencies.py tests/test_key_validation.py
git commit -m "feat: rewrite API key validation to use Postgres with Redis cache"
```

---

### Task 13: Database Lifecycle in main.py

**Files:**
- Modify: `app/main.py:20-53`

- [ ] **Step 1: Update the lifespan to initialize and close the Postgres engine**

In `app/main.py`, update the `lifespan` function. Add the DB engine initialization at the start of the `yield` block and close it after:

Add import at the top:

```python
from app.db.engine import get_engine, get_session_factory, close_engine
```

In the `lifespan` function, after `app.state.rate_limit_service = ...` (line 49), add:

```python
    # Database engine
    get_engine(settings)
    get_session_factory(settings)
```

After `await redis_client.aclose()` (line 53), add:

```python
    await close_engine()
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add Postgres engine lifecycle to FastAPI lifespan"
```

---

### Task 14: Docker Compose — Add PostgreSQL

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add postgres service to docker-compose.yml**

Add the `postgres` service after the `redis` service:

```yaml
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: sliceops
      POSTGRES_PASSWORD: sliceops
      POSTGRES_DB: sliceops
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sliceops"]
      interval: 10s
      timeout: 5s
      retries: 3
```

- [ ] **Step 2: Add database URL env var to api and worker services**

Add to the `environment` section of both `api` and `worker` services:

```yaml
      - SLICEOPS_DATABASE_URL=postgresql+asyncpg://sliceops:sliceops@postgres:5432/sliceops
```

- [ ] **Step 3: Add postgres dependency to api and worker services**

Add `postgres` to the `depends_on` of both `api` and `worker`:

```yaml
      postgres:
        condition: service_healthy
```

- [ ] **Step 4: Add postgres-data volume**

Add to the `volumes` section at the bottom:

```yaml
  postgres-data:
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add PostgreSQL service to docker-compose"
```

---

### Task 15: Verify All Existing Tests Still Pass

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. The existing tests use `SLICEOPS_AUTH_ENABLED=false` so they bypass Postgres and use the dummy key path.

- [ ] **Step 2: If any tests fail, fix them**

Common issues to check:
- Import errors from changed `app/auth/dependencies.py` — existing tests mock `auth_service.validate_key` which is no longer the path used. Since `auth_enabled=false` returns the dummy key, these should still work.
- Any new imports that fail at module load time.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: ensure existing tests pass with new auth infrastructure"
```

---

### Task 16: Update .env.example and Documentation

**Files:**
- Create: `.env.example`
- The README and internal docs can be updated separately as needed.

- [ ] **Step 1: Create .env.example with all environment variables**

```bash
# SliceOps Configuration

# Slicers
SLICEOPS_PRUSA_SLICER_PATH=prusa-slicer
SLICEOPS_BAMBU_STUDIO_PATH=bambu-studio

# Redis
SLICEOPS_REDIS_URL=redis://localhost:6379/0

# PostgreSQL
SLICEOPS_DATABASE_URL=postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops

# Admin
SLICEOPS_ADMIN_API_KEY=

# GitHub OAuth
SLICEOPS_GITHUB_CLIENT_ID=
SLICEOPS_GITHUB_CLIENT_SECRET=

# Stripe
SLICEOPS_STRIPE_SECRET_KEY=
SLICEOPS_STRIPE_WEBHOOK_SECRET=
SLICEOPS_STRIPE_PRO_PRICE_ID=

# JWT
SLICEOPS_JWT_SECRET=change-me-in-production

# Base URL (for OAuth callback URLs)
SLICEOPS_BASE_URL=http://localhost:8000
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with all configuration variables"
```
