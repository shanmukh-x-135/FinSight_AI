# Authentication & User Preferences (Phase 1)

How the auth module works: token lifecycle, the refresh/rotation flow, how to
protect a new route, and the preferences schema that drives later
personalization.

## Endpoints

All under `/api/v1`, all responses in the standard envelope
(`success · message · data · timestamp · requestId`).

| Method & path              | Auth | Purpose                                            |
|----------------------------|------|----------------------------------------------------|
| `POST /auth/register`      | –    | Create an account (+ default preferences). 201.    |
| `POST /auth/login`         | –    | Exchange credentials for an access+refresh pair.   |
| `POST /auth/refresh`       | –    | Rotate tokens using a valid refresh token.         |
| `GET  /user/me`            | ✔    | Current user + preferences (the canonical protected route). |
| `GET  /user/preferences`   | ✔    | Read preferences.                                  |
| `PUT  /user/preferences`   | ✔    | Partial update of preferences.                     |

`POST /auth/login` is rate-limited per client IP (default: 5 attempts / 60s) →
HTTP 429 when exceeded.

## Tokens

Two JWT types (HS256), configured in `config/settings.py`:

| Token   | Claim `type` | Lifetime (default)                | Extra claims |
|---------|--------------|-----------------------------------|--------------|
| access  | `access`     | `ACCESS_TOKEN_EXPIRE_MINUTES` (30)| —            |
| refresh | `refresh`    | `REFRESH_TOKEN_EXPIRE_DAYS` (7)   | `jti`        |

- The **access token** is sent as `Authorization: Bearer <token>` on every
  authenticated request.
- The **refresh token** carries a unique `jti` recorded in the `sessions` table.

## Refresh & rotation flow

1. `POST /auth/login` issues an access+refresh pair and inserts a `sessions` row
   keyed by the refresh token's `jti`.
2. `POST /auth/refresh` with a refresh token:
   - decode + validate (signature, expiry, `type == refresh`);
   - look up the `jti` in `sessions`; reject if missing, revoked, or expired;
   - **revoke** that session row (rotation) and issue a brand-new pair.
3. A rotated (old) refresh token therefore fails on reuse — replay protection.

Revocation is server-side: deleting/revoking a `sessions` row invalidates its
refresh token immediately.

## Protecting a new route

Depend on `get_current_user` from `app/auth/dependencies.py`:

```python
from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter()

@router.get("/something")
async def handler(user: User = Depends(get_current_user)):
    return {"user_id": user.id}
```

Missing/expired/invalid/wrong-type tokens yield a clean **401** (never a 500),
rendered in the error envelope with `error.type == "invalid_token"`.

## Password hashing

Argon2id via `argon2-cffi` (`app/shared/security/passwords.py`). Salts are
embedded in the hash; hashes are never logged or returned in any response. The
login path runs a throwaway verify on the "user not found" branch to equalize
timing against account enumeration.

## Data model (User domain)

Three tables (design doc §6.3), migration `0002_auth` plus the administrator
capability migration `0008_user_admin`:

- **users** — `id, email (unique), hashed_password, is_active, is_admin, created_at`.
- **preferences** — 1:1 with users:
  `risk_tolerance, investment_horizon, preferred_market, preferred_sectors (JSON list)`.
  A default row is created at registration.
- **sessions** — issued refresh tokens: `user_id, jti (unique), expires_at, revoked, created_at`.

### Preference vocabularies (`app/auth/constants.py`)

| Field                | Allowed values                          | Default    |
|----------------------|-----------------------------------------|------------|
| `risk_tolerance`     | conservative · moderate · aggressive    | moderate   |
| `investment_horizon` | short · medium · long                   | medium     |
| `preferred_market`   | IN · US                                 | IN         |
| `preferred_sectors`  | list of free-form sector names          | `[]`       |

These preferences drive report generation, recommendation ranking, alert
thresholds, dashboard content, and AI responses in later phases (design doc §5.10).

### Operations-only routes

Manual market/news ingestion and historical-index rebuild routes depend on
`get_admin_user`. Registration always creates `is_admin = false`; administrators
must be promoted directly through a controlled database/operations workflow.
There is intentionally no public self-promotion endpoint. Missing credentials
return 401, while an authenticated non-admin receives 403 with
`error.type == "admin_access_required"`.

## Frontend token storage

The frontend (`frontend/lib/api.ts`, `frontend/lib/auth-context.tsx`) stores the
access + refresh tokens in **localStorage** and sends the access token as a
Bearer header. One consistent approach across the app. On a 401 it transparently
attempts a single refresh, then retries. Trade-off: localStorage is exposed to
XSS; a future hardening is httpOnly, SameSite cookies (would require the API and
web app to share a domain or a credentialed CORS setup).

## Tests

`backend/tests/auth/` — unit tests for hashing and JWT, service-level edge cases
(deactivated account), and full API-flow tests (register/login/refresh/rotation/
preferences/rate-limit). Coverage on the auth module is ~99% (target: 80%+).
