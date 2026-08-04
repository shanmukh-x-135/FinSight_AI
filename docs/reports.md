# Reports & export (Phase 8)

Turns Phase 6's structured report data into a browsable, filterable, exportable
Reports experience. Nothing new is *generated* here — generation stays in the
intelligence pipeline (`app/intelligence/`); this module (`app/reports/`) owns
the browse → open → export workflow and reuses Phase 6's `reports` table
unchanged (no migration).

## Report structure

A report is stored as **structured JSONB `sections`** (design doc §6.2), not a
rendered document. Markdown/PDF are produced **on demand** — never stored
redundantly. Section keys (optional ones appear only when relevant):

| Section | Notes |
|---------|-------|
| `executive_summary` | Prose synthesis (string). |
| `market_summary` | `narrative`, `breadth`, `gainers`, `losers`. |
| `portfolio_summary` | *(optional)* narrative + value/return/health/risk/diversification/holdings. Present only if the user has a portfolio. |
| `historical_summary` | *(optional)* narrative + `statistics` + `similar_sessions`. Present only if the FAISS index is built. |
| `recommendations` | Watch-rated picks — each with `evidence`, `risks`, `confidence`, `historical_context`, `explanation`. |
| `risk_alerts` | Avoid-rated, same shape. |
| `news` | `notable[]` (title, sentiment, tags). |
| `meta` | `prompt_version`, `llm_backend`, `generated_at`. |

Rankings, evidence, confidence, and risks are all deterministic (Phase 6); the
LLM only writes the prose. Exports are therefore reproducible.

## Endpoints (`/api/v1`, auth-protected)

| Endpoint | Purpose |
|----------|---------|
| `POST /reports/generate` | Generate + store a report (delegates to the intelligence pipeline). |
| `GET /reports` | List your reports — filterable + paginated (see params). |
| `GET /reports/{id}` | Report detail. Ownership-scoped: a user-scoped report is 404 to others. |
| `GET /reports/{id}/export?format=markdown\|pdf` | Export on demand — returns a downloadable file (not the JSON envelope). |

A user sees their own reports plus global (user-less) market reports.

### Filter & pagination parameters (`GET /reports`)

| Param | Type | Default | Meaning |
|-------|------|---------|---------|
| `report_type` | string | — | Exact match (e.g. `daily`). |
| `start_date` | date (`YYYY-MM-DD`) | — | Created on/after (00:00 UTC). |
| `end_date` | date | — | Created on/before (inclusive of the whole day). |
| `limit` | int 1–100 | 20 | Page size. |
| `offset` | int ≥0 | 0 | Rows to skip. |

Results are ordered newest-first (`created_at desc, id desc`). `data` is the
page as a plain list; the frontend advances by `offset` and stops when a page
returns fewer than `limit` rows.

## Export pipeline

**Markdown is the single source of truth; PDF is rendered from that Markdown**,
so the two formats can never drift (roadmap refactor guidance).

```
stored sections → render_markdown() → Markdown  ─┬─→  .md  (text/markdown)
                                                 └─→ render_pdf() → .pdf (application/pdf)
```

- `app/reports/exporters/markdown.py` — pure, deterministic layout of the
  sections in reading order. Optional sections are simply skipped when absent.
- `app/reports/exporters/pdf.py` — renders the Markdown with **fpdf2** (pure
  Python, no system libraries, so the base image stays light — same
  light-default pattern as FinBERT/Gemini/Plotly). Supports a Markdown subset:
  `#`/`##`/`###` headings, `-` bullets, `**bold**`, paragraph breaks.

### Robustness (the roadmap's PDF edge cases)

fpdf2's core fonts are latin-1 only, so any Unicode the LLM might emit is
**sanitized** before writing — em/en dashes, curly quotes, `₹` (→ `Rs.`),
arrows, ellipses map to safe equivalents, and anything still unrepresentable is
replaced (never crashes). Long text wraps via `multi_cell` (with the cursor
reset to the left margin each block); missing optional sections just don't
appear. All three cases are covered by tests.

## Frontend

- `/reports` (list) — date/type filters, a **Generate report** button, and
  prev/next pagination.
- `/reports/{id}` (detail) — the **Report page template**: Executive Summary →
  Analysis (market/portfolio/historical) → Recommendations (each with the same
  **Show Evidence** expander from Phase 7) → Appendix (news). **Export
  Markdown / Export PDF** buttons stream the file with the Bearer token via a
  blob download, so the exported content matches what's on screen.

## Tests

- **API:** auth, type filter, date filter, pagination (multi-page, no overlap),
  detail, ownership 404 (`tests/reports/test_reports_api.py`).
- **Export:** Markdown contains every section / skips missing ones / handles
  empty recommendations; PDF renders for the happy path, **unusually long
  text**, **special/Unicode characters**, and **missing sections**; the export
  endpoints return the right content-type/disposition and reject unknown
  formats (`tests/reports/test_export.py`).
- Live-verified against the Docker stack: generated a real report, listed +
  filtered it, and exported valid Markdown and a valid PDF (`%PDF`, ~4 KB).
