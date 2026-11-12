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
