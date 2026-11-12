import allure
import pytest

from bvnk.api import auth, wallets as wallets_api
from bvnk.constants import (Currency, HTTPStatus, NIL_UUID, NON_EXISTENT_WALLET_ID,
                            WALLET_ACTIVE)

pytestmark = [pytest.mark.api, allure.epic("API")]

PROTECTED = ["/echo", "/api/wallet", "/api/wallet/1", "/api/v1/quote", f"/api/v1/quote/{NIL_UUID}"]


@allure.parent_suite("API")
@pytest.mark.auth
@allure.suite("Authentication")
@allure.feature("Authentication")
@allure.sub_suite("Token handling and /echo")
class TestAuthentication:

    @pytest.mark.negative
    @allure.title("Request without a token is rejected (401): {path}")
    @pytest.mark.parametrize("path", PROTECTED)
    def test_missing_token_rejected(self, anon_client, path):
        method = "POST" if path == "/echo" else "GET"
        assert anon_client.request(method, path, auth=False).status_code == HTTPStatus.UNAUTHORIZED

    @pytest.mark.negative
    @allure.title("Request with an invalid token is rejected (401)")
    def test_invalid_token_rejected(self, anon_client):
        assert anon_client.get("/api/wallet", token="not-a-real-token").status_code == HTTPStatus.UNAUTHORIZED

    @pytest.mark.positive
    @allure.title("/echo returns the token expiry and echoes the request body")
    def test_echo_returns_expiry_and_body(self, client):
        payload = {"hello": "bvnk", "n": 1}
        resp = auth.echo(client, payload)
        assert resp.status_code == HTTPStatus.OK
        body = resp.json()
        assert body["request_payload"] == payload
        assert body["auth_token_expiry_time"]


@allure.parent_suite("API")
@pytest.mark.wallet
@allure.suite("Wallets")
@allure.feature("Wallets")
@allure.sub_suite("Wallet listing and lookup")
class TestWallets:

    @pytest.mark.positive
    @allure.title("Account has active, non-negative ETH, TRX and USDT wallets")
    def test_list_wallets_has_required_currencies(self, wallets):
        assert set(Currency) <= set(wallets)
        assert all(w.balance >= 0 and w.status == WALLET_ACTIVE for w in wallets.values())

    @pytest.mark.positive
    @allure.title("Get wallet by id matches the wallet returned by the list")
    def test_get_wallet_matches_list(self, client, wallets):
        for w in wallets.values():
            assert wallets_api.get_wallet(client, w.id) == w

    @pytest.mark.positive
    @allure.title("List wallets honours offset / max_count pagination")
    def test_list_wallets_pagination(self, client, wallets):
        first = wallets_api.list_wallets_raw(client, params={"offset": 0, "max_count": 1}).json()
        assert len(first) == 1
        assert wallets_api.list_wallets_raw(client, params={"offset": len(wallets), "max_count": 10}).json() == []

    @pytest.mark.negative
    @allure.title("Get unknown wallet is rejected (404)")
    def test_get_unknown_wallet_404(self, client):
        assert wallets_api.get_wallet_raw(client, NON_EXISTENT_WALLET_ID).status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.negative
    @allure.title("Get wallet with a non-numeric id is rejected (422)")
    def test_get_wallet_non_numeric_id_422(self, client):
        assert wallets_api.get_wallet_raw(client, "abc").status_code == HTTPStatus.UNPROCESSABLE_ENTITY
