import os
from decimal import Decimal

BASE_URL = os.getenv("BVNK_BASE_URL", "https://qa-simulator.test.bvnk.com").rstrip("/")
PRESET_TOKEN = os.getenv("BVNK_TOKEN")
REQUEST_TIMEOUT = float(os.getenv("BVNK_TIMEOUT", "15"))

SERVICE_FEE_RATE = Decimal("0.0001")  # 0.01% per the task brief
SERVICE_FEE_PERCENT = SERVICE_FEE_RATE * 100  # as reported in fees.percentage.service
QUOTE_TTL_SECONDS = 20
EXPIRY_GRACE_SECONDS = 2        # extra wait past the TTL before asserting a quote has expired

# Polling for asynchronous settlement (observed: PROCESSING -> SUCCESS in ~6s)
SETTLEMENT_TIMEOUT = 60
SETTLEMENT_POLL_INTERVAL = 1
STATUS_POLL_INTERVAL = 0.25

WALLET_PAGE_SIZE = 100          # max_count used when walking the paginated wallet list
LOG_BODY_LIMIT = 300            # chars of response body written to the log
CONCURRENT_ACCEPT_WORKERS = 5
UNFUNDED_AMOUNT = 10 ** 9       # larger than any simulator balance
# Forex rates fluctuate, so we never assert against a hard-coded rate; we assert against the
# rate the quote itself reports. The API rounds prices to 8dp (see bvnk/tolerance.py):
PRICE_QUANTUM = Decimal("1e-8")
