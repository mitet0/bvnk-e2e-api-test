"""Wire format of the QA simulator (https://qa-simulator.test.bvnk.com/openapi.json).

Amounts are decimal strings in the API; we parse them to Decimal to avoid float drift.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from bvnk.constants import WALLET_METHOD


def dec(value) -> Optional[Decimal]:
    return None if value in (None, "") else Decimal(str(value))


@dataclass(frozen=True)
class Wallet:
    id: int
    currency: str
    balance: Decimal
    available: Decimal
    status: Optional[str]
    precision: int  # decimal places the currency is quoted in (quantityPrecision)

    @classmethod
    def parse(cls, d: dict) -> "Wallet":
        return cls(id=d["id"], currency=d["currency"]["code"], balance=dec(d["balance"]),
                   available=dec(d["available"]), status=d.get("status"),
                   precision=d["currency"]["quantityPrecision"])


@dataclass(frozen=True)
class Quote:
    uuid: str
    from_currency: str
    to_currency: str
    amount_in: Decimal
    amount_out: Decimal
    price: Decimal
    fee: Decimal
    quote_status: str
    payment_status: str
    raw: dict

    @classmethod
    def parse(cls, d: dict) -> "Quote":
        return cls(uuid=d["uuid"], from_currency=d["from"], to_currency=d["to"],
                   amount_in=dec(d["amountIn"]), amount_out=dec(d["amountOut"]),
                   price=dec(d["price"]), fee=dec(d["fee"]),
                   quote_status=d["quoteStatus"], payment_status=d["paymentStatus"], raw=d)


def quote_payload(from_currency: str, to_currency: str, amount_in, from_wallet: int, to_wallet: int,
                  amount_out=None) -> dict:
    """Exactly one of amount_in / amount_out must be given (the API rejects neither or both)."""
    body = {
        "from": from_currency, "to": to_currency,
        "fromWallet": from_wallet, "toWallet": to_wallet,
        "useMaximum": False, "useMinimum": False,
        "reference": "e2e-test",
        "payInMethod": WALLET_METHOD, "payOutMethod": WALLET_METHOD,
    }
    if amount_out is not None:
        body["amountOut"] = str(amount_out)
    else:
        body["amountIn"] = str(amount_in)
    return body
