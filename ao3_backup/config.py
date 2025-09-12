import os
from pathlib import Path

DB_URL = os.getenv("AO3_CRAWLER_DB_URL", "sqlite:///ao3_crawler.sqlite3")
STORE_ROOT = Path(os.getenv("AO3_STORE_ROOT", "./store")).resolve()

CLAIM_BATCH = int(os.getenv("AO3_CLAIM_BATCH", "50"))
PARALLELISM = int(os.getenv("AO3_PARALLELISM", "8"))

USER_AGENT = os.getenv("AO3_USER_AGENT", "ArchiveMirror/0.6 (+contact)")
GUEST_DELAY_S = float(os.getenv("AO3_GUEST_DELAY_S", "0.6"))
AUTH_DELAY_S = float(os.getenv("AO3_AUTH_DELAY_S", "1.5"))
JITTER_S = float(os.getenv("AO3_JITTER_S", "0.25"))

CREDENTIALS_FILE = Path(
    os.getenv("AO3_CREDENTIALS_FILE", "./credentials.json")
).resolve()
COOLDOWN_SECONDS = int(os.getenv("AO3_COOLDOWN_SECONDS", "900"))
