import logging

from bvnk.client import ApiClient, mask

log = logging.getLogger("bvnk.auth")


def init_account(client: ApiClient) -> str:
    """GET /init -> fresh account + bearer token (valid 24h)."""
    resp = client.get("/init", auth=False)
    resp.raise_for_status()
    body = resp.json()
    assert body.get("access_token"), "/init returned no access_token"
    log.info("initialised new account, token %s, expiry %s", mask(body["access_token"]), body.get("expiry"))
    return body["access_token"]


def echo(client: ApiClient, body=None, **kw):
    return client.post("/echo", json=body, **kw)
