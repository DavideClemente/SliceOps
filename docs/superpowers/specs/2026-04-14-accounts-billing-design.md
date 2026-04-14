# User Accounts, API Key Self-Service & Stripe Billing

## Overview

Add user accounts (GitHub OAuth), self-service API key management, and Stripe subscription billing to SliceOps. Users sign up with GitHub, get a free plan with an API key, and can upgrade to Pro via Stripe.

## Decisions

- **Auth:** GitHub OAuth only (no passwords, no GDPR credential concerns)
- **OAuth library:** `httpx-oauth` (async-native, minimal)
- **Database:** PostgreSQL via SQLAlchemy async + Alembic migrations
- **Session:** JWT (access + refresh tokens) via `PyJWT`
- **Billing:** Stripe Checkout + Billing Portal, recurring subscriptions
- **Plans:** Free and Pro (configurable limits, pricing set in Stripe)
- **API keys:** One per user, auto-generated, no user input needed

## Data Model

### PostgreSQL Tables

**`users`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `github_id` | INTEGER | Unique, from GitHub OAuth |
| `github_username` | VARCHAR | Display name |
| `email` | VARCHAR | Nullable (GitHub email can be private) |
| `plan` | VARCHAR | `"free"` or `"pro"`, default `"free"` |
| `stripe_customer_id` | VARCHAR | Nullable |
| `stripe_subscription_id` | VARCHAR | Nullable |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**`api_keys`** (replaces Redis-based key storage)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK -> users, unique (one key per user) |
| `key` | VARCHAR | Unique, the `so_live_...` token |
| `active` | BOOLEAN | Default true |
| `created_at` | TIMESTAMP | |

**Redis (unchanged):** Job state, rate limit counters, usage tracking.

**Migration path:** Existing admin-created Redis API keys won't carry over. Pre-production, so old keys are replaced by user-created ones.

## Auth Flow

1. Client calls `GET /auth/github` -> API returns redirect URL to GitHub OAuth
2. User authorizes -> GitHub redirects to `GET /auth/callback?code=...`
3. API exchanges code for GitHub access token, fetches user profile
4. If `github_id` exists -> existing user. If not -> create user with `plan="free"`
5. API returns JWT access token (30 min) + refresh token (30 days)

### Auth Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /auth/github` | None | Get GitHub OAuth URL |
| `GET /auth/callback` | None | OAuth callback, returns JWT |
| `POST /auth/refresh` | Refresh token | Get new access token |
| `GET /auth/me` | JWT | Get current user profile |

### Token Details

- Access token: 30 min TTL, contains `user_id`, `plan`
- Refresh token: 30 days TTL, signed JWT
- JWT auth is for account management endpoints only
- API key auth (`X-API-Key`) remains for slicing endpoints

## Self-Service API Key Management

### Endpoints (JWT-protected)

| Endpoint | Method | Purpose |
|---|---|---|
| `/account/keys` | `GET` | Get the user's API key (or empty if none) |
| `/account/keys` | `POST` | Generate an API key (fails 409 if one exists) |
| `/account/keys` | `DELETE` | Revoke the key (can POST to regenerate) |

### Behavior

- One key per user (enforced by unique constraint on `user_id`)
- Key auto-generated (`so_live_...` format), no user input needed
- Plan limits resolved from the user record, not stored on the key
- Revoking + regenerating gives a new key, old one stops working

### Key Validation Change

The `get_api_key` dependency is updated to:
1. Look up key in PostgreSQL, join to user table for current plan
2. Cache result in Redis with 60s TTL
3. Rate limiting reads plan from cached user data

## Stripe Integration

### Billing Endpoints (JWT-protected)

| Endpoint | Method | Purpose |
|---|---|---|
| `/account/billing/checkout` | `POST` | Create Stripe Checkout Session, returns URL |
| `/account/billing/portal` | `POST` | Create Stripe Billing Portal session, returns URL |
| `/account/billing` | `GET` | Get current billing status (plan, renewal date) |

### Webhook

`POST /webhooks/stripe` (no auth, Stripe signature verification)

**Events handled:**
- `checkout.session.completed` -> upgrade user to pro
- `customer.subscription.updated` -> sync plan changes
- `customer.subscription.deleted` -> downgrade to free
- `invoice.payment_failed` -> optional flagging (Stripe retries automatically)

