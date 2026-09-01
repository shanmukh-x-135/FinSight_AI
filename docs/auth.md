# Authentication & User Preferences (Phase 13B)

How the auth module works: token lifecycle, the refresh/rotation flow, how to
protect a new route, and the preferences schema that drives later
personalization.

## Endpoints

All under `/api/v1`, all responses in the standard envelope
(`success · message · data · timestamp · requestId`).

| Method & path              | Auth | Purpose                                            |
|----------------------------|------|----------------------------------------------------|
| `POST /auth/register`      | –    | Create an account (+ default preferences). 201.    |
| `POST /auth/login`         | –    | Establish an HttpOnly cookie session.               |
| `GET  /auth/session`       | Cookie | Hydrate user state and a session-bound CSRF token. |
| `GET  /auth/csrf`          | Refresh cookie | Bootstrap CSRF before an expired-access refresh. |
| `POST /auth/refresh`       | Refresh cookie + CSRF | Rotate the cookie session.       |
| `POST /auth/logout`        | Cookie + CSRF | Revoke and clear the current session.           |
| `GET  /auth/google/start`  | – | Start Google OAuth 2.0 / OpenID Connect.             |
| `GET  /auth/google/callback` | Signed transaction | Verify and link Google identity.  |
| `GET  /user/me`            | ✔    | Current user + preferences (the canonical protected route). |
| `GET  /user/preferences`   | ✔    | Read preferences.                                  |
| `PUT  /user/preferences`   | ✔    | Partial update of preferences.                     |

`POST /auth/login` is rate-limited per client IP (default: 5 attempts / 60s) →
HTTP 429 when exceeded.

## Tokens

Two JWT types (HS256), configured in `config/settings.py`:

| Token   | Claim `type` | Lifetime (default)                | Extra claims |
|---------|--------------|-----------------------------------|--------------|
| access  | `access`     | `ACCESS_TOKEN_EXPIRE_MINUTES` (30)| session `jti`|
| refresh | `refresh`    | `REFRESH_TOKEN_EXPIRE_DAYS` (7)   | `jti`        |

- The browser receives both tokens only as `HttpOnly` cookies. JavaScript never
  reads or persists bearer credentials.
- The **refresh token** carries a unique `jti` recorded in the `sessions` table.
- The access token carries the same `jti`, making the persisted session row the
  authoritative logout/revocation boundary.

## Refresh & rotation flow

1. `POST /auth/login` issues an access+refresh pair as cookies and inserts a
   `sessions` row keyed by their shared `jti`.
2. `POST /auth/refresh` with the refresh cookie and matching CSRF header:
   - decode + validate (signature, expiry, `type == refresh`);
   - look up the `jti` in `sessions`; reject if missing, revoked, or expired;
   - lock the row on PostgreSQL so concurrent rotation is serialized;
   - **revoke** that session row and issue a brand-new cookie pair.
3. A rotated (old) refresh token therefore fails on reuse — replay protection.

Revocation is server-side: revoking a `sessions` row invalidates both access and
refresh authentication immediately.

The frontend funnels API traffic through `/api-proxy`, a Next.js same-origin
rewrite to Render. This makes cookies first-party on the Vercel application
origin instead of relying on cross-site third-party cookie behavior. Production
cookies use `Secure`, `HttpOnly`, `SameSite=Lax`, explicit lifetimes, and `/`
scope. Local HTTP development uses the same topology without `Secure`.

## CSRF

Cookie-authenticated `POST`, `PUT`, `PATCH`, and `DELETE` requests require
`X-CSRF-Token`. The token is an HMAC derived from the server-side session id and
is returned by session/login/refresh responses; it contains no bearer secret and
is held only in frontend memory. Refresh bootstrap uses `GET /auth/csrf`, whose
response cannot be read cross-origin because production CORS remains an explicit
credentialed allowlist. Rotation changes both the session id and CSRF token.

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

