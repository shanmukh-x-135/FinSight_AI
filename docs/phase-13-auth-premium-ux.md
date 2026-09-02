# Phase 13 — authentication and premium research UX

Phase 13 replaces the browser-readable token model with a server-authoritative
cookie session, adds Google OpenID Connect and password recovery, and establishes
one coherent research workspace across every product route. It does not change
the platform's analytics-first contract: deterministic services still calculate
rankings, metrics, evidence, risks, and confidence; language models explain them.

## Authentication audit and final architecture

The previous client stored access and refresh JWTs in `localStorage`. Each tab
hydrated independently, each failed request could begin its own refresh, and no
authoritative cross-tab event reconciled login or logout. A page opened before a
login could therefore remain unauthenticated while another page had a valid
session; refresh rotation also allowed tabs to disagree about which token won.

The final model is:

- the browser talks to FastAPI through the Next.js same-origin `/api-proxy`;
- access and rotating refresh JWTs exist only in `HttpOnly` cookies;
- access and refresh tokens share a `jti` backed by the `sessions` table;
- every protected request validates that persisted session, so revocation is
  immediate rather than waiting for JWT expiry;
- unsafe cookie-authenticated methods require an in-memory, session-bound HMAC
  CSRF token;
- one in-document promise serializes refresh; a losing tab in a rotation race
  rechecks the shared access cookie and converges on the winner;
- `BroadcastChannel`, with a storage-event fallback, broadcasts credential-free
  login, logout, and session-change notifications;
- the UI distinguishes checking, authenticated, unauthenticated, refreshing,
  expired, and backend-unavailable states. Network failure never destroys a
  potentially valid session.

Failed password logins are limited by normalized email and client IP. Only
invalid credentials consume the sliding window; successful logins clear prior
failures. This prevents brute-force attempts without locking out legitimate
multi-tab or test-suite logins.

See [Authentication](auth.md) for the endpoint, cookie, CSRF, and rotation
details.

## Google OpenID Connect and recovery

Google sign-in uses a short-lived signed `HttpOnly` transaction cookie containing
random state, nonce, and a validated local return path. The backend exchanges the
authorization code and verifies signature, issuer, audience, expiry, nonce,
subject, verified email, and identity consistency. Existing verified-email
password accounts can be linked; conflicts are rejected instead of guessed or
merged. Provider denial, invalid state, missing code, unavailable configuration,
and identity conflicts map to stable, recoverable UI messages.

Password recovery stores only a SHA-256 token digest, supersedes older unused
tokens, expires tokens, permits one use, revokes all sessions after reset, and
uses a generic response to prevent account enumeration. Resend receives the raw
token only as part of the delivery link and uses an idempotency key; delivery
logs omit addresses and credentials.

Production requires the Render-only values listed in `render.yaml`: Google
client ID/secret/redirect URI, Resend key/from address, frontend URL, explicit
CORS origins, database URL, and JWT secret. Google must authorize the exact
same-origin callback:

```text
https://<frontend-domain>/api-proxy/api/v1/auth/google/callback
```

## Authentication experience

Login, registration, forgot-password, reset-password, and OAuth callback screens
share a responsive split composition, explicit labels, password-manager metadata,
visibility controls, keyboard focus treatments, non-enumerating recovery copy,
and honest progress/error states. Protected routes retain a skeleton while the
initial session is unknown, preventing login flashes during hydration or refresh.

## Design system and route redesign

The workspace uses explicit display, page-heading, section-heading, label,
metadata, and financial-number roles; tabular figures; a restrained elevation
vocabulary; and semantic positive, negative, warning, delayed, stale, selected,
and confidence colors. Color is always paired with text or icons. `Panel`,
`MetricStrip`, `DataTable`, evidence disclosures, data-state components, and
research Markdown rendering replace repeated generic card grids and raw model
text.

The application shell provides a collapsible desktop rail, contextual top bar,
five-item mobile dock, complete keyboard-contained mobile drawer, and a global
`Ctrl/Cmd+K` palette for routes, actions, and NIFTY 100 instruments. Focus and
background scroll are restored when overlays close.

Route outcomes:

- **Overview:** compact market, portfolio, freshness, news, watchlist, opportunity,
  and risk hierarchy.
- **Market:** persisted universe/screener controls, dense sticky table, breadth,
  heatmap, rotation, technical, event, and evidence-backed signal layers.
- **News:** source-led evidence and explicit coverage/availability semantics.
- **Stock detail:** price history first, compact quote context, technical evidence,
  news, historical analogues, and contextual research actions.
- **Portfolio:** value/allocation/P&L and holdings before advanced risk; unavailable
  equity history is disclosed rather than fabricated.
- **Watchlist:** persistent controls and optimistic pin/remove with accessible
  announcements and rollback.
- **Research and strategies:** regime evidence, deterministic factors, rules,
  backtests, robustness, and audit tables retain their analytical hierarchy.
- **Discover:** filter workflow, validated AST explanation, saved screens, and
  deterministic results.
- **Reports:** filterable archive, generation, reader hierarchy, evidence,
  appendix, and Markdown/PDF export.
- **AI:** a focused research conversation with semantic rendered prose, persisted
  history, sources, risks, confidence, and shared evidence disclosure.
- **Settings:** compact preferences and account/session context using the same
  workspace language.

See [Frontend components](frontend-components.md) for the reusable component and
responsive behavior contracts.

## Interaction, accessibility, and responsive behavior

Every major route has distinct loading, error, empty, and populated states.
Tables contain their own overflow, sticky headings remain within local scrollers,
and the full route matrix is checked at desktop, laptop, and mobile widths.
Dialogs close with Escape, contain tab focus, lock background scroll, and restore
the invoking focus. A global `prefers-reduced-motion` rule removes non-essential
animation and smooth scrolling. Signed values never depend on color alone.

## Verification contract

Before release, run:

```bash
cd backend
./.venv/bin/python -m pytest
TEST_POSTGRES_URL=postgresql+asyncpg://finsight:finsight@127.0.0.1:5432/finsight \
  ./.venv/bin/python -m pytest -q \
  tests/auth/test_postgres_refresh.py \
  tests/scheduler/test_postgres_control_plane.py \
  tests/test_postgres_history_recovery.py \
  tests/test_postgres_idempotency.py \
  tests/test_postgres_incremental_ingestion.py
./.venv/bin/ruff check .
./.venv/bin/python -m compileall -q app config tests

cd ../frontend
npm test -- --run
npm run lint
npx tsc --noEmit
npm run build
E2E_BASE_URL=http://127.0.0.1:3000 \
E2E_API_URL=http://127.0.0.1:8000 npx playwright test
```

The auth browser suite covers registration, password login, direct routes,
pre-opened and duplicated tabs, cross-tab login/logout, hard reload, refresh
rotation after access loss, invalid-session recovery, and OAuth-denial UX.
Backend tests cover provider exchange/verification/linking/conflicts, expired and
replayed sessions, CSRF, failure limiting, recovery expiry/replay, and ownership.
A real Google consent and delivered Resend email remain production checks because
they require operator-owned provider credentials.
