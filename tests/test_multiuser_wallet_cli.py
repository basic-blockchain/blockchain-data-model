import json
import os
import subprocess
import sys
from pathlib import Path


TEST_JWT_SECRET = "test-secret-key-for-jwt-minimum-32-chars!!"


def _run_cli(args, cwd: Path):
    cmd = [sys.executable, "scripts/multiuser_wallet_cli.py", *args]
    env = os.environ.copy()
    env["PERSISTENCE_BACKEND"] = "json"
    env["PYTHONIOENCODING"] = "utf-8"
    env["JWT_SECRET"] = TEST_JWT_SECRET
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    return completed


def _bootstrap_admin(store_file: str, cwd: Path) -> str:
    """Register first user (becomes ADMIN) and return JWT token."""
    _run_cli(["--store-file", store_file, "register", "--user-id", "admin", "--display-name", "Admin", "--password", "admin123"], cwd=cwd)
    out = _run_cli(["--store-file", store_file, "login", "--user-id", "admin", "--password", "admin123", "--json"], cwd=cwd)
    payload = json.loads(out.stdout)
    return payload["result"]["access_token"]


def test_cli_accepts_json_flag_before_subcommand(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    token = _bootstrap_admin(str(store_file), repo_root)
    out = _run_cli(
        [
            "--json",
            "--store-file",
            str(store_file),
            "--token",
            token,
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

    token = _bootstrap_admin(str(store_file), repo_root)
    _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
            "--token",
            token,
            "list-users",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["success"] is True
    assert len(payload["result"]) == 2


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
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
            "--token",
            token,
            "create-user",
            "--user-id",
            "u2",
            "--display-name",
            "User Two",
        ],
        cwd=repo_root,
    ).returncode == 0
    wallet1 = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    assert wallet1.returncode == 0
    token_u1 = json.loads(wallet1.stdout)["result"]["auth_token"]
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "15"],
        cwd=repo_root,
    ).returncode == 0

    set_policy = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
        ["--store-file", str(store_file), "--token", token, "get-policy", "--user-id", "u1", "--json"],
        cwd=repo_root,
    )
    payload = json.loads(get_policy.stdout)
    assert payload["success"] is True
    assert payload["result"]["can_transfer"] is False

    blocked_transfer = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "5",
            "--sender-token",
            token_u1,
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
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
            "--token",
            token,
            "create-user",
            "--user-id",
            "u2",
            "--display-name",
            "User Two",
        ],
        cwd=repo_root,
    ).returncode == 0
    wallet1 = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    assert wallet1.returncode == 0
    token_u1 = json.loads(wallet1.stdout)["result"]["auth_token"]
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "20"],
        cwd=repo_root,
    ).returncode == 0

    set_risk = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
        ["--store-file", str(store_file), "--token", token, "get-risk-profile", "--user-id", "u1", "--json"],
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
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "6",
            "--sender-token",
            token_u1,
            "--json",
        ],
        cwd=repo_root,
    )
    assert transfer.returncode == 0, transfer.stderr

    alerts = _run_cli(
        ["--store-file", str(store_file), "--token", token, "list-alerts", "--user-id", "u1", "--json"],
        cwd=repo_root,
    )
    alerts_payload = json.loads(alerts.stdout)
    assert alerts_payload["success"] is True
    assert len(alerts_payload["result"]) == 1
    assert alerts_payload["result"][0]["type"] == "TRANSFER_THRESHOLD"


def test_cli_create_wallet_rejects_invalid_wallet_id(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    ).returncode == 0

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "ab",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 1
    payload = json.loads(out.stdout)
    assert payload["success"] is False
    assert "Wallet invalida" in payload["result"]


def test_cli_transfer_requires_sender_token(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
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
            "--token",
            token,
            "create-user",
            "--user-id",
            "u2",
            "--display-name",
            "User Two",
        ],
        cwd=repo_root,
    ).returncode == 0

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "5"],
        cwd=repo_root,
    ).returncode == 0

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "1",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 1
    payload = json.loads(out.stdout)
    assert "sender_token es requerido" in payload["result"]