Four tables, introduced by `0002_auth`, `0008_user_admin`, and
`0020_google_identities`:

- **users** — `id, email (unique), hashed_password, is_active, is_admin, created_at`.
- **preferences** — 1:1 with users:
  `risk_tolerance, investment_horizon, preferred_market, preferred_sectors (JSON list)`.
  A default row is created at registration.
- **sessions** — issued refresh tokens: `user_id, jti (unique), expires_at, revoked, created_at`.
- **auth_identities** — external identity links:
  `user_id, provider, provider_subject, provider_email, linked_at`, with a unique
  provider+subject constraint. OAuth-only users have no password hash.

## Google OpenID Connect

`GET /auth/google/start` creates random state and nonce values, stores them in a
short-lived signed HttpOnly transaction cookie, and redirects to Google's
authorization endpoint. The configured redirect URI must use the frontend
gateway, for example:

```text
https://your-app.vercel.app/api-proxy/api/v1/auth/google/callback
```

The callback exchanges the one-time code on the backend. `google-auth` verifies
the ID-token signature, issuer, audience, and expiry; FinSight additionally
checks nonce, provider subject, email presence, and `email_verified == true`.
No browser-supplied profile or identity claim is trusted.

Linking rules are deliberately narrow:

- an existing Google subject signs into its already linked internal user;
- a new Google subject with the same verified email as a password account links
  to that account;
- a new verified email creates one OAuth-only internal user;
- a subject/email combination that points at different users is rejected rather
  than merged;
- missing, unverified, denied, expired, or conflicting flows return a stable
  error code to the login experience.

Configuration is all-or-none: `GOOGLE_OAUTH_CLIENT_ID`,
`GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REDIRECT_URI`. Secrets remain on
Render; the browser receives neither the client secret nor Google tokens.

### Preference vocabularies (`app/auth/constants.py`)

| Field                | Allowed values                          | Default    |
|----------------------|-----------------------------------------|------------|
| `risk_tolerance`     | conservative · moderate · aggressive    | moderate   |
| `investment_horizon` | short · medium · long                   | medium     |
| `preferred_market`   | IN · US                                 | IN         |
| `preferred_sectors`  | list of free-form sector names          | `[]`       |

These preferences are the persisted personalization surface for report,
recommendation, alert, dashboard, and conversational features (design doc §5.10).

### Operations-only routes

Manual market/news ingestion and historical-index rebuild routes depend on
`get_admin_user`. Registration always creates `is_admin = false`; administrators
must be promoted directly through a controlled database/operations workflow.
There is intentionally no public self-promotion endpoint. Missing credentials
return 401, while an authenticated non-admin receives 403 with
`error.type == "admin_access_required"`.

For the first production administrator, register the account normally and then
promote that exact user through the managed database console in a controlled
maintenance window. Verify the email and affected-row count before committing;
never expose self-promotion through a public endpoint. Re-login afterward so the
operator can call the protected ingestion, history rebuild, and EOD status
routes.

## Frontend session model

`frontend/lib/api.ts` sends credentialed requests through the same-origin proxy
and centralizes refresh behind one in-flight promise. Concurrent 401 responses
in one document share that promise. If two tabs race refresh-token rotation, the
loser checks the new shared access cookie and converges on the winning session
instead of clearing it.

`frontend/lib/auth-context.tsx` exposes explicit `checking`, `authenticated`,
`unauthenticated`, `refreshing`, `expired`, and `unavailable` states. Backend
cold starts and network errors retain credentials and show a recoverable state;
they are not treated as logout. `BroadcastChannel` plus a storage-event fallback
causes login/logout/rotation in one tab to revalidate every other open tab. The
storage event contains only an event type and timestamp, never credentials.

## Tests

`backend/tests/auth/` — unit tests for hashing and JWT, service-level edge cases
(deactivated account), and full API-flow tests (register/login/refresh/rotation/
preferences/rate-limit). Coverage on the auth module is ~99% (target: 80%+).
