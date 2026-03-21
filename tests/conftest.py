import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name, file_name):
    module_path = ROOT / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar modulo {module_name} desde {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def account_module():
    return _load_module("account_model", "account-model.py")


@pytest.fixture(scope="session")
def utxo_module():
    return _load_module("utxo_model", "utxo-model.py")
