# BVNK E2E API test framework

pytest + requests suite for the BVNK QA simulator (`https://qa-simulator.test.bvnk.com`).
Requires Python 3.11+.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
Config via env vars (see `.env.example`): `BVNK_BASE_URL`, `BVNK_TOKEN`, `BVNK_TIMEOUT`.

## Layout
- `bvnk/client.py` – HTTP wrapper (bearer auth, timeout, logging)
- `bvnk/api/` – one module per endpoint group; `*_raw` helpers return the Response for negative tests
- `bvnk/schemas.py` – the only place that knows the wire field names
- `tests/api/` – authentication and wallet tests

Work in progress: quote and trade tests follow.
