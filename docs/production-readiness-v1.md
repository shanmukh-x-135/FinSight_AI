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

### Remaining exit evidence

The normal production news/sentiment path must still be invoked and its
post-run counts verified after these changes are deployed. This is an operator
action: repository policy forbids an automatic push. Part 1 is not signed off
and Phase 10E has not started.
