# v1.0 Production-Readiness Evidence

This log records current-state evidence for the ordered v1.0 campaign. A later
phase is not started until the preceding phase's exit criteria are proven.

## Part 1 — Production news and sentiment

### Read-only production diagnosis (2026-08-23)

The deployed Render API and database health endpoints returned HTTP 200. Public
aggregate reads established:

- 50 active equities;
- 0 persisted articles returned (the endpoint limit was 200);
- 0 linked articles, associations, or distinct linked equities;
- 50 latest-sentiment records, all with `null` values;
- 0 equities with sentiment data; therefore the persisted positive, neutral,
  and negative article distributions were all zero;
- no news-ingestion or sentiment timestamp exists when their tables are empty.

The displayed `0 positive / 50 neutral / 0 negative` was therefore not evidence
of neutral coverage. It combined an empty production news store with a frontend
reducer that counted `null` as neutral.

Authenticated GitHub Actions logs later established why the news store remained
empty: on 2026-08-21 the market step successfully ingested 18 of 19 configured
symbols, but Yahoo returned 404 for retired `TATAMOTORS.NS`. Strict market-step
semantics correctly stopped the pipeline before news. Phase 10C subsequently
deployed the validated replacement `TMPV.NS`; a read-only readiness probe for
the 2026-08-21 session now returns `ready`.

### Source and linker audit

On the same date, the four configured public RSS sources returned 100 real
articles (three sources supplied entries and one supplied none). All 100 had
publication timestamps and the latest was `2026-08-23T10:13:15Z`.

The old token linker associated 32 articles to 18 equities but inspection found
material false positives, including generic `OIL`, `LIFE`, and `TECH` matches.
The corrected phrase linker associated 12 articles through 20 plausible links
to 13 equities. The deterministic lexicon distribution for those linked
articles was 8 positive, 2 neutral, and 2 negative. URL/date fingerprinting
continues to collapse cross-feed copies during ingestion.

### Changes and regression evidence

- reviewed phrase aliases plus dynamic ticker/full-name fallbacks;
- normal-ingestion reconciliation of recent deduped article tags, including
  removal of orphaned derived sentiment without deleting source articles;
- generic-token and shared-brand regression tests;
- recent sentiment bounded to the latest market session window;
- admin-only aggregate diagnostics with counts and timestamps;
- Overview unavailable state and separate mixed-coverage count;
- targeted news, dashboard API, intelligence, and frontend component tests.

### Scheduled refresh observation (2026-08-24)

Both regular GitHub Actions EOD attempts completed successfully on deployed
commit `fcc0ff2` (runs `32723382503` and `32736400811`). The later run completed
all automatic EOD steps in 36 seconds. Public read endpoints subsequently
reported:

- 98 real persisted articles: 85 dated 2026-08-24 and 13 older feed entries;
- article sentiment distribution: 51 positive, 34 neutral, 13 negative;
- 35 tagged articles, 63 untagged articles, and 59 stock associations;
- 24 of 50 active equities with a latest sentiment value and 26 unavailable;
- stock-level distribution among the 24 observed values: 14 positive,
  6 neutral, and 4 negative.

This proves that the normal scheduled path can fetch, score, persist, and
aggregate current news after the retired-symbol blocker was removed. It does
**not** sign off tagging correctness: `fcc0ff2` predates the phrase-linker and
reconciliation fixes, and the live associations still contain the audited
generic-token false positives. A deployment and one normal post-deployment EOD
run are required to reconcile those persisted links before Part 1 passes.

### Final exit evidence

Part 1 was signed off on 2026-08-24 after the corrected production path ran on
the `QA` branch. The final evidence is:

- production refresh run `32745789099` completed successfully on `ec178fb`;
- the final idempotent pass fetched 100 feed entries, inserted no duplicates,
  reconciled one remaining shared-brand collision, removed one association,
  and recomputed 18 stock/day sentiment aggregates;
- 115 total persisted articles, of which 102 were in the seven-day publication
  window; replayed 2024 feed entries no longer appear as current news;
- 12 linked articles, 22 associations, and 18 distinct active stocks with links
  across the persisted corpus;
- the current public feed contained 8 linked articles, 18 manually audited
  plausible associations across 14 equities, with source URLs preserved;
- current article distribution: 49 positive, 37 neutral, 16 negative;
- current stock-level distribution: 8 positive, 6 neutral, 0 negative, and 36
  explicitly unavailable. Zero negative stock aggregates is the observed
  result, not a substitute for missing coverage;
- latest article ingestion: `2026-08-24T15:14:29.756981Z`;
- latest sentiment aggregation: `2026-08-24T15:36:05.437909Z`;
- CI succeeded on final Part 1 revision `6d6cc7d`; Render and Vercel both
  reported successful deployments for that exact revision;
- the canonical frontend and `/dashboard` returned HTTP 200, and the deployed
  dashboard artifact contains the `No recent sentiment` and `unavailable`
  states covered by the frontend regression tests.

Normal scheduled EOD behavior remains unchanged. A manual `news-only`
operation now provides an authenticated, fail-closed maintenance path when the
durable EOD session is already complete; it cannot accept a historical target
date and therefore cannot perform a fake backfill.

Part 1 is complete. Phase 10E may begin.
