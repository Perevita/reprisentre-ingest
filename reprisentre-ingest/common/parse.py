import re
from datetime import datetime, timezone
from typing import Optional


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def parse_euro_amount(value: Optional[str]) -> Optional[int]:
    """Parse strings like '597 686 €' into 597686. Returns None for unknown values."""
    if not value:
        return None
    lowered = value.lower()
    if "inconnue" in lowered or "non communiqu" in lowered:
        return None
    digits = re.findall(r"\d+", value.replace("\xa0", " "))
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def extract_after(text: str, label: str) -> Optional[str]:
    """Return the text fragment immediately after `label` up to the next field marker."""
    idx = text.lower().find(label.lower())
    if idx == -1:
        return None
    rest = text[idx + len(label):].strip(" :")
    # Stop at the next known field marker
    stoppers = ["CA :", "Valeur demand", "N°"]
    cut = len(rest)
    for s in stoppers:
        j = rest.find(s)
        if j != -1 and j < cut and j > 0:
            cut = j
    return clean_text(rest[:cut])
