from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def account_module():
    return SourceFileLoader(
        "account_model", str(ROOT / "account-model.py")
    ).load_module()


@pytest.fixture(scope="session")
def utxo_module():
    return SourceFileLoader(
        "utxo_model", str(ROOT / "utxo-model.py")
    ).load_module()
