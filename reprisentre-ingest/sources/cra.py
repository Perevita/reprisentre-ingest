"""
CRA (https://www.cra.asso.fr) list-page indexer.

Scrapes the public /liste-entreprises-a-reprendre.aspx?page=N pages and
captures one Listing per card. The card's stable id is the N° number,
which also forms the detail URL: /opportunite-reprise.aspx?num={ref}.

We do NOT visit detail pages here. Status (vendu / sous LOI), employees,
EBE, etc. belong to a separate enrichment pass.
"""

import logging
import re
import time
from typing import Iterator, List

from bs4 import BeautifulSoup

from common import http
from common.config import REQUEST_DELAY_SECONDS, MAX_PAGES
from common.models import Listing
from common.parse import clean_text, extract_after, now_utc, parse_euro_amount

SOURCE_NAME = "cra"
BASE = "https://www.cra.asso.fr"
LIST_URL = BASE + "/liste-entreprises-a-reprendre.aspx?page={page}"
DETAIL_URL = BASE + "/opportunite-reprise.aspx?num={ref}"

DETAIL_HREF_RE = re.compile(r"opportunite-reprise\.aspx\?num=(\d+)", re.IGNORECASE)
NUM_RE = re.compile(r"N°\s*(\d+)")


def scrape() -> List[Listing]:
    listings: dict[str, Listing] = {}

    with http.client() as c:
        first_html = http.get(c, LIST_URL.format(page=1))
        total = _detect_total_pages(first_html)
        if MAX_PAGES is not None:
            total = min(total, MAX_PAGES)
        logging.info(f"CRA: scraping {total} page(s)")

        for page in range(1, total + 1):
            html = first_html if page == 1 else http.get(c, LIST_URL.format(page=page))
            count = 0
            for listing in _parse_cards(html, page):
                listings[listing.external_ref] = listing
                count += 1
            logging.info(f"CRA page {page}: {count} listings")
            if page < total:
                time.sleep(REQUEST_DELAY_SECONDS)

    return list(listings.values())


def _detect_total_pages(html: str) -> int:
    """Find the highest page number in the pager (e.g. '... 13')."""
    soup = BeautifulSoup(html, "html.parser")
    nums: list[int] = []

    # Any link or text mentioning ?page=N
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]page=(\d+)", a["href"])
        if m:
            nums.append(int(m.group(1)))

    # Fallback: pager text "... 13"
    text = soup.get_text(" ", strip=True)
    for m in re.finditer(r"\.\.\.\s*(\d+)", text):
        nums.append(int(m.group(1)))

    return max(nums) if nums else 1


def _parse_cards(html: str, page: int) -> Iterator[Listing]:
    """
    Yield one Listing per card on the page.

    Strategy: find every detail link (opportunite-reprise.aspx?num=...).
    Each unique link corresponds to one card. Walk up to a reasonable
    container and pull title / region / CA / Valeur demandée from its text.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_url = LIST_URL.format(page=page)
    seen: set[str] = set()
    now = now_utc()

    for a in soup.find_all("a", href=DETAIL_HREF_RE):
        m = DETAIL_HREF_RE.search(a["href"])
        if not m:
            continue
        ref = m.group(1)
        if ref in seen:
            continue
        seen.add(ref)

        # Use the closest meaningful ancestor as the card container.
        card = a.find_parent(["li", "article", "div"]) or a
        text = clean_text(card.get_text(" ", strip=True)) or ""

        yield Listing(
            source_name=SOURCE_NAME,
            external_ref=ref,
            source_url=DETAIL_URL.format(ref=ref),
            source_page_url=page_url,
            title=_extract_title(card, text),
            region=_extract_region(text),
            revenue_eur=parse_euro_amount(extract_after(text, "CA :")),
            asking_price_eur=parse_euro_amount(extract_after(text, "Valeur demandée")),
            raw_text=text,
            last_seen_at=now,
        )


def _extract_title(card, text: str) -> str | None:
    """
    The title is typically the first non-empty line of the card, before
    'CA :' / 'Valeur demandée' / 'N°' markers.
    """
    # Try the link text first; CRA often wraps the title in the detail link.
    link_text = clean_text(card.get_text(" ", strip=True))
    if not link_text:
        return None
    # Strip everything from the first field marker onwards.
    cut = len(link_text)
    for marker in ["CA :", "Valeur demand", "N°"]:
        i = link_text.find(marker)
        if i != -1 and i < cut:
            cut = i
    head = clean_text(link_text[:cut])
    if not head:
        return None
    # The region often appears doubled before the title; trim it.
    region = _extract_region(text)
    if region and head.startswith(region + " "):
        head = head[len(region) + 1:]
    return head[:300]


REGION_HINT = re.compile(
    r"(Auvergne-Rhône-Alpes|Bourgogne-Franche-Comté|Bretagne|Centre-Val de Loire|"
    r"Corse|Grand Est|Hauts-de-France|Île-de-France|Ile-de-France|Normandie|"
    r"Nouvelle-Aquitaine|Occitanie|Pays de la Loire|Provence-Alpes-Côte d'Azur|"
    r"Guadeloupe|Martinique|Guyane|La Réunion|Mayotte)"
)


def _extract_region(text: str) -> str | None:
    """
    Best-effort region extraction. CRA cards include the region as a plain
    string in the card text. We use a permissive hint regex but fall back
    to None rather than guessing — region is nice-to-have, not required.
    """
    m = REGION_HINT.search(text)
    if not m:
        return None
    val = m.group(1)
    return "Île-de-France" if val == "Ile-de-France" else val
