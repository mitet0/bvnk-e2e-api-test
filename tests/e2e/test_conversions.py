"""E2E trades: precondition balances -> quote -> accept -> settle -> verify.

The three trades required by the brief; scenarios move to a YAML table in a later commit.
"""
from decimal import Decimal

import allure
import pytest

from bvnk import config
from bvnk.api import quotes
from bvnk.constants import PaymentStatus, QuoteStatus
from bvnk.tolerance import price_rounding_error, quantum, warn_if_not_discriminating, within

pytestmark = [pytest.mark.e2e, allure.epic("Trading"), allure.feature("Currency conversion")]

FEE = config.SERVICE_FEE_RATE

MANDATORY_TRADES = [
    pytest.param("ETH", "TRX", Decimal(1), id="1-ETH-to-TRX", marks=pytest.mark.mandatory),
    pytest.param("TRX", "USDT", Decimal(420), id="420-TRX-to-USDT", marks=pytest.mark.mandatory),
    pytest.param("TRX", "ETH", Decimal(987), id="987-TRX-to-ETH", marks=pytest.mark.mandatory),
]


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
    @pytest.mark.parametrize("src,dst,amount", MANDATORY_TRADES)
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
