# Phase 13A — Authentication Audit and Reproduction

## Scope and current architecture

The Phase 1 authentication implementation uses short-lived JWT access tokens and
rotating JWT refresh tokens. Both tokens are returned in JSON and stored in
`localStorage` by the frontend. Protected API requests attach the access token as
a bearer header. A refresh token's `jti` is persisted in `sessions`; refresh
revokes that row and creates a replacement session.

One root-level client `AuthProvider` owns an in-memory `user` value. On mount it
checks for an access token and calls `GET /api/v1/user/me`. Protected routes wait
for that first check, then redirect to `/login` when no user is present. There is
no Next.js middleware or server-side session check. Logout only removes the two
local-storage values and does not call the backend.

## Root cause of the reported cross-page/tab failure

The browser storage and React session state are two independent sources of truth.
Login writes tokens to `localStorage`, but only updates the `AuthProvider` in the
document where login occurred. Other open documents do not listen for the
`storage` event, revalidate on focus, or receive any explicit session message.
They therefore remain in their previously resolved unauthenticated state and can
continue redirecting to `/login` after another tab has logged in.

Refresh behavior is additionally nondeterministic under concurrency. Every 401
starts its own refresh request. Refresh tokens rotate on first use, so two API
requests or tabs can present the same refresh token concurrently. One refresh
succeeds and stores a new token pair; the losing refresh sees the original token
as revoked and clears storage, potentially deleting the winner's valid pair.
This race explains why a subsequent hard refresh can also appear unreliable.

## Additional defects found

- Session hydration treats every `/me` failure—including network failures, 5xx
  responses, and backend cold starts—as invalid credentials and deletes tokens.
- Auth state only distinguishes `loading`, authenticated, and unauthenticated.
  It cannot represent refreshing, expired, or temporarily unavailable sessions.
- Hydration refuses to refresh when the access token is missing but a valid
  refresh token remains.
- Frontend logout does not revoke the persisted backend refresh session.
- Login/register always navigate to `/dashboard`; direct protected routes lose
  their intended destination.
- Auth pages do not react to an already authenticated session.
- A user's active/deactivated state is cached in React until a request or manual
  refresh updates it.
- Refresh logic is duplicated across JSON requests and streaming/download
  requests, allowing independent refresh races.
- Browser-JavaScript-readable access and refresh tokens increase the impact of
  an XSS defect.
- The in-memory login rate limit is process-local and is not authoritative in a
  multi-instance deployment.

## Reproduction matrix

The regression suite must cover these scenarios as the architecture is replaced:

| Scenario | Current result | Required result |
| --- | --- | --- |
| Tab B open before login in A | B stays logged out | B hydrates the new session |
| Logout in A | B retains authenticated UI | B immediately becomes signed out |
| Two protected requests receive 401 | Two rotating refreshes race | One shared refresh, both retry once |
| Hard refresh/direct route | Client-only check; intended route is lost on failure | Loading state, then route or return-to login |
| Access expired, refresh valid | Usually recovers; races can clear valid tokens | Deterministic recovery |
| Refresh expired/revoked | Tokens cleared without an expired state | Explicit expired state and useful sign-in path |
| Backend unavailable/cold | Tokens cleared and user appears logged out | Recoverable unavailable state; credentials retained |
| Browser restart | `localStorage` tokens hydrate client-side | Server-controlled session hydrates safely |
| Duplicate tab/new tab | New provider may hydrate; existing tab does not sync | Both converge on one session state |
| Logout then browser Back | Protected shell blocks content but backend session survives | Server session revoked; no stale protected content |
| Account deactivated | Next protected request fails and may trigger refresh | Session expires cleanly across tabs |

## Migration path

1. Introduce backend-owned HttpOnly cookie sessions while retaining the existing
   session table and refresh rotation semantics.
2. Add an explicit session endpoint/logout endpoint and CSRF protection for
   cookie-authenticated state-changing requests.
3. Make the frontend API transport credentialed and centralize refresh behind a
   single-flight coordinator with bounded retry.
4. Replace token presence checks with authoritative `/me` hydration and explicit
   checking/authenticated/unauthenticated/refreshing/expired/unavailable states.
5. Synchronize login/logout/session changes across tabs using `BroadcastChannel`
   with a storage-event fallback, then revalidate rather than sharing secrets.
6. Preserve a validated local-development mode and verify the real Vercel ↔
   Render cookie/CORS topology before removing the bearer compatibility path.
7. Add Google OIDC identities only after the unified session architecture is
   proven by unit, integration, and browser tests.

## Security constraints for Phase 13B

Cross-origin production cookies must use `HttpOnly`, `Secure`, `SameSite=None`,
an explicit lifetime, and the narrowest practical path/domain. Local HTTP
development requires environment-aware cookie settings. State-changing requests
must present a CSRF token bound to the session or an equivalent verified
same-origin signal; `HttpOnly` alone is not a CSRF defense. CORS must remain an
explicit origin allowlist with credentials enabled.
