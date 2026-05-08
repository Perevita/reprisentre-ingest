from typing import Callable, List
from common.models import Listing

# A source is just a callable returning a list of Listing objects.
ScrapeFn = Callable[[], List[Listing]]
