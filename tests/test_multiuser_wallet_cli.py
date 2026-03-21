import json
import subprocess
import sys
from pathlib import Path


def _run_cli(args, cwd: Path):
    cmd = [sys.executable, "scripts/multiuser_wallet_cli.py", *args]
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return completed


def test_cli_accepts_json_flag_before_subcommand(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    out = _run_cli(
        [
            "--json",
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["success"] is True


def test_cli_accepts_json_flag_after_subcommand(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    )

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "list-users",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["success"] is True
    assert len(payload["result"]) == 1


def test_cli_returns_non_zero_on_domain_error(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "transfer",
            "--from-wallet",
            "w-a",
            "--to-wallet",
            "w-b",
            "--amount",
            "10",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 1
    payload = json.loads(out.stdout)
    assert payload["success"] is False


def test_cli_policy_commands_and_transfer_block(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u2",
            "--display-name",
            "User Two",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "create-wallet", "--user-id", "u1", "--wallet-id", "w1"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "create-wallet", "--user-id", "u2", "--wallet-id", "w2"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "mint", "--wallet-id", "w1", "--amount", "15"],
        cwd=repo_root,
    ).returncode == 0

    set_policy = _run_cli(
        [
            "--store-file",
            str(store_file),
            "set-policy",
            "--user-id",
            "u1",
            "--can-transfer",
            "false",
            "--json",
        ],
        cwd=repo_root,
    )
    assert set_policy.returncode == 0, set_policy.stderr

    get_policy = _run_cli(
        ["--store-file", str(store_file), "get-policy", "--user-id", "u1", "--json"],
        cwd=repo_root,
    )
    payload = json.loads(get_policy.stdout)
    assert payload["success"] is True
    assert payload["result"]["can_transfer"] is False

    blocked_transfer = _run_cli(
        [
            "--store-file",
            str(store_file),
            "transfer",
            "--from-wallet",
            "w1",
            "--to-wallet",
            "w2",
            "--amount",
            "5",
            "--json",
        ],
        cwd=repo_root,
    )
    assert blocked_transfer.returncode == 1
    blocked_payload = json.loads(blocked_transfer.stdout)
    assert blocked_payload["success"] is False


def test_cli_risk_profile_and_alerts_commands(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--user-id",
            "u2",
            "--display-name",
            "User Two",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "create-wallet", "--user-id", "u1", "--wallet-id", "w1"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "create-wallet", "--user-id", "u2", "--wallet-id", "w2"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "mint", "--wallet-id", "w1", "--amount", "20"],
        cwd=repo_root,
    ).returncode == 0

    set_risk = _run_cli(
        [
            "--store-file",
            str(store_file),
            "set-risk-profile",
            "--user-id",
            "u1",
            "--profile-name",
            "HIGH",
            "--transfer-alert-threshold",
            "5",
            "--daily-alert-threshold",
            "8",
            "--json",
        ],
        cwd=repo_root,
    )
    assert set_risk.returncode == 0, set_risk.stderr

    get_risk = _run_cli(
        ["--store-file", str(store_file), "get-risk-profile", "--user-id", "u1", "--json"],
        cwd=repo_root,
    )
    risk_payload = json.loads(get_risk.stdout)
    assert risk_payload["success"] is True
    assert risk_payload["result"]["profile_name"] == "HIGH"
    assert risk_payload["result"]["transfer_alert_threshold"] == "5.00000000"

    transfer = _run_cli(
        [
            "--store-file",
            str(store_file),
            "transfer",
            "--from-wallet",
            "w1",
            "--to-wallet",
            "w2",
            "--amount",
            "6",
            "--json",
        ],
        cwd=repo_root,
    )
    assert transfer.returncode == 0, transfer.stderr

    alerts = _run_cli(
        ["--store-file", str(store_file), "list-alerts", "--user-id", "u1", "--json"],
        cwd=repo_root,
    )
    alerts_payload = json.loads(alerts.stdout)
    assert alerts_payload["success"] is True
    assert len(alerts_payload["result"]) == 1
    assert alerts_payload["result"][0]["type"] == "TRANSFER_THRESHOLD"
