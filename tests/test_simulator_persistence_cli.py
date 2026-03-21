import json
import subprocess
import sys
from pathlib import Path


def _run_simulator(args, cwd: Path):
    cmd = [sys.executable, "scripts/blockchain_models_simulator.py", *args]
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return completed


def test_cli_persist_list_show_utxo(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_dir = tmp_path / "runs"

    persist = _run_simulator(
        [
            "--scenario",
            "retail-payments",
            "--model",
            "utxo",
            "--persist",
            "--json",
            "--store-dir",
            str(store_dir),
        ],
        cwd=repo_root,
    )
    assert persist.returncode == 0, persist.stderr

    persist_payload = json.loads(persist.stdout)
    assert len(persist_payload["persisted_runs"]) == 1
    run_id = persist_payload["persisted_runs"][0]["run_id"]

    listed = _run_simulator(
        [
            "--list-runs",
            "--run-model",
            "utxo",
            "--limit",
            "5",
            "--json",
            "--store-dir",
            str(store_dir),
        ],
        cwd=repo_root,
    )
    assert listed.returncode == 0, listed.stderr
    listed_payload = json.loads(listed.stdout)
    assert len(listed_payload) >= 1
    assert listed_payload[0]["run_id"] == run_id
    assert listed_payload[0]["source_model"] == "utxo"

    shown = _run_simulator(
        [
            "--show-run-id",
            run_id,
            "--run-model",
            "utxo",
            "--json",
            "--store-dir",
            str(store_dir),
        ],
        cwd=repo_root,
    )
    assert shown.returncode == 0, shown.stderr
    shown_payload = json.loads(shown.stdout)
    assert shown_payload["run_id"] == run_id
    assert shown_payload["payload"]["model"] == "utxo"
    assert shown_payload["source_model"] == "utxo"
