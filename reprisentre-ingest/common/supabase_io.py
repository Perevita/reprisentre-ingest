import logging
from typing import List, Optional

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
    Upserts into `listings` keyed by canonical_key = '{source_name}:{external_ref}'.
    Also writes a row into `listing_sources` for provenance.
    Schema assumed:
      listings(canonical_key UNIQUE, title, region, revenue_eur, asking_price_eur,
               source_url, source_primary, last_seen_active_at, raw_data jsonb, ...)
      listing_sources(listing_id, source_name, external_ref UNIQUE w/ source_name,
                      source_url, last_seen_at, content_hash)
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
            "raw_data": l.to_dict(),
        })

    logging.info(f"Upserting {len(listings_payload)} rows into listings")
    res = sb.table("listings").upsert(
        listings_payload, on_conflict="canonical_key"
    ).execute()

    # Map canonical_key -> listing.id so we can write provenance rows.
    keys = [r["canonical_key"] for r in listings_payload]
    rows = sb.table("listings").select("id, canonical_key").in_("canonical_key", keys).execute()
    id_by_key = {r["canonical_key"]: r["id"] for r in (rows.data or [])}

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


def log_scrape_run(
    source_name: str,
    started_at: str,
    finished_at: str,
    status: str,
    listings_found: int,
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
            "error_message": error_message,
        }).execute()
    except Exception as e:
        logging.warning(f"Could not log scrape run (table may not exist): {e}")
