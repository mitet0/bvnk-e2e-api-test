import time
import uuid

import allure
import pytest

from bvnk import config
from bvnk.api import quotes
from bvnk.constants import Currency, HTTPStatus, PaymentStatus, QuoteStatus, WALLET_METHOD

pytestmark = [pytest.mark.api, allure.epic("API")]


@pytest.fixture
def new_quote(client, wallets):
    def _make(src=Currency.ETH, dst=Currency.TRX, amount=1):
        return quotes.create_quote(client, src, dst, amount, wallets[src].id, wallets[dst].id)
    return _make


@allure.parent_suite("API")
@pytest.mark.quotes
@allure.suite("Quotes")
@allure.feature("Quotes")
@allure.sub_suite("Quote lifecycle and validation")
class TestQuotes:

    @pytest.mark.positive
    @allure.title("Get quote returns the quote that was created")
    def test_get_quote_returns_created_quote(self, client, new_quote):
        q = new_quote()
        got = quotes.get_quote(client, q.uuid)
        assert got.uuid == q.uuid and got.amount_in == q.amount_in and got.amount_out == q.amount_out

    @pytest.mark.positive
    @allure.title("Created quote appears in the quote list")
    def test_quote_listed_in_all_quotes(self, client, new_quote):
        q = new_quote()
        assert q.uuid in [x["uuid"] for x in quotes.list_quotes_raw(client).json()]

    @pytest.mark.positive
    @allure.title("Quote acceptance window is 20 seconds")
    def test_quote_acceptance_window_is_20_seconds(self, new_quote):
        q = new_quote()
        window = q.raw["acceptanceExpiryDate"] - q.raw["dateCreated"]
        assert window == config.QUOTE_TTL_SECONDS

    @pytest.mark.negative
    @allure.title("Get unknown quote is rejected (404)")
    def test_unknown_quote_404(self, client):
        assert quotes.get_quote_raw(client, str(uuid.uuid4())).status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.negative
    @allure.title("Malformed quote uuid is rejected on get and accept (400/422); wallets unchanged")
    def test_malformed_quote_uuid_rejected(self, client, wallets_unchanged):
        # BVNK docs list 400 for Get quote; the simulator (FastAPI) answers 422. Either is a client-error rejection.
        rejected = (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY)
        with wallets_unchanged():
            assert quotes.get_quote_raw(client, "not-a-uuid").status_code in rejected
            assert quotes.accept_quote_raw(client, "not-a-uuid").status_code in rejected

    @pytest.mark.negative
    @allure.title("amountIn and amountOut are mutually exclusive (400); wallets unchanged")
    def test_amount_in_and_out_are_mutually_exclusive(self, client, wallets, wallets_unchanged):
        body = {"from": Currency.ETH, "to": Currency.TRX, "fromWallet": wallets[Currency.ETH].id,
                "toWallet": wallets[Currency.TRX].id,
                "useMaximum": False, "useMinimum": False, "reference": "t", "payInMethod": WALLET_METHOD,
                "payOutMethod": WALLET_METHOD}
        with wallets_unchanged():
            neither = client.post("/api/v1/quote", json=body)
            both = client.post("/api/v1/quote", json={**body, "amountIn": 1, "amountOut": 1})
            assert neither.status_code == HTTPStatus.BAD_REQUEST
            assert both.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.negative
    @allure.title("Create quote with missing required fields is rejected (422); wallets unchanged")
    def test_missing_required_fields_422(self, client, wallets_unchanged):
        with wallets_unchanged():
            resp = client.post("/api/v1/quote", json={"from": Currency.ETH})
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.negative
    @allure.title("Create quote above the available balance is rejected (412); wallets unchanged")
    def test_insufficient_funds_rejected(self, client, wallets, wallets_unchanged):
        with wallets_unchanged():
            resp = quotes.create_quote_raw(client, Currency.ETH, Currency.TRX, config.UNFUNDED_AMOUNT,
                                           wallets[Currency.ETH].id, wallets[Currency.TRX].id)
        assert resp.status_code == HTTPStatus.PRECONDITION_FAILED

    @pytest.mark.negative
    @pytest.mark.slow
    @allure.title("Accepting a settled quote again is rejected (400); funds not moved twice")
    def test_accept_twice_does_not_double_spend(self, client, new_quote, snapshot):
        q = new_quote()
        quotes.accept_quote(client, q.uuid)
        assert quotes.wait_for_settlement(client, q.uuid).payment_status == PaymentStatus.SUCCESS
        settled = snapshot()
        assert quotes.accept_quote_raw(client, q.uuid).status_code == HTTPStatus.BAD_REQUEST
        assert snapshot() == settled

    @pytest.mark.negative
    @pytest.mark.slow
    @allure.title("Expired quote (after 20s) cannot be accepted (412); wallets unchanged")
    def test_expired_quote_cannot_be_accepted(self, client, new_quote, snapshot):
        q = new_quote()
        before = snapshot()
        time.sleep(config.QUOTE_TTL_SECONDS + config.EXPIRY_GRACE_SECONDS)
        assert quotes.accept_quote_raw(client, q.uuid).status_code == HTTPStatus.PRECONDITION_FAILED
        expired = quotes.get_quote(client, q.uuid)
        assert (expired.quote_status, expired.payment_status) == (QuoteStatus.EXPIRED, PaymentStatus.EXPIRED)
        assert snapshot() == before

    @pytest.mark.negative
    @allure.title("Create quote with a zero amount is rejected (400); wallets unchanged")
    def test_zero_amount_rejected(self, client, wallets, wallets_unchanged):
        with wallets_unchanged():
            resp = quotes.create_quote_raw(client, Currency.ETH, Currency.TRX, 0,
                                           wallets[Currency.ETH].id, wallets[Currency.TRX].id)
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.negative
    @pytest.mark.xfail(reason="Simulator defect: a negative amountIn is quoted with a 201 and a negative "
                              "amountOut instead of being rejected. Remove xfail once fixed.")
    @allure.title("Create quote with a negative amount is rejected (400/422); wallets unchanged")
    def test_negative_amount_rejected(self, client, wallets, wallets_unchanged):
        with wallets_unchanged():
            resp = quotes.create_quote_raw(client, Currency.ETH, Currency.TRX, -1,
                                           wallets[Currency.ETH].id, wallets[Currency.TRX].id)
        assert resp.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY)

    @pytest.mark.negative
    @allure.title("Create quote for an unsupported currency is rejected (400); wallets unchanged")
    def test_unsupported_currency_rejected(self, client, wallets, wallets_unchanged):
        with wallets_unchanged():
            resp = quotes.create_quote_raw(client, Currency.ETH, "XXX", 1,
                                           wallets[Currency.ETH].id, wallets[Currency.TRX].id)
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.negative
    @allure.title("Create quote whose wallet does not match the currency is rejected (400); wallets unchanged")
    def test_wallet_currency_mismatch_rejected(self, client, wallets, wallets_unchanged):
        with wallets_unchanged():
            resp = quotes.create_quote_raw(client, Currency.ETH, Currency.TRX, 1,
                                           wallets[Currency.TRX].id, wallets[Currency.ETH].id)  # wallets swapped
        assert resp.status_code == HTTPStatus.BAD_REQUEST
