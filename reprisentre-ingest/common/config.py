import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
MAX_PAGES = int(os.getenv("MAX_PAGES")) if os.getenv("MAX_PAGES") else None

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (compatible; ReprisentreIndexer/0.1; +https://reprisentre.com)",
)
