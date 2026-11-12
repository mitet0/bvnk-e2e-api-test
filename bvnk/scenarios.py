"""Loads data/trade_scenarios.yaml into pytest params."""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

FILE = Path(__file__).resolve().parent.parent / "data" / "trade_scenarios.yaml"


def load(mode: str):
    rows = yaml.safe_load(FILE.read_text())["scenarios"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate scenario ids in trade_scenarios.yaml"
    return [
        pytest.param(r["from"], r["to"], Decimal(str(r["amount"])),
                     id=r["id"], marks=[getattr(pytest.mark, t) for t in r.get("tags", [])])
        for r in rows if r["mode"] == mode
    ]
