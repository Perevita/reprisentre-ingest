"""
CRA (https://www.cra.asso.fr) list-page indexer.

Scrapes /liste-entreprises-a-reprendre.aspx?page=N and yields one Listing
per `<article class="presAF">` card. The card's stable id is the N° number,
which also forms the detail URL: /opportunite-reprise.aspx?num={ref}.

Detail pages (status, employees, EBE, etc.) are out of scope here — that
belongs to a separate enrichment pass.
"""

import logging
import re
import time
from typing import Iterator, List, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from common import http
from common.config import REQUEST_DELAY_SECONDS, MAX_PAGES
from common.models import Listing
from common.parse import clean_text, now_utc, parse_euro_amount

SOURCE_NAME = "cra"
BASE = "https://www.cra.asso.fr"
LIST_URL = BASE + "/liste-entreprises-a-reprendre.aspx?page={page}"
DETAIL_URL = BASE + "/opportunite-reprise.aspx?num={ref}"


def scrape() -> Tuple[List[Listing], int, int]:
    """Returns (listings, pages_scraped, expected_pages)."""
    listings: dict[str, Listing] = {}
    pages_scraped = 0

    with http.client() as c:
        first_html = http.get(c, LIST_URL.format(page=1))
        expected_pages = _detect_total_pages(first_html)
        target_pages = expected_pages
        if MAX_PAGES is not None:
            target_pages = min(target_pages, MAX_PAGES)
        logging.info(
            f"CRA: detected {expected_pages} page(s), scraping {target_pages}"
        )

        for page in range(1, target_pages + 1):
            try:
                html = (
                    first_html
                    if page == 1
                    else http.get(c, LIST_URL.format(page=page))
                )
            except Exception as e:
                logging.warning(f"CRA page {page} fetch failed: {e}")
                continue

            count = 0
            for listing in _parse_cards(html, page):
                listings[listing.external_ref] = listing
                count += 1
            pages_scraped += 1
            logging.info(f"CRA page {page}: {count} listings")

            if page < target_pages:
                time.sleep(REQUEST_DELAY_SECONDS)

    return list(listings.values()), pages_scraped, target_pages


def _detect_total_pages(html: str) -> int:
    """Highest page number referenced from the pager (e.g. '... 13')."""
    soup = BeautifulSoup(html, "html.parser")
    nums: list[int] = []

    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]page=(\d+)", a["href"])
        if m:
            nums.append(int(m.group(1)))

    return max(nums) if nums else 1


def _parse_cards(html: str, page: int) -> Iterator[Listing]:
    """
    Yield one Listing per <article class="presAF"> card.

    HTML shape (per card):
      <article class="presAF presAFn">
        <div class="imageAF"><a href="/opportunite-reprise.aspx?num=...">
          <picture><img src="..."></picture></a></div>
        <div class="texteAF">
          <p class="place">Région</p>
          <div class="result">
            <div class="res1">
              <p class="title"><a href="...">Title</a></p>
              <p class="price">CA : <b>X €</b><br>Valeur demandée : <b>Y €</b></p>
            </div>
            <div class="res2"><p class="identifier"> N°12345</p></div>
          </div>
        </div>
      </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    page_url = LIST_URL.format(page=page)
    now = now_utc()

    for article in soup.select("article.presAF"):
        title_p = article.select_one("div.texteAF p.title")
        title_a = title_p.find("a", href=True) if title_p else None
        if not title_a:
            continue

        href = title_a.get("href", "")
        ref = _extract_num(href)
        if not ref:
            continue

        # Title text often sits as a sibling text node next to an empty <a>,
        # so read the whole <p class="title"> rather than just the link.
        title = clean_text(title_p.get_text(" ", strip=True))
        place_el = article.select_one("div.texteAF p.place")
        region = clean_text(place_el.get_text(" ", strip=True)) if place_el else None

        revenue_eur = None
        asking_price_eur = None
        price_el = article.select_one("div.texteAF p.price")
        if price_el:
            bs = price_el.find_all("b")
            if len(bs) >= 1:
                revenue_eur = parse_euro_amount(bs[0].get_text(" ", strip=True))
            if len(bs) >= 2:
                asking_price_eur = parse_euro_amount(bs[1].get_text(" ", strip=True))

        img_el = article.select_one("div.imageAF picture img[src]")
        image_url = urljoin(BASE, img_el["src"]) if img_el and img_el.get("src") else None

        raw_text = clean_text(article.get_text(" ", strip=True)) or ""

        yield Listing(
            source_name=SOURCE_NAME,
            external_ref=ref,
            source_url=DETAIL_URL.format(ref=ref),
            source_page_url=page_url,
            title=title,
            region=_normalize_region(region),
            revenue_eur=revenue_eur,
            asking_price_eur=asking_price_eur,
            image_url=image_url,
            raw_text=raw_text,
            last_seen_at=now,
        )


def _extract_num(href: str) -> str | None:
    """Pull the `num=` query param out of a detail href."""
    try:
        qs = parse_qs(urlparse(href).query)
        nums = qs.get("num")
        if nums and nums[0].isdigit():
            return nums[0]
    except Exception:
        pass
    m = re.search(r"num=(\d+)", href)
    return m.group(1) if m else None


def _normalize_region(value: str | None) -> str | None:
    if not value:
        return None
    if value == "Ile-de-France":
        return "Île-de-France"
    return value
