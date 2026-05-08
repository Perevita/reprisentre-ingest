import logging
import httpx

from .config import USER_AGENT


def client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        },
        timeout=30.0,
        follow_redirects=True,
    )


def get(c: httpx.Client, url: str) -> str:
    logging.info(f"GET {url}")
    r = c.get(url)
    r.raise_for_status()
    return r.text
