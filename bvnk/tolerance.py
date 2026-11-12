"""Rounding-aware comparisons for API amounts.

The simulator rounds amounts to the currency's precision and prices to 8dp, so exact equality is
too strict, while a blanket tolerance (the old 1e-6) is loose enough to hide a wrong fee. Every
tolerance here is derived from the rounding that is actually applied.
"""
import logging
from decimal import Decimal

from bvnk import config

log = logging.getLogger("bvnk.tolerance")


def quantum(precision: int) -> Decimal:
    """Smallest unit of a currency with `precision` decimal places (8 -> 1e-8)."""
    return Decimal(1).scaleb(-precision)


def decimal_quantum(value: Decimal) -> Decimal:
    """Smallest unit the API used when it formatted `value` (Decimal('12.500000') -> 1e-6)."""
    return Decimal(1).scaleb(value.as_tuple().exponent)


def price_rounding_error(amount: Decimal, result: Decimal) -> Decimal:
    """Max error in `amount * price` when price is rounded to 8dp and the result to its own precision.

    Rounding is to nearest, so each source contributes at most half a quantum.
    """
    return amount * config.PRICE_QUANTUM / 2 + decimal_quantum(result) / 2


def within(actual: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(actual - expected) <= tolerance


def warn_if_not_discriminating(what: str, tolerance: Decimal, fee_effect: Decimal) -> None:
    """The check only proves the fee was applied if rounding error is smaller than the fee itself."""
    if tolerance >= fee_effect:
        log.warning("%s: tolerance %s >= fee effect %s, this check cannot tell the fee from rounding",
                    what, tolerance, fee_effect)
