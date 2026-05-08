from typing import Callable, List, Tuple
from common.models import Listing

# A source returns (listings, pages_scraped, expected_pages).
# pages_scraped < expected_pages signals a partial run; the orchestrator
# uses this to decide whether to flag missing rows as unavailable.
ScrapeFn = Callable[[], Tuple[List[Listing], int, int]]
