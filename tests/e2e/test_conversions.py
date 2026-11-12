"""E2E trades: precondition balances -> quote -> accept -> settle -> verify.

Scenarios are table-driven from data/trade_scenarios.yaml.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

import allure
import pytest

from bvnk import config, scenarios
from bvnk.api import quotes
from bvnk.client import ApiClient
from bvnk.constants import Currency, HTTPStatus, PaymentStatus, QuoteStatus
from bvnk.tolerance import price_rounding_error, quantum, warn_if_not_discriminating, within

pytestmark = [pytest.mark.e2e, allure.epic("Trading"), allure.feature("Currency conversion")]

FEE = config.SERVICE_FEE_RATE


def assert_new_quote(quote, src, dst, fee_base: Decimal, fee_base_error: Decimal = Decimal(0)):
    """Checks common to every freshly created quote, whichever amount mode requested it.

    The fee semantics asserted here (0.01% of the source amount, deducted from amountIn) are observed
    simulator behaviour; the brief and BVNK docs only state "0.01% service fee".

    fee_base is the amount the 0.01% service fee is charged on (amountIn, or amountOut * price);
    fee_base_error is how far price rounding can move it (0 when fee_base is an exact request amount).
    """
    assert (quote.from_currency, quote.to_currency) == (src, dst)
    assert (quote.quote_status, quote.payment_status) == (QuoteStatus.PENDING, PaymentStatus.PENDING)
    assert quote.amount_in > 0 and quote.amount_out > 0 and quote.price > 0

    expected_fee, fee_tol = fee_base * FEE, fee_base_error * FEE
    fees = quote.raw["fees"]
    assert within(quote.fee, expected_fee, fee_tol), f"fee {quote.fee} != {expected_fee} (+/-{fee_tol})"
    assert Decimal(fees["percentage"]["service"]) == config.SERVICE_FEE_PERCENT
    assert within(Decimal(fees["value"]["service"]), expected_fee, fee_tol)
    assert Decimal(fees["value"]["processing"]) == 0


def settle_and_verify(client, snapshot, wallets, before, quote, src, dst):
    """Accept, wait for settlement, then verify wallet movements (shared by both amount modes)."""
    with allure.step("Accept quote and wait for settlement"):
        accepted = quotes.accept_quote(client, quote.uuid)
        assert accepted.uuid == quote.uuid and accepted.quote_status == QuoteStatus.ACCEPTED
        final = quotes.wait_for_settlement(client, quote.uuid)
        assert final.payment_status == PaymentStatus.SUCCESS, f"trade did not settle: {final.payment_status}"

    with allure.step("Verify wallet balances"):
        after = snapshot()
        # Balances are held to the currency's precision, so allow one quantum of that currency.
        debit, credit = before[src] - after[src], after[dst] - before[dst]
        assert within(debit, quote.amount_in, quantum(wallets[src].precision)), \
            f"{src} debited {debit}, quote said {quote.amount_in}"
        assert within(credit, quote.amount_out, quantum(wallets[dst].precision)), \
            f"{dst} credited {credit}, quote said {quote.amount_out}"
        for ccy in set(before) - {src, dst}:
            assert after[ccy] == before[ccy], f"unrelated wallet {ccy} changed"


def preconditions(request, wallets, snapshot, src, dst, needed):
    with allure.step("Preconditions: wallets exist and source is funded"):
        assert src in wallets and dst in wallets, f"missing wallet(s): {sorted(wallets)}"
        before = snapshot()
        if before[src] < needed:
            reason = f"insufficient {src}: {before[src]} < {needed}"
            # A mandatory scenario must never silently skip: that would look like a pass.
            if request.node.get_closest_marker("mandatory"):
                pytest.fail(reason)
            pytest.skip(reason)
        return before


@allure.parent_suite("E2E")
@allure.suite("Currency conversions")
@allure.sub_suite("Quote -> accept -> settle")
class TestCurrencyConversion:
    """Full trade lifecycle against the quote and wallet endpoints."""

    @pytest.mark.positive
    @pytest.mark.slow  # waits ~6s for asynchronous settlement
    @pytest.mark.parametrize("src,dst,amount", scenarios.load("amount_in"))
    @allure.title("Sell {amount} {src} for {dst}")
    def test_convert(self, request, client, wallets, snapshot, src, dst, amount):
        before = preconditions(request, wallets, snapshot, src, dst, amount)

        with allure.step("Create quote and validate it"):
            quote = quotes.create_quote(client, src, dst, amount, wallets[src].id, wallets[dst].id)
            assert_new_quote(quote, src, dst, fee_base=amount)
            assert quote.amount_in == amount

        with allure.step("Validate amountOut = amountIn * price * (1 - fee)"):
            # Rates fluctuate, so use the quote's own price; allow only the rounding actually applied.
            tolerance = price_rounding_error(amount, quote.amount_out)
            gross = amount * quote.price
            warn_if_not_discriminating("amountOut", tolerance, gross * FEE)
            assert within(quote.amount_out, gross * (1 - FEE), tolerance), \
                f"amountOut {quote.amount_out} != {gross * (1 - FEE)} (+/-{tolerance}): fee not applied as 0.01%?"

        settle_and_verify(client, snapshot, wallets, before, quote, src, dst)

    @pytest.mark.positive
    @pytest.mark.slow
    @pytest.mark.parametrize("src,dst,amount", scenarios.load("amount_out"))
    @allure.title("Receive exactly {amount} {dst} by selling {src}")
    def test_convert_exact_output(self, request, client, wallets, snapshot, src, dst, amount):
        # The source amount is unknown until quoted, so the funding check happens after the quote is created.
        before = preconditions(request, wallets, snapshot, src, dst, Decimal(0))

        with allure.step("Create quote by requested output amount and validate it"):
            quote = quotes.create_quote(client, src, dst, None, wallets[src].id, wallets[dst].id,
                                        amount_out=amount)
            # In this mode price is quoted as source-per-target and the fee is added on top:
            #   gross = amountOut * price;  fee = gross * 0.01%;  amountIn = gross + fee
            gross = amount * quote.price
            assert_new_quote(quote, src, dst, fee_base=gross,
                             fee_base_error=amount * config.PRICE_QUANTUM / 2)
            assert quote.amount_out == amount, "requested output must be quoted exactly"
            assert before[src] >= quote.amount_in, f"insufficient {src}: {before[src]} < {quote.amount_in}"

        with allure.step("Validate amountIn = amountOut * price * (1 + fee)"):
            tolerance = price_rounding_error(amount, quote.amount_in)
            warn_if_not_discriminating("amountIn", tolerance, gross * FEE)
            assert within(quote.amount_in, gross * (1 + FEE), tolerance), \
                f"amountIn {quote.amount_in} != {gross * (1 + FEE)} (+/-{tolerance})"

        settle_and_verify(client, snapshot, wallets, before, quote, src, dst)


@allure.parent_suite("E2E")
@allure.suite("Quote lifecycle")
@allure.sub_suite("Status transitions")
class TestQuoteLifecycle:

    @pytest.mark.positive
    @pytest.mark.slow
    @allure.title("Quote moves PENDING -> ACCEPTED/PROCESSING -> PAYMENT_OUT_PROCESSED/SUCCESS")
    def test_status_transitions(self, client, wallets):
        with allure.step("Created quote is PENDING with no acceptance date yet"):
            q = quotes.create_quote(client, Currency.TRX, Currency.USDT, 100,
                                    wallets[Currency.TRX].id, wallets[Currency.USDT].id)
            assert (q.quote_status, q.payment_status) == (QuoteStatus.PENDING, PaymentStatus.PENDING)
            assert q.raw["acceptanceDate"] is None

        with allure.step("Accept and record every status observed until settlement"):
            accepted = quotes.accept_quote(client, q.uuid)
            assert (accepted.quote_status, accepted.payment_status) == (QuoteStatus.ACCEPTED, PaymentStatus.PROCESSING)
            observed = quotes.track_statuses(client, q.uuid)
            allure.attach(str(observed), "observed statuses")

        with allure.step("Statuses only ever move forward, ending in SUCCESS"):
            order = [(QuoteStatus.ACCEPTED, PaymentStatus.PROCESSING),
                     (QuoteStatus.PAYMENT_OUT_PROCESSED, PaymentStatus.SUCCESS)]
            assert observed[-1] == order[-1]
            assert set(observed) <= set(order), f"unexpected status seen: {observed}"
            assert [order.index(s) for s in observed] == sorted(order.index(s) for s in observed)

        with allure.step("Acceptance timestamps are coherent and the final state is stable"):
            final = quotes.get_quote(client, q.uuid)
            assert (final.quote_status, final.payment_status) == order[-1]
            raw = final.raw
            assert raw["dateCreated"] <= raw["acceptanceDate"] <= raw["acceptanceExpiryDate"]


@allure.parent_suite("E2E")
@allure.suite("Quote lifecycle")
@allure.sub_suite("Concurrency")
class TestConcurrentAcceptance:

    @pytest.mark.negative
    @pytest.mark.slow
    @allure.title("Accepting one quote from {workers} concurrent clients executes the trade exactly once")
    @pytest.mark.parametrize("workers", [config.CONCURRENT_ACCEPT_WORKERS])
    def test_concurrent_accept_executes_once(self, client, wallets, snapshot, workers):
        src, dst, amount = Currency.TRX, Currency.USDT, Decimal(100)
        before = snapshot()
        q = quotes.create_quote(client, src, dst, amount, wallets[src].id, wallets[dst].id)

        barrier = threading.Barrier(workers)

        def accept():
            c = ApiClient(token=client.token)  # one session per thread
            barrier.wait()  # release all requests together
            return quotes.accept_quote_raw(c, q.uuid).status_code

        with allure.step(f"Fire {workers} simultaneous accept requests"):
            with ThreadPoolExecutor(workers) as pool:
                codes = [f.result() for f in [pool.submit(accept) for _ in range(workers)]]
            allure.attach(str(codes), "status codes")

        with allure.step("Exactly one accept succeeds (200), the rest are rejected (400)"):
            assert codes.count(HTTPStatus.OK) == 1, f"expected exactly one 200, got {codes}"
            assert all(c == HTTPStatus.BAD_REQUEST for c in codes if c != HTTPStatus.OK), codes

        with allure.step("Funds moved exactly once"):
            assert quotes.wait_for_settlement(client, q.uuid).payment_status == PaymentStatus.SUCCESS
            after = snapshot()
            assert within(before[src] - after[src], amount, quantum(wallets[src].precision)), \
                "source debited more or less than once"
            assert within(after[dst] - before[dst], q.amount_out, quantum(wallets[dst].precision)), \
                "target credited more or less than once"