def test_cli_transfer_rejects_invalid_expected_nonce(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u1", "--display-name", "User One"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u2", "--display-name", "User Two"],
        cwd=repo_root,
    ).returncode == 0

    wallet = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    token_u1 = json.loads(wallet.stdout)["result"]["auth_token"]
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "10"],
        cwd=repo_root,
    ).returncode == 0

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "2",
            "--sender-token",
            token_u1,
            "--expected-nonce",
            "2",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 1
    payload = json.loads(out.stdout)
    assert "nonce inválido" in payload["result"]


def test_cli_verify_integrity_reports_valid_chain(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u1", "--display-name", "User One"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u2", "--display-name", "User Two"],
        cwd=repo_root,
    ).returncode == 0

    wallet = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    token_u1 = json.loads(wallet.stdout)["result"]["auth_token"]
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "10"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "2",
            "--sender-token",
            token_u1,
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    out = _run_cli(
        ["--store-file", str(store_file), "--token", token, "verify-integrity", "--json"],
        cwd=repo_root,
    )
    assert out.returncode == 0
    payload = json.loads(out.stdout)
    assert payload["success"] is True
    assert payload["result"]["valid"] is True


def test_cli_list_transfers_scoped_prevents_non_admin_user_id_override(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    admin_token = _bootstrap_admin(str(store_file), repo_root)

    for user_id in ("alice", "bob", "caro"):
        assert _run_cli(
            [
                "--store-file", str(store_file),
                "--token", admin_token,
                "create-user",
                "--user-id", user_id,
                "--display-name", user_id.title(),
                "--password", "pass123",
            ],
            cwd=repo_root,
        ).returncode == 0

    assert _run_cli(
        ["--store-file", str(store_file), "--token", admin_token, "assign-role", "--user-id", "alice", "--role", "VIEWER"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", admin_token, "assign-role", "--user-id", "bob", "--role", "OPERATOR"],
        cwd=repo_root,
    ).returncode == 0

    bob_wallet = _run_cli(
        [
            "--store-file", str(store_file),
            "--token", admin_token,
            "create-wallet",
            "--user-id", "bob",
            "--wallet-id", "wallet_user_bravo_utxo_02",
            "--json",
        ],
        cwd=repo_root,
    )
    assert bob_wallet.returncode == 0
    bob_sender_token = json.loads(bob_wallet.stdout)["result"]["auth_token"]

    assert _run_cli(
        [
            "--store-file", str(store_file),
            "--token", admin_token,
            "create-wallet",
            "--user-id", "caro",
            "--wallet-id", "wallet_user_carlo_utxo_03",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    assert _run_cli(
        ["--store-file", str(store_file), "--token", admin_token, "mint", "--wallet-id", "wallet_user_bravo_utxo_02", "--amount", "10"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file", str(store_file),
            "--token", admin_token,
            "transfer",
            "--from-wallet", "wallet_user_bravo_utxo_02",
            "--to-wallet", "wallet_user_carlo_utxo_03",
            "--amount", "2",
            "--sender-token", bob_sender_token,
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    alice_login = _run_cli(
        ["--store-file", str(store_file), "login", "--user-id", "alice", "--password", "pass123", "--json"],
        cwd=repo_root,
    )
    assert alice_login.returncode == 0
    alice_token = json.loads(alice_login.stdout)["result"]["access_token"]

    alice_view = _run_cli(
        [
            "--store-file", str(store_file),
            "--token", alice_token,
            "list-transfers",
            "--user-id", "bob",
            "--json",
        ],
        cwd=repo_root,
    )
    assert alice_view.returncode == 0
    alice_payload = json.loads(alice_view.stdout)
    assert alice_payload["success"] is True
    assert alice_payload["result"] == []

    admin_view = _run_cli(
        [
            "--store-file", str(store_file),
            "--token", admin_token,
            "list-transfers",
            "--user-id", "bob",
            "--json",
        ],
        cwd=repo_root,
    )
    assert admin_view.returncode == 0
    admin_payload = json.loads(admin_view.stdout)
    assert admin_payload["success"] is True
    assert len(admin_payload["result"]) >= 1


def test_cli_utxo_model_transfer_and_list_utxos(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u1", "--display-name", "User One"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u2", "--display-name", "User Two"],
        cwd=repo_root,
    ).returncode == 0

    wallet = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--model",
            "UTXO",
            "--json",
        ],
        cwd=repo_root,
    )
    assert wallet.returncode == 0
    token_u1 = json.loads(wallet.stdout)["result"]["auth_token"]

    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_bravo_02",
            "--model",
            "UTXO",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "mint", "--wallet-id", "wallet_user_alpha_01", "--amount", "10"],
        cwd=repo_root,
    ).returncode == 0

    transfer = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "transfer",
            "--from-wallet",
            "wallet_user_alpha_01",
            "--to-wallet",
            "wallet_user_bravo_02",
            "--amount",
            "3",
            "--fee",
            "1",
            "--sender-token",
            token_u1,
            "--json",
        ],
        cwd=repo_root,
    )
    assert transfer.returncode == 0

    utxos = _run_cli(
        ["--store-file", str(store_file), "--token", token, "list-utxos", "--wallet-id", "wallet_user_bravo_02", "--json"],
        cwd=repo_root,
    )
    assert utxos.returncode == 0
    payload = json.loads(utxos.stdout)
    assert payload["success"] is True
    assert len(payload["result"]) == 1
    assert payload["result"][0]["amount"] == "3.00000000"


