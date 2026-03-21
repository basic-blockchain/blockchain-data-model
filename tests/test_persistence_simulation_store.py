from pathlib import Path

from persistence.simulation_store import JsonSimulationStore


def test_store_save_list_get_roundtrip(tmp_path):
    store_file: Path = tmp_path / "utxo-runs.json"
    store = JsonSimulationStore(store_file)

    run_payload = {
        "model": "utxo",
        "scenario": "retail-payments",
        "requested_model": "utxo",
        "results": [{"model": "utxo", "events": ["ok"]}],
    }

    run_id = store.save_run(run_payload)
    assert run_id.startswith("run-")
    assert store_file.exists()

    summary = store.list_runs(limit=10)
    assert len(summary) == 1
    assert summary[0]["run_id"] == run_id
    assert summary[0]["model"] == "utxo"
    assert summary[0]["scenario"] == "retail-payments"

    run = store.get_run(run_id)
    assert run is not None
    assert run["payload"]["model"] == "utxo"
    assert run["payload"]["results"][0]["events"] == ["ok"]


def test_store_list_runs_reverse_chronological(tmp_path):
    store_file: Path = tmp_path / "account-runs.json"
    store = JsonSimulationStore(store_file)

    first = store.save_run({"model": "account", "scenario": "coffee-export", "results": []})
    second = store.save_run({"model": "account", "scenario": "retail-payments", "results": []})

    summary = store.list_runs(limit=2)
    assert [summary[0]["run_id"], summary[1]["run_id"]] == [second, first]