**Idempotency:** Use Stripe event ID to prevent duplicate processing.

### Stripe as Source of Truth

Billing state is always synced from Stripe via webhooks. Client never directly sets plan.

## Error Handling & Edge Cases

**OAuth:**
- User cancels -> callback returns error JSON
- Token exchange fails -> 502
- No public email -> fine, email is nullable

**Keys:**
- Create second key -> 409 Conflict
- Delete nonexistent key -> 404

**Billing:**
- Already on Pro + checkout -> error or redirect to portal
- Webhook before callback (race) -> upsert by `github_id`, idempotent
- Webhook replay -> deduplicate via Stripe event ID
- Payment fails -> Stripe retries; `subscription.deleted` -> downgrade to free
- Mid-cycle downgrade -> Stripe proration; plan updates at period end

**JWT:**
- Expired access token -> 401, use refresh
- Invalid/tampered -> 401
- Refresh expired -> 401, re-auth via GitHub

**Cache:**
- Plan upgrade -> DB updated via webhook -> Redis cache stale up to 60s (acceptable; can add explicit invalidation in webhook handler)

## Project Structure

### New Files

```
app/
  db/
    engine.py          # async SQLAlchemy engine + session factory
    models.py          # User, ApiKey SQLAlchemy models
  auth/
    oauth.py           # GitHub OAuth flow
    jwt.py             # JWT creation/validation
  api/
    auth_routes.py     # /auth/* endpoints
    account_routes.py  # /account/* endpoints
    webhook_routes.py  # /webhooks/stripe
  billing/
    service.py         # Stripe checkout, portal, webhook handling
alembic/               # Migration directory
alembic.ini            # Alembic config
```

### Modified Files

- `app/auth/service.py` — rewritten for PostgreSQL-backed key operations
- `app/auth/dependencies.py` — key validation via Postgres + Redis cache, plan from user
- `app/config.py` — new env vars (Postgres URL, GitHub OAuth, Stripe keys, JWT secret)
- `app/main.py` — register new routers, Postgres engine lifecycle
- `docker-compose.yml` — add postgres service

### Unchanged

- Slicing endpoints, job store, rate limiting logic, Celery worker, temp storage
- API key format (`so_live_...`)
- `X-API-Key` header auth for slicing

## New Dependencies

- `sqlalchemy[asyncio]` + `asyncpg` — async PostgreSQL ORM
- `alembic` — database migrations
- `httpx-oauth` — GitHub OAuth
- `PyJWT` — JWT token handling
- `stripe` — Stripe SDK

## New Environment Variables

| Variable | Purpose |
|---|---|
| `SLICEOPS_DATABASE_URL` | PostgreSQL connection string |
| `SLICEOPS_GITHUB_CLIENT_ID` | GitHub OAuth app client ID |
| `SLICEOPS_GITHUB_CLIENT_SECRET` | GitHub OAuth app client secret |
| `SLICEOPS_STRIPE_SECRET_KEY` | Stripe secret key |
| `SLICEOPS_STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SLICEOPS_STRIPE_PRO_PRICE_ID` | Stripe Price ID for Pro plan |
| `SLICEOPS_JWT_SECRET` | JWT signing secret |
| `SLICEOPS_BASE_URL` | Public base URL (for OAuth callback) |

## Testing Strategy

**Unit tests:**
- JWT creation/validation
- Stripe webhook signature verification
- API key generation logic
- Plan resolution (user -> key -> limits)

**Integration tests:**
- OAuth flow with mocked GitHub HTTP responses
- Stripe checkout/webhook with test mode + fixture events
- API key CRUD lifecycle (create, get, revoke, regenerate)
- Key validation with Redis cache (hit/miss/invalidation)
- Plan upgrade/downgrade reflected in rate limits

**Infrastructure:**
- Postgres test database (separate, wiped between runs)
- Existing Redis test setup unchanged
- `pytest-asyncio` for async tests

## Plans Configuration

Plans remain in `config/plans.yaml` with configurable limits. The `plan` field on the user record maps to the plan key in the YAML. Stripe doesn't control limits — it controls billing. The webhook updates the `plan` field, which maps to the YAML-defined limits.