def test_cli_refresh_token_for_owner(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u1", "--display-name", "User One"],
        cwd=repo_root,
    ).returncode == 0

    wallet = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    assert wallet.returncode == 0
    old_token = json.loads(wallet.stdout)["result"]["auth_token"]

    refreshed = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "refresh-token",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--current-token",
            "DOES_NOT_MATCH",
            "--json",
        ],
        cwd=repo_root,
    )
    assert refreshed.returncode == 0
    payload = json.loads(refreshed.stdout)
    assert payload["success"] is True
    assert payload["result"]["previous_token_matches"] is False
    assert payload["result"]["auth_token"] != old_token


def test_cli_refresh_token_rejects_non_owner(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u1", "--display-name", "User One"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        ["--store-file", str(store_file), "--token", token, "create-user", "--user-id", "u2", "--display-name", "User Two"],
        cwd=repo_root,
    ).returncode == 0
    assert _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-wallet",
            "--user-id",
            "u1",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    ).returncode == 0

    denied = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "refresh-token",
            "--user-id",
            "u2",
            "--wallet-id",
            "wallet_user_alpha_01",
            "--json",
        ],
        cwd=repo_root,
    )
    assert denied.returncode == 1
    payload = json.loads(denied.stdout)
    assert payload["success"] is False
    assert "no es propietario" in payload["result"]


def test_cli_argument_error_is_json_when_json_flag_present(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "create-user",
            "--display-name",
            "Bob",
            "--json",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 2
    payload = json.loads(out.stdout)
    assert payload["success"] is False
    assert payload["error_type"] == "ArgumentError"


def test_cli_non_json_success_uses_visual_success_alert(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "create-user",
            "--user-id",
            "u1",
            "--display-name",
            "User One",
        ],
        cwd=repo_root,
    )
    assert out.returncode == 0
    assert "[SUCCESS] create-user" in out.stdout


def test_cli_non_json_error_alert_message_omits_error_prefix(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    store_file = tmp_path / "wallet-ledger.json"
    token = _bootstrap_admin(str(store_file), repo_root)

    out = _run_cli(
        [
            "--store-file",
            str(store_file),
            "--token",
            token,
            "mint",
            "--wallet-id",
            "wallet_missing",
            "--amount",
            "10",
        ],
        cwd=repo_root,
    )

    assert out.returncode == 1
    assert "[ERROR] mint" in out.stderr
    assert "wallet wallet_missing no existe" in out.stderr
