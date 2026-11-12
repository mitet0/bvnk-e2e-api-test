import io
import logging
from contextlib import contextmanager

import allure
import pytest

from bvnk import config
from bvnk.api import auth
from bvnk.api.wallets import balances, list_wallets
from bvnk.client import ApiClient

logging.getLogger("urllib3").setLevel(logging.WARNING)  # connection chatter drowns out our own logs


@pytest.fixture
def token():
    """Bearer token for this test. Each /init call creates a fresh funded account, so tests never
    share balances and can run in parallel. BVNK_TOKEN overrides this with one shared account."""
    return config.PRESET_TOKEN or auth.init_account(ApiClient())


@pytest.fixture
def client(token):
    return ApiClient(token=token)


@pytest.fixture
def anon_client():
    return ApiClient()


@pytest.fixture
def snapshot(client):
    """Callable returning a fresh currency->balance map."""
    return lambda: balances(client)


@pytest.fixture
def wallets(client):
    """currency code -> Wallet"""
    return {w.currency: w for w in list_wallets(client)}


@pytest.fixture
def wallets_unchanged(client):
    """Context manager for negative tests: balance and available funds of every wallet must be
    identical after the block, i.e. a rejected request must not move or hold funds."""
    def state():
        return {w.currency: (w.balance, w.available) for w in list_wallets(client)}

    @contextmanager
    def _check():
        before = state()
        yield
        with allure.step("Verify wallets are unchanged"):
            assert state() == before, "wallets changed after a rejected request"
    return _check


@pytest.fixture(autouse=True)
def test_log(request):
    """Log START/END markers and attach this test's log in the Allure "Tear down" section.

    allure-pytest's own capture is disabled (--allure-no-capture in pytest.ini) so the log is not
    attached twice; this fixture's teardown is what puts it under Tear down.
    """
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-5s %(name)-14s %(message)s",
                                           "%H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    log = logging.getLogger("bvnk.test")
    log.info("=== START %s", request.node.nodeid)
    yield
    log.info("=== END   %s", request.node.nodeid)
    root.removeHandler(handler)
    allure.attach(buffer.getvalue(), "test log", allure.attachment_type.TEXT)
