# News + Sentiment (Phase 5)

Ingest financial news, score sentiment, tag it to tracked companies, aggregate
daily sentiment, and **feed real sentiment into Phase 4's feature vector** —
closing the placeholder left there. Sentiment is a *deterministic classification
input* ("analytics before AI"); the LLM never scores it.

## Pipeline

```
RSS feeds → dedupe → sentiment score → company tag → aggregate (daily/stock) → history feature vector
```

Wired into the post-close scheduler pipeline: **market ingest → news ingest →
history rebuild**, so sentiment refreshes and the similarity index picks it up.

### 1. News source (`shared/clients/news_client.py`)

Free Indian financial-news **RSS** feeds (Economic Times, Moneycontrol, Business
Standard, LiveMint — configurable), parsed with `feedparser` behind a
provider-agnostic `NewsClient` interface (tests inject a fake, no network). A bad
feed is skipped, never fatal.

**Dedupe** is two-layer: by URL (unique constraint) and by normalized title
within a batch (the same story from two feeds → stored once, so aggregation isn't
double-counted).

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

Pure, whole-word (token) matching of stock aliases (ticker base + name tokens)
against the article. False-positive guards (the roadmap's noted risk):
- aliases shorter than 3 chars are dropped (short tickers colliding with words);
- generic tokens (`LTD`, `BANK`, `SERVICES`, …) are dropped;
- **conglomerate group prefixes** (`TATA`, `ADANI`, `BAJAJ`, …) are dropped — they
  span many listed entities, so matching on them over-tags (e.g. "Tata Power"
  would wrongly tag TCS). Match on the company-specific token instead
  (`CONSULTANCY` for TCS). *This exact bug was caught in live testing and fixed.*

Tagging is best-effort and imperfect by nature (documented limitation).

### 4. Aggregation (`news/service.py`)

`sentiment_daily` = per stock, per day: average article sentiment + positive/
negative/neutral counts, recomputed idempotently from all tagged articles. This
is the read surface consumed by the history module.

## Closing the Phase 4 loop

`history/feature_engineering.py`'s `avg_sentiment` feature is no longer a constant
placeholder: `StockDay` carries a `sentiment` value, and the history service
loads `sentiment_daily` and attaches per-stock sentiment per date. Dates with no
news get a neutral `0.0` (zero variance → no effect); dates with news get real,
varying values that contribute to similarity. **Verified end-to-end**: a session's
`avg_sentiment` moved from `0.0` to the injected value after a sentiment row was
added for that date and the index rebuilt.

## Data model (migration `0006_news`)

- **news_articles** — deduped article (unique `url`) + sentiment scores.
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
| `POST /api/v1/admin/jobs/news-ingestion/run` | Ingest + score + tag + aggregate (administrator only) |

## Verification

- **Unit**: lexicon scorer ranges/bounds + FinBERT fallback; tagging (aliases,
  whole-word, group-prefix guard, no false positives); RSS client (mocked
  feedparser: extraction, dedupe, bad-feed).
- **Integration**: fake feed → ingest → score → tag → aggregate; **a bad-news day
  yields negative aggregate sentiment** (DoD); re-ingest dedupes; multi-article
  averaging.
- **Live**: 100 real RSS articles ingested; correct tags after the group-prefix
  fix (only genuine mentions tag); FinBERT verified; Phase 4 loop closure proven.

~94% coverage across news modules (FinBERT internals excluded — verified live,
not loaded in unit tests).

## Known limitations

- Company-specific news for a small universe is sparse in general market feeds;
  tagging yields few hits per fetch (expected).
- Cross-run near-duplicate stories (same story, new URL next day) may recur;
  within-batch title dedupe handles the common case.
