import logging
from decimal import Decimal
from typing import Dict, List

from bvnk import config
from bvnk.client import ApiClient
from bvnk.schemas import Wallet

log = logging.getLogger("bvnk.wallets")


def list_wallets_raw(client: ApiClient, **kw):
    return client.get("/api/wallet", **kw)


def list_wallets(client: ApiClient, page_size: int = config.WALLET_PAGE_SIZE) -> List[Wallet]:
    """All wallets (the endpoint paginates with offset/max_count, default 10)."""
    out, offset = [], 0
    while True:
        resp = list_wallets_raw(client, params={"offset": offset, "max_count": page_size})
        resp.raise_for_status()
        page = resp.json()
        out += [Wallet.parse(w) for w in page]
        if len(page) < page_size:
            return out
        offset += page_size


def get_wallet_raw(client: ApiClient, wallet_id, **kw):
    return client.get(f"/api/wallet/{wallet_id}", **kw)


def get_wallet(client: ApiClient, wallet_id: int) -> Wallet:
    resp = get_wallet_raw(client, wallet_id)
    resp.raise_for_status()
    return Wallet.parse(resp.json())


def balances(client: ApiClient) -> Dict[str, Decimal]:
    """currency code -> balance snapshot."""
    snapshot = {w.currency: w.balance for w in list_wallets(client)}
    log.debug("balances: %s", {c: str(b) for c, b in snapshot.items()})
    return snapshot
