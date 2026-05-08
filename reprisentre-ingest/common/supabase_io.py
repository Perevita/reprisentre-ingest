import logging
from typing import Iterable, List, Optional

from .config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from .models import Listing

try:
    from supabase import create_client
except ImportError:
    create_client = None


def _client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    if create_client is None:
        raise RuntimeError("Missing dependency: supabase. pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def upsert_listings(listings: List[Listing]) -> None:
    """
    Upsert into `listings` keyed by canonical_key = '{source_name}:{external_ref}'.
    Existing rows with the same canonical_key are UPDATED (not duplicated),
    and any row whose status was previously 'unavailable' is reactivated to
    'active' because we just saw it again.

    Also writes a provenance row into `listing_sources`.
    """
    sb = _client()
    if sb is None:
        logging.warning("Supabase env not set; skipping upsert.")
        return
    if not listings:
        logging.info("No listings to upsert.")
        return

    listings_payload = []
    for l in listings:
        listings_payload.append({
            "canonical_key": f"{l.source_name}:{l.external_ref}",
            "title": l.title or "(untitled)",
            "region": l.region,
            "revenue_eur": l.revenue_eur,
            "asking_price_eur": l.asking_price_eur,
            "source_primary": l.source_name,
            "source_url": l.source_url,
            "last_seen_active_at": l.last_seen_at,
            "last_checked_at": l.last_seen_at,
            "status": "active",
            "status_reason": None,
            "raw_data": l.to_dict(),
        })

    logging.info(f"Upserting {len(listings_payload)} rows into listings")
    sb.table("listings").upsert(
        listings_payload, on_conflict="canonical_key"
    ).execute()

    # Map canonical_key -> id for provenance.
    keys = [r["canonical_key"] for r in listings_payload]
    id_by_key: dict[str, str] = {}
    for chunk in _chunks(keys, 200):
        rows = sb.table("listings").select("id, canonical_key").in_("canonical_key", chunk).execute()
        for r in (rows.data or []):
            id_by_key[r["canonical_key"]] = r["id"]

    sources_payload = []
    for l in listings:
        listing_id = id_by_key.get(f"{l.source_name}:{l.external_ref}")
        if not listing_id:
            continue
        sources_payload.append({
            "listing_id": listing_id,
            "source_name": l.source_name,
            "external_ref": l.external_ref,
            "source_url": l.source_url,
            "last_seen_at": l.last_seen_at,
        })

    if sources_payload:
        sb.table("listing_sources").upsert(
            sources_payload, on_conflict="source_name,external_ref"
        ).execute()

    logging.info("Upsert complete")


def mark_unavailable(source_name: str, seen_keys: Iterable[str]) -> int:
    """
    Flip rows for this source that we did NOT see this run from 'active' to
    'unavailable'. Returns the number of rows flipped (best effort).

    The caller is responsible for only invoking this after a HEALTHY full run
    (see main.py guard) — otherwise a partial scrape would mass-mark live
    listings as gone.
    """
    sb = _client()
    if sb is None:
        return 0

    seen = list(seen_keys)
    if not seen:
        logging.warning(f"[{source_name}] mark_unavailable called with empty seen set; refusing")
        return 0

    # Pull the active rows we DO have for this source, filter client-side
    # against `seen`, then update by id. This avoids the URL-length limit
    # of `not_.in_(huge_list)`.
    existing = sb.table("listings").select("id, canonical_key").eq(
        "source_primary", source_name
    ).eq("status", "active").execute()

    seen_set = set(seen)
    missing_ids = [
        r["id"] for r in (existing.data or [])
        if r["canonical_key"] not in seen_set
    ]

    if not missing_ids:
        logging.info(f"[{source_name}] no listings to mark unavailable")
        return 0

    flipped = 0
    for chunk in _chunks(missing_ids, 200):
        sb.table("listings").update({
            "status": "unavailable",
            "status_reason": "not_listed_on_source",
        }).in_("id", chunk).execute()
        flipped += len(chunk)

    logging.info(f"[{source_name}] marked {flipped} listings as unavailable")
    return flipped


def log_scrape_run(
    source_name: str,
    started_at: str,
    finished_at: str,
    status: str,
    listings_found: int,
    pages_scraped: int = 0,
    error_message: Optional[str] = None,
) -> None:
    sb = _client()
    if sb is None:
        return
    try:
        sb.table("scrape_runs").insert({
            "source_name": source_name,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "listings_found": listings_found,
            "pages_scraped": pages_scraped,
            "error_message": error_message,
        }).execute()
    except Exception as e:
        logging.warning(f"Could not log scrape run (table may not exist): {e}")


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]
