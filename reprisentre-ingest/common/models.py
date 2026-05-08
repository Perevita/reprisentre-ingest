from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class Listing:
    source_name: str          # e.g. "cra"
    external_ref: str         # source-stable id, e.g. CRA "18595"
    source_url: str           # detail URL (derived from external_ref)
    source_page_url: str      # list page where it was found
    title: Optional[str]
    region: Optional[str]
    revenue_eur: Optional[int]
    asking_price_eur: Optional[int]
    raw_text: str
    last_seen_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
