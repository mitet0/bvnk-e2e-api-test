"""Named values for the simulator's contract (statuses, currencies, ids) so tests read as intent."""
from enum import StrEnum
from http import HTTPStatus  # re-exported: use HTTPStatus.NOT_FOUND, not 404

__all__ = ["HTTPStatus", "Currency", "QuoteStatus", "PaymentStatus", "WALLET_METHOD",
           "WALLET_ACTIVE", "NIL_UUID", "NON_EXISTENT_WALLET_ID"]


class Currency(StrEnum):
    ETH = "ETH"
    TRX = "TRX"
    USDT = "USDT"


class QuoteStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PAYMENT_OUT_PROCESSED = "PAYMENT_OUT_PROCESSED"
    EXPIRED = "EXPIRED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


WALLET_METHOD = "wallet"          # payInMethod / payOutMethod for wallet-to-wallet conversions
WALLET_ACTIVE = "ACTIVE"
NIL_UUID = "00000000-0000-0000-0000-000000000000"
NON_EXISTENT_WALLET_ID = 999_999_999
