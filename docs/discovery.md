# Discovery and Research Workflow

Discovery turns constrained natural language into deterministic research
screens. A language model never chooses securities or generates SQL.

`POST /api/v1/discovery/screen` parses text into the versioned
`screener_ast_v1` contract. Only enumerated universes, fields, operators, and
values are accepted; unsupported requests fail with
`422 unsupported_screener_query` and the supported field list. Filters cover
NIFTY 50, NIFTY Next 50 and NIFTY 100 membership, sector, daily change, RSI,
EMA relationships, MACD, relative volume, P/E, positive EPS, recent news
sentiment, signal state, and current-regime alignment. Missing values never
satisfy conditions.

The executor reads approved membership and batched market, fundamental,
relative-volume and recent-sentiment data. It evaluates the AST in Python and
returns interpreted conditions plus a SHA-256 hash of the canonical AST and
sorted observations. Identical stored inputs therefore produce identical
ordering and hashes.

Migration `0019_saved_screens` stores the original text and validated AST in a
user-owned record. Creation reparses the text and rejects AST tampering. List,
replay, and delete are ownership-scoped and return 404 for other users:

- `POST /api/v1/discovery/screens`
- `GET /api/v1/discovery/screens`
- `POST /api/v1/discovery/screens/{id}/run`
- `DELETE /api/v1/discovery/screens/{id}`

The responsive `/discover` page exposes interpreted filters, reproducibility
hashes, results and saved-screen actions. Stock, portfolio and news pages can
open `/chat` with a visible contextual question; the authenticated assistant's
normal evidence pipeline remains authoritative. Historical Similarity also
supports selecting an analogue to inspect grouped matches, divergences,
one-/five-session outcomes, drawdown, coverage and model metadata.

Tests cover parsing, unsupported fields, deterministic hashes, filtering,
tamper rejection, replay, ownership, saved-screen interactions, and encoded
contextual research links.
