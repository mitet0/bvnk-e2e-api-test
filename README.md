# BVNK E2E API test framework

[![Lint](https://github.com/mitet0/bvnk-e2e-api-test/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/mitet0/bvnk-e2e-api-test/actions/workflows/lint.yml)

pytest + requests suite for the BVNK simulator (currency quotes/trades). Requires **Python 3.11+**. Reports: a self-contained HTML report plus Allure results.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest                       # full run (~100s) vs. the real simulator
.venv/bin/pytest -m mandatory          # only the 3 trades required by the brief
.venv/bin/pytest -m e2e                # all e2e: trades, status lifecycle, concurrency
.venv/bin/pytest -m "not slow"         # skip tests that wait on settlement/expiry (~6-22s each)
.venv/bin/pytest -m negative           # also: positive, slow, api, auth, wallet, quotes
```
**Reports** (written to `reports/`, git-ignored, regenerated every run):
- `reports/report.html` – self-contained pytest-html report, open it directly in a browser (no extra tooling).
- `reports/allure-results` – Allure data; view with `allure serve reports/allure-results` (needs the Allure CLI, e.g. `brew install allure`). Each test has steps, HTTP request/response attachments and a `test log` attachment in the **Tear down** section (attached by the autouse `test_log` fixture in `tests/conftest.py`; allure-pytest's own capture is off via `--allure-no-capture` so it isn't duplicated).
- `reports/test.log` – full DEBUG log.

Config via environment variables, all optional (see `.env.example`; copy it to `.env` and run `set -a; source .env; set +a`, as `.env` files are not loaded automatically):
- `BVNK_BASE_URL` – simulator URL (default `https://qa-simulator.test.bvnk.com`)
- `BVNK_TOKEN` – reuse an existing bearer token instead of calling `/init`
- `BVNK_TIMEOUT` – per-request timeout in seconds (default `15`)

## Logging / debugging
- Every run writes `reports/test.log` (DEBUG; overwritten each run) and each test's log is attached to its Allure result under Tear down.
- Each request is logged as `>> METHOD path auth=<masked token> payload=...` and each response as `<< METHOD path -> status in <ms>`; bodies are DEBUG-only (truncated to `LOG_BODY_LIMIT`), non-2xx responses log the body at WARNING.
- Also logged: new account init, quote creation (amounts/price/fee), status transitions, balance snapshots, and `=== START/END <test id>` markers.
- Tokens are masked (first 4 chars) and `/init` bodies are redacted everywhere.
- Live console output: `pytest --log-cli-level=DEBUG -k <test>`.

## Layout
- `bvnk/client.py` – HTTP wrapper (bearer auth, timeout, logging)
- `bvnk/api/` – one module per endpoint group (auth, wallets, quotes); `*_raw` returns the Response for negative tests
- `bvnk/schemas.py` – the **only** place that knows wire field names (parsing + quote payload)
- `data/trade_scenarios.yaml` – table-driven trade scenarios (id, from, to, mode `amount_in`/`amount_out`, amount, tags). Add a row to add a test.
- `tests/e2e/` – trades from the YAML (3 mandatory + the other ordered ETH/TRX/USDT pairs + exact-output mode): snapshot balances, quote, validate fee and amount maths, accept, settle, verify debit/credit; plus quote status-transition and concurrent-accept tests
- `tests/api/` – auth (missing/invalid token, `/echo`), wallets + pagination, quote negatives (validation, unknown id, insufficient funds, double-accept, expiry after 20s)

## Findings about the simulator
- Accept (`PUT /api/v1/quote/accept/{uuid}`) is asynchronous: `paymentStatus` goes PROCESSING -> SUCCESS in ~6s and balances only move then, so tests poll (`quotes.wait_for_settlement`).
- Fee semantics are **observed, not documented**: the brief and docs.bvnk.com only state a 0.01% service fee, not what it is charged on or whether it is deducted from or added to `amountIn`. The tests encode what the simulator does, so a failure means its behaviour changed, not that a documented rule was broken. Observed: fee = 0.01% of the *source* amount. `amountIn` mode: `amountOut = amountIn * price * (1 - fee)`. `amountOut` mode (exact output): `price` is source-per-target and `amountIn = amountOut * price * (1 + fee)`; `price` is rounded to 8dp, so tolerances are derived from that.
- Statuses: `PENDING/PENDING` -> `ACCEPTED/PROCESSING` -> `PAYMENT_OUT_PROCESSED/SUCCESS`. `paymentReceiptDate` stays null and `lastUpdated` does not advance on settlement, so these are not asserted.
- Concurrent accepts of one quote: exactly one 200, others 400, funds move once.
- Quote creation needs `fromWallet`/`toWallet` ids (from `/api/wallet`), `amountIn` xor `amountOut`; insufficient funds -> 412.

## Simulator vs. real BVNK API
Tests target the simulator's contract only. It mimics the legacy Quote API (retired in production on 30 Oct 2026 in favour of Transfers v.3). Known differences from docs.bvnk.com: Bearer token instead of Hawk auth, FastAPI `{"detail": ...}` errors instead of `{code, status, traceId, message}`, `offset`/`max_count` pagination instead of `page`/`size`, 422 vs 400 on malformed UUIDs, and no idempotency keys. Assertions therefore avoid real-API error bodies.

## Design notes
- Rates fluctuate, so assertions use the rate reported by the quote itself, never a hard-coded one.
- Each test is independent and compares before/after wallet snapshots (deltas), so it does not depend on default balances beyond having sufficient funds (non-mandatory scenarios skip if underfunded; **mandatory scenarios fail**, so they can never silently skip).
- A token is created per test via `/init`; each call returns a fresh funded account (own wallets and balances), so tests are isolated and safe to run in parallel (`pytest -n 4`, pytest-xdist). Setting `BVNK_TOKEN` forces one shared account for every test, which is **not** parallel-safe because balance-delta assertions would interfere.
- Tolerances are derived from the rounding the API applies (`bvnk/tolerance.py`): balances to the currency's `quantityPrecision`, prices to 8dp. A blanket tolerance would be larger than the 0.01% fee on small-price pairs (e.g. TRX->ETH) and hide a wrong fee. If a scenario is so small that rounding could mask the fee, a warning is logged (`warn_if_not_discriminating`).
- Rejection tests assert exact status codes observed on the simulator (expired quote -> 412 and state `EXPIRED`, re-accept -> 400), not just "any 4xx/5xx".

## Known simulator defect
- A negative `amountIn` is accepted (201) with a negative `amountOut`. Recorded as `test_negative_amount_rejected` (xfail).
