# reprisentre-ingest

Daily scrapers that index public French SME-for-sale sources into the
Reprisentre Supabase database.

## Layout

```
main.py             # orchestrator, picks a source by CLI arg / SOURCE env var
common/             # shared model, http client, parsing helpers, Supabase upsert
sources/cra.py      # CRA list-page indexer
```

## Run locally

```bash
pip install -e .
DRY_RUN=true MAX_PAGES=1 python main.py cra
```

DRY_RUN prints JSON to stdout instead of writing to Supabase.

## Run against the database

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
DRY_RUN=false python main.py cra
```

## Add a new source

1. Create `sources/foo.py` exporting `scrape() -> list[Listing]`.
2. Register it in `main.py`:
   ```python
   from sources import foo
   SOURCES = {"cra": cra.scrape, "foo": foo.scrape}
   ```
3. Add a Railway service that runs `python main.py foo` on a daily cron.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `SUPABASE_URL` | — | Required for DB writes |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Required for DB writes |
| `DRY_RUN` | `true` | When true, prints JSON instead of upserting |
| `REQUEST_DELAY_SECONDS` | `1.0` | Sleep between page fetches |
| `MAX_PAGES` | unset | Cap pages scraped (smoke tests) |
| `SOURCE` | `cra` | Default source if no CLI arg given |
| `USER_AGENT` | Reprisentre UA | HTTP User-Agent header |

## Database expectations

The upsert writes to two tables that already exist in the Reprisentre
Supabase project:

- `listings` — keyed by `canonical_key = '{source_name}:{external_ref}'`
- `listing_sources` — keyed by `(source_name, external_ref)` for provenance

A `scrape_runs` table is optional; if absent, run logging is skipped silently.
