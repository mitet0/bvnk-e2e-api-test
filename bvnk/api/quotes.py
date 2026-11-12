import logging
import time

from bvnk import config
from bvnk.client import ApiClient
from bvnk.constants import HTTPStatus, PaymentStatus
from bvnk.schemas import Quote, quote_payload

log = logging.getLogger("bvnk.quotes")


def create_quote_raw(client: ApiClient, from_currency, to_currency, amount, from_wallet, to_wallet,
                     amount_out=None, **kw):
    body = quote_payload(from_currency, to_currency, amount, from_wallet, to_wallet, amount_out)
    return client.post("/api/v1/quote", json=body, **kw)


def create_quote(client: ApiClient, from_currency, to_currency, amount, from_wallet, to_wallet,
                 amount_out=None) -> Quote:
    resp = create_quote_raw(client, from_currency, to_currency, amount, from_wallet, to_wallet, amount_out)
    assert resp.status_code == HTTPStatus.CREATED, f"create quote failed: {resp.status_code} {resp.text}"
    q = Quote.parse(resp.json())
    log.info("quote %s created: %s %s -> %s %s @ %s fee=%s", q.uuid, q.amount_in, q.from_currency,
             q.amount_out, q.to_currency, q.price, q.fee)
    return q


def accept_quote_raw(client: ApiClient, quote_uuid: str, **kw):
    return client.request("PUT", f"/api/v1/quote/accept/{quote_uuid}", **kw)


def accept_quote(client: ApiClient, quote_uuid: str) -> Quote:
    resp = accept_quote_raw(client, quote_uuid)
    assert resp.status_code == HTTPStatus.OK, f"accept failed: {resp.status_code} {resp.text}"
    return Quote.parse(resp.json())


def get_quote_raw(client: ApiClient, quote_uuid: str, **kw):
    return client.get(f"/api/v1/quote/{quote_uuid}", **kw)


def get_quote(client: ApiClient, quote_uuid: str) -> Quote:
    resp = get_quote_raw(client, quote_uuid)
    resp.raise_for_status()
    return Quote.parse(resp.json())


def list_quotes_raw(client: ApiClient, **kw):
    return client.get("/api/v1/quote", **kw)


FINAL_STATUSES = {PaymentStatus.SUCCESS, PaymentStatus.FAILED, PaymentStatus.EXPIRED, PaymentStatus.CANCELLED}


def wait_for_settlement(client: ApiClient, quote_uuid: str, timeout: float = config.SETTLEMENT_TIMEOUT,
                       interval: float = config.SETTLEMENT_POLL_INTERVAL) -> Quote:
    """Accept is asynchronous (paymentStatus PROCESSING -> SUCCESS); poll until final."""
    deadline = time.monotonic() + timeout
    while True:
        q = get_quote(client, quote_uuid)
        log.debug("quote %s: %s/%s", quote_uuid, q.quote_status, q.payment_status)
        if q.payment_status in FINAL_STATUSES:
            return q
        if time.monotonic() > deadline:
            log.error("quote %s did not settle within %ss (last: %s/%s)", quote_uuid, timeout,
                      q.quote_status, q.payment_status)
            return q
        time.sleep(interval)


def track_statuses(client: ApiClient, quote_uuid: str, timeout: float = config.SETTLEMENT_TIMEOUT,
                    interval: float = config.STATUS_POLL_INTERVAL):
    """Poll until settled and return the ordered, de-duplicated list of (quoteStatus, paymentStatus) seen."""
    seen, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        q = get_quote(client, quote_uuid)
        state = (q.quote_status, q.payment_status)
        if not seen or seen[-1] != state:
            seen.append(state)
            log.info("quote %s status -> %s/%s", quote_uuid, *state)
        if q.payment_status in FINAL_STATUSES:
            break
        time.sleep(interval)
    return seen
