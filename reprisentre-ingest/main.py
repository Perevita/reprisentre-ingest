"""
Reprisentre ingest orchestrator.

Usage:
    python main.py            # uses SOURCE env var, defaults to "cra"
    python main.py cra        # run a specific source
    python main.py all        # run every registered source

Env:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (required for DB write)
    DRY_RUN=true|false                       (default true: prints JSON instead of upserting)
    REQUEST_DELAY_SECONDS=1.0                (politeness between requests)
    MAX_PAGES=2                              (smoke-test cap; unset for full run)
    MIN_LISTINGS_FOR_SWEEP=100               (safety floor before flipping rows)
"""

import json
import logging
import os
import sys

from common.config import DRY_RUN
from common.parse import now_utc
from common.supabase_io import upsert_listings, mark_unavailable, log_scrape_run
from sources import cra

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# Add new sources here. Adding Fusacq later = `from sources import fusacq`
# and `"fusacq": fusacq.scrape`. No other changes needed.
SOURCES = {
    "cra": cra.scrape,
}

MIN_LISTINGS_FOR_SWEEP = int(os.getenv("MIN_LISTINGS_FOR_SWEEP", "100"))


def run_one(name: str) -> None:
    if name not in SOURCES:
        raise SystemExit(f"Unknown source: {name}. Known: {list(SOURCES)}")

    started = now_utc()
    pages_scraped = 0
    try:
        listings, pages_scraped, expected_pages = SOURCES[name]()
        logging.info(
            f"[{name}] {len(listings)} unique listings "
            f"(pages {pages_scraped}/{expected_pages})"
        )

        if DRY_RUN:
            print(json.dumps(
                [l.to_dict() for l in listings],
                ensure_ascii=False,
                indent=2,
            ))
        else:
            upsert_listings(listings)

            # Safety guard — only sweep when the run looks complete.
            healthy = (
                pages_scraped >= expected_pages
                and len(listings) >= MIN_LISTINGS_FOR_SWEEP
            )
            if healthy:
                seen = [f"{name}:{l.external_ref}" for l in listings]
                mark_unavailable(name, seen)
            else:
                logging.warning(
                    f"[{name}] partial run "
                    f"({pages_scraped}/{expected_pages} pages, "
                    f"{len(listings)} listings, floor {MIN_LISTINGS_FOR_SWEEP}) "
                    f"— skipping unavailable sweep"
                )

        log_scrape_run(name, started, now_utc(), "success", len(listings), pages_scraped)
    except Exception as e:
        log_scrape_run(name, started, now_utc(), "error", 0, pages_scraped, str(e))
        logging.exception(f"[{name}] failed")
        raise


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SOURCE", "cra")
    targets = list(SOURCES) if arg == "all" else [arg]
    for name in targets:
        run_one(name)


if __name__ == "__main__":
    main()
