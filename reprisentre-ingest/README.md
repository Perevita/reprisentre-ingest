# reprisentre-ingest

Daily scrapers that index public French SME-for-sale sources into the
Reprisentre Supabase database.

## Layout

```
main.py                # orchestrator: picks source(s), runs them, sweeps
common/
  models.py            # Listing dataclass
  http.py              # httpx client + GET helper
  parse.py             # text/euro/date helpers
  supabase_io.py       # upsert + mark-unavailable + run logging
  config.py            # env vars
sources/
  base.py              # ScrapeFn type
  cra.py               # CRA list-page scraper
  fusacq.py            # placeholder for future source
```

## Run locally

```bash
pip install -e .
DRY_RUN=true MAX_PAGES=1 python main.py cra
```

`DRY_RUN=true` prints JSON to stdout instead of writing to Supabase.

## Run against the database

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
DRY_RUN=false python main.py cra
```

## Add a new source

1. Create `sources/foo.py` exporting
   `scrape() -> tuple[list[Listing], int, int]`
   (returns `(listings, pages_scraped, expected_pages)`).
2. Register it in `main.py`:
   ```python
   from sources import foo
   SOURCES = {"cra": cra.scrape, "foo": foo.scrape}
   ```
3. Add a Railway cron service that runs `python main.py foo`.

## How dedup works

Every listing has a stable `canonical_key = "{source_name}:{external_ref}"`
(e.g. `cra:18643`). The DB has a unique index on `canonical_key`, and
`upsert_listings(...)` uses `on_conflict="canonical_key"`. So:

- New listing → inserted.
- Existing listing → updated in place (title, region, CA, asking price, etc.)
  and `last_seen_active_at` / `last_checked_at` set to now.
- `status` is forced back to `'active'` on every sighting (so a row that
  was previously flagged `'unavailable'` automatically reactivates if it
  comes back).

No duplicates can be created.

## How the unavailable sweep works

After a healthy full run we want to flip listings that are no longer on the
source (sold, withdrawn, signed LOI) to `status='unavailable'`.

`mark_unavailable(source_name, seen_keys)`:

1. Loads every row in `listings` where
   `source_primary = source_name AND status = 'active'`.
2. Diffs against `seen_keys` (the canonical_keys we just scraped).
3. Updates the missing rows to
   `status='unavailable', status_reason='not_listed_on_source'`.

### Safety guard

`main.py` only calls the sweep when:

- `pages_scraped >= expected_pages` (no page failures), AND
- `len(listings) >= MIN_LISTINGS_FOR_SWEEP` (default 100).

A partial run logs a warning and skips the sweep so a single failed page
can never wipe out hundreds of live rows.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `SUPABASE_URL` | — | Required for DB writes |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Required for DB writes |
| `DRY_RUN` | `true` | When true, prints JSON instead of upserting |
| `REQUEST_DELAY_SECONDS` | `1.0` | Sleep between page fetches |
| `MAX_PAGES` | unset | Cap pages scraped (smoke tests only — leave unset in prod) |
| `MIN_LISTINGS_FOR_SWEEP` | `100` | Refuse to mark unavailable if fewer listings found |
| `SOURCE` | `cra` | Default source if no CLI arg given |
| `USER_AGENT` | Reprisentre UA | HTTP User-Agent header |

## Database expectations

Tables already exist in the Reprisentre Supabase project:

- `listings` — keyed by `canonical_key` (unique). Fields used: `title`,
  `region`, `revenue_eur`, `asking_price_eur`, `source_primary`,
  `source_url`, `last_seen_active_at`, `last_checked_at`, `status`,
  `status_reason`, `raw_data` (jsonb).
- `listing_sources` — keyed by `(source_name, external_ref)`.
- `scrape_runs` — optional. If absent, run logging is skipped silently.
  If present, fields used: `source_name`, `started_at`, `finished_at`,
  `status`, `listings_found`, `pages_scraped`, `error_message`.
