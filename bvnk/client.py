import json
import logging
from typing import Optional

import allure
import requests

from bvnk import config

log = logging.getLogger("bvnk.http")
SENSITIVE_PATHS = ("/init",)  # responses contain the bearer token, never log/attach their body


def mask(token: Optional[str]) -> str:
    """First 4 chars only, enough to tell tokens apart in logs."""
    return "<none>" if not token else f"{token[:4]}…({len(token)} chars)"


class ApiClient:
    """Thin requests wrapper: base URL, bearer auth, timeout, request/response logging."""

    def __init__(self, base_url: str = config.BASE_URL, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()

    def request(self, method: str, path: str, *, auth: bool = True, token: Optional[str] = None,
                **kw) -> requests.Response:
        headers = kw.pop("headers", {})
        tok = token if token is not None else self.token
        if auth and tok is not None:
            headers["Authorization"] = f"Bearer {tok}"
        sent = kw.get("json") if kw.get("json") is not None else kw.get("params")
        log.debug(">> %s %s auth=%s payload=%s", method, path,
                  mask(tok) if auth else "off", None if sent is None else json.dumps(sent, default=str))
        resp = self.session.request(method, self.base_url + path, headers=headers,
                                    timeout=config.REQUEST_TIMEOUT, **kw)
        body = "<redacted>" if path in SENSITIVE_PATHS else resp.text[:config.LOG_BODY_LIMIT]
        elapsed_ms = resp.elapsed.total_seconds() * 1000
        if resp.ok:  # keep INFO to one short line; the body is DEBUG-only
            log.info("<< %s %s -> %s in %.0fms", method, path, resp.status_code, elapsed_ms)
            log.debug("   body: %s", body)
        else:
            log.warning("<< %s %s -> %s in %.0fms %s", method, path, resp.status_code, elapsed_ms, body)
        self._attach(method, path, kw, resp)
        return resp

    @staticmethod
    def _attach(method, path, kw, resp):
        """Attach the exchange to the Allure report (never the Authorization header / token)."""
        with allure.step(f"{method} {path} -> {resp.status_code}"):
            if kw.get("json") is not None or kw.get("params"):
                allure.attach(json.dumps(kw.get("json") or kw.get("params"), indent=2, default=str),
                              "request", allure.attachment_type.JSON)
            if path not in SENSITIVE_PATHS:  # response contains the bearer token
                allure.attach(resp.text, "response", allure.attachment_type.JSON)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)
