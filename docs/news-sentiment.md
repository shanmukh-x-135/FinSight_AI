# News + Sentiment (Phase 5)

Ingest financial news, score sentiment, tag it to tracked companies, aggregate
daily sentiment, and **feed real sentiment into Phase 4's feature vector** —
closing the placeholder left there. Sentiment is a *deterministic classification
input* ("analytics before AI"); the LLM never scores it.

## Pipeline

```
RSS feeds → dedupe → sentiment score → company tag → aggregate (daily/stock) → history feature vector
```

Wired into the post-close EOD pipeline: **market ingest → news ingest → history
rebuild**, so sentiment refreshes and the similarity index picks it up.

If the durable EOD session is already complete, operators must not reopen or
weaken its idempotency ledger merely to refresh news. The existing EOD Actions
workflow exposes a manual `news-only` operation that runs
`python -m app.news.runner`: the same fetch, score, tag-reconciliation, and
aggregation service without market ingestion, fake backfill, or history
mutation. Supplying a target date with this operation fails closed.

### 1. News source (`shared/clients/news_client.py`)

Free Indian financial-news **RSS** feeds (Economic Times, Moneycontrol, Business
Standard, LiveMint — configurable), parsed with `feedparser` behind a
provider-agnostic `NewsClient` interface (tests inject a fake, no network). A bad
feed is skipped, never fatal.

**Dedupe** is database-backed: URL remains unique, and migration
`0010_write_idempotency` adds a unique SHA-256 story fingerprint derived from a
normalized title and publication date. It works across batches, process retries,
different feed URLs, and concurrent workers; the database atomically chooses the
winner. See [Write Idempotency](write-idempotency.md).

Deduplication does not freeze old company associations. Every normal ingestion
reconciles tags on articles from the last `NEWS_RETAG_WINDOW_DAYS` (30 by
default) against the current active universe and reviewed aliases. Incorrect
legacy links are removed, missing links are added, and derived daily sentiment
rows with no remaining source article are deleted. Articles and source URLs are
never removed by this repair path.

### 2. Sentiment scoring (`shared/ml/sentiment.py`)

One interface, two backends (compound score in [-1, 1] + per-class proportions):

| Backend | When | Notes |
|---------|------|-------|
| **FinBERT** (`ProsusAI/finbert`) | `SENTIMENT_BACKEND=finbert` | Design doc's model. Lazy-loaded, batched. Needs the ML extras (`requirements-ml.txt`). **Verified** on Python 3.13 (positive→+0.87, negative→−0.96, neutral→−0.01). |
| **Lexicon** | default | Dependency-free financial-sentiment lexicon. Fast, deterministic, no model download — keeps the base image light and tests offline. Automatic fallback if the ML stack is unavailable. |

**Design decision (like Phase 3's chart):** FinBERT is fully integrated,
verified, and selectable, but the *default/shipped* backend is the lexicon so the
image stays small and there's no runtime model-download failure mode. The
pipeline and the sentiment it feeds into Phase 4 are identical either way. Enable
FinBERT with `pip install -r requirements-ml.txt` and `SENTIMENT_BACKEND=finbert`.

### 3. Company tagging (`news/tagging.py`)

Pure, ordered whole-phrase matching uses the ticker, cleaned official company
name, and a reviewed set of common publisher names for current NIFTY 50
constituents. The official-name/ticker fallback continues to support future
dynamic-universe changes even before a shortened publisher name is reviewed.

The earlier 15-stock linker treated every company-name token as an alias. At 50
stocks that made generic words such as `OIL`, `LIFE`, `INSURANCE`, `PASS`, and
`TECH` produce false associations. Phrase matching now requires identities such
as `ONGC`, `HDFC LIFE`, or `TECH MAHINDRA`; shared group names such as `HDFC` and
`TATA` do not identify a company by themselves. Aliases shorter than three
characters and legal suffix-only names remain excluded.

Tagging is best-effort and imperfect by nature (documented limitation).

### 4. Aggregation (`news/service.py`)

`sentiment_daily` = per stock, per day: average article sentiment + positive/
negative/neutral counts, recomputed idempotently from all tagged articles. This
is the read surface consumed by the history module.

Universe-wide “latest sentiment” and RAG candidate sentiment are restricted to
`NEWS_RECENT_WINDOW_DAYS` (seven calendar days by default), anchored to the
latest canonical market session. A stock without a row in that window returns
`null`; it is not converted to neutral. Full historical series remain available
on the stock sentiment endpoint.

## Closing the Phase 4 loop

`history/feature_engineering.py`'s `avg_sentiment` feature is no longer a constant
placeholder: `StockDay` carries a `sentiment` value, and the history service
loads `sentiment_daily` and attaches per-stock sentiment per date. Dates with no
news get a neutral `0.0` (zero variance → no effect); dates with news get real,
varying values that contribute to similarity. **Verified end-to-end**: a session's
`avg_sentiment` moved from `0.0` to the injected value after a sentiment row was
added for that date and the index rebuilt.

## Data model (migrations `0006_news`, `0010_write_idempotency`)

- **news_articles** — deduped article (unique `url` and `fingerprint`) + sentiment scores.
- **news_article_stocks** — company tags (unique `(article_id, stock_id)`).
- **sentiment_daily** — per-stock, per-day aggregate (unique `(stock_id, date)`).
  Sector/day sentiment is derived on read as an article-count-weighted aggregate
  of these canonical stock rows, avoiding redundant stored totals.

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/news?limit=` | Recent articles with sentiment + tags |
| `GET /api/v1/news/sentiment/{symbol}` | Daily sentiment series for a stock |
| `GET /api/v1/news/sentiment/sector/{sector}` | Article-weighted daily sentiment for a sector |
| `GET /api/v1/admin/jobs/news-ingestion/status?recent_window_days=` | Aggregate counts and latest ingestion/sentiment timestamps, with no article content (administrator only) |
| `POST /api/v1/admin/jobs/news-ingestion/run` | Ingest + score + tag + aggregate (administrator only) |

## Verification

- **Unit**: lexicon scorer ranges/bounds + FinBERT fallback; tagging (aliases,
  whole-word, group-prefix guard, no false positives); RSS client (mocked
  feedparser: extraction, dedupe, bad-feed).
- **Integration**: fake feed → ingest → score → tag → aggregate; **a bad-news day
  yields negative aggregate sentiment** (DoD); re-ingest dedupes; multi-article
  averaging; recent deduped articles are retagged after alias corrections and
  orphaned derived sentiment is removed.
- **Production-readiness feed audit (2026-08-23)**: configured sources returned
  100 real current articles. The corrected linker found 12 relevant articles,
  20 plausible stock associations across 13 active equities; deterministic
  classification of the tagged set produced 8 positive, 2 neutral, and 2
  negative articles. These are provider-input audit numbers, not claims that the
  rows had already been persisted to production.
- **Missing-data UI**: the Overview renders a compact unavailable state when no
  active stock has recent sentiment. Mixed coverage reports the unavailable
  stock count separately from observed neutral scores.

~94% coverage across news modules (FinBERT internals excluded — verified live,
not loaded in unit tests).

## Known limitations

- Company-specific news for a small universe is sparse in general market feeds;
  tagging yields few hits per fetch (expected).
- Publisher aliases are deterministic and reviewed. A newly added constituent
  can match by ticker or full official name immediately, but a publisher-specific
  shortened brand may require an alias addition with a regression test.
- Fingerprinting intentionally uses exact normalized headlines rather than fuzzy
  semantic matching; materially rewritten headlines can remain distinct.
