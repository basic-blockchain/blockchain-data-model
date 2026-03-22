"""PostgreSQL implementation of WalletLedgerRepository."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.interfaces import WalletLedgerRepository
from persistence.pg_connection import get_connection


class PgMultiUserWalletStore(WalletLedgerRepository):

    def load_ledger(self) -> MultiUserWalletLedger:
        snapshot = self._read_snapshot()
        return MultiUserWalletLedger.from_snapshot(snapshot)

    def save_ledger(self, ledger: MultiUserWalletLedger) -> str:
        snapshot = ledger.state_snapshot()
        revision_id = self._generate_revision_id()

        with get_connection() as conn:
            with conn.cursor() as cur:
                self._upsert_users(cur, snapshot.get("users", []))
                self._upsert_wallets(cur, snapshot.get("wallets", []))
                self._upsert_policies(cur, snapshot.get("policies", []))
                self._upsert_risk_profiles(cur, snapshot.get("risk_profiles", []))
                self._sync_utxos(cur, snapshot.get("utxos", []))
                self._sync_transfers(cur, snapshot.get("transfers", []))
                self._sync_alerts(cur, snapshot.get("alerts", []))
                self._sync_nonces(cur, ledger)
                self._upsert_credentials(cur, snapshot.get("credentials", []))
                self._sync_roles(cur, snapshot.get("roles", []))
                self._insert_revision(cur, revision_id, snapshot)

        return revision_id

    def list_revisions(self, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT revision_id, created_at, user_count,
                           wallet_count, transfer_count
                    FROM ledger_revisions
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            {
                "revision_id": row[0],
                "created_at": row[1].isoformat() if row[1] else "",
                "users": row[2],
                "wallets": row[3],
                "transfers": row[4],
            }
            for row in rows
        ]

    # ── Snapshot reconstruction ──────────────────────────────

    def _read_snapshot(self) -> dict:
        with get_connection() as conn:
            with conn.cursor() as cur:
                users = self._fetch_users(cur)
                wallets = self._fetch_wallets(cur)
                policies = self._fetch_policies(cur)
                risk_profiles = self._fetch_risk_profiles(cur)
                utxos = self._fetch_utxos(cur)
                transfers = self._fetch_transfers(cur)
                alerts = self._fetch_alerts(cur)
                credentials = self._fetch_credentials(cur)
                roles = self._fetch_roles(cur)

        return {
            "users": users,
            "wallets": wallets,
            "policies": policies,
            "risk_profiles": risk_profiles,
            "utxos": utxos,
            "transfers": transfers,
            "alerts": alerts,
            "credentials": credentials,
            "roles": roles,
        }

    def _fetch_users(self, cur) -> list[dict]:
        cur.execute("SELECT user_id, display_name, created_at FROM users ORDER BY created_at")
        return [
            {
                "user_id": r[0],
                "display_name": r[1],
                "created_at": r[2].isoformat() if r[2] else "",
                "wallet_ids": [],
            }
            for r in cur.fetchall()
        ]

    def _fetch_wallets(self, cur) -> list[dict]:
        cur.execute(
            """
            SELECT wallet_id, user_id, model, currency, balance,
                   auth_token, token_issued_at, token_expires_at, created_at
            FROM wallets ORDER BY created_at
            """
        )
        return [
            {
                "wallet_id": r[0],
                "user_id": r[1],
                "model": r[2],
                "currency": r[3],
                "balance": str(r[4]),
                "utxo_count": 0,
                "auth_token": r[5],
                "token_issued_at": r[6],
                "token_expires_at": r[7],
                "created_at": r[8].isoformat() if r[8] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_policies(self, cur) -> list[dict]:
        cur.execute("SELECT user_id, can_transfer, daily_limit, updated_at FROM user_policies")
        return [
            {
                "user_id": r[0],
                "can_transfer": r[1],
                "daily_limit": str(r[2]) if r[2] is not None else None,
                "updated_at": r[3].isoformat() if r[3] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_risk_profiles(self, cur) -> list[dict]:
        cur.execute(
            """
            SELECT user_id, profile_name, daily_limit,
                   transfer_alert_threshold, daily_alert_threshold, updated_at
            FROM user_risk_profiles
            """
        )
        return [
            {
                "user_id": r[0],
                "profile_name": r[1],
                "daily_limit": str(r[2]) if r[2] is not None else None,
                "transfer_alert_threshold": str(r[3]) if r[3] is not None else None,
                "daily_alert_threshold": str(r[4]) if r[4] is not None else None,
                "updated_at": r[5].isoformat() if r[5] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_utxos(self, cur) -> list[dict]:
        cur.execute(
            "SELECT utxo_id, wallet_id, currency, amount, source, created_at FROM wallet_utxos"
        )
        return [
            {
                "utxo_id": r[0],
                "wallet_id": r[1],
                "currency": r[2],
                "amount": str(r[3]),
                "source": r[4],
                "created_at": r[5].isoformat() if r[5] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_transfers(self, cur) -> list[dict]:
        cur.execute(
            """
            SELECT transfer_id, type, sender_wallet, receiver_wallet,
                   amount, fee, nonce, previous_hash, tx_hash,
                   reference, status, created_at
            FROM transfers ORDER BY created_at
            """
        )
        return [
            {
                "transfer_id": r[0],
                "type": r[1],
                "sender_wallet": r[2] or "",
                "receiver_wallet": r[3],
                "amount": str(r[4]),
                "fee": str(r[5]),
                "nonce": r[6],
                "previous_hash": r[7] or "",
                "tx_hash": r[8] or "",
                "reference": r[9],
                "status": r[10],
                "created_at": r[11].isoformat() if r[11] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_alerts(self, cur) -> list[dict]:
        cur.execute(
            """
            SELECT alert_id, user_id, profile_name, type, severity,
                   threshold, observed, transfer_id, created_at
            FROM alerts ORDER BY created_at
            """
        )
        return [
            {
                "alert_id": r[0],
                "user_id": r[1],
                "profile_name": r[2],
                "type": r[3],
                "severity": r[4],
                "threshold": str(r[5]),
                "observed": str(r[6]),
                "transfer_id": r[7],
                "created_at": r[8].isoformat() if r[8] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_credentials(self, cur) -> list[dict]:
        cur.execute("SELECT user_id, password_hash, created_at, updated_at FROM user_credentials")
        return [
            {
                "user_id": r[0],
                "password_hash": r[1],
                "created_at": r[2].isoformat() if r[2] else "",
                "updated_at": r[3].isoformat() if r[3] else "",
            }
            for r in cur.fetchall()
        ]

    def _fetch_roles(self, cur) -> list[dict]:
        cur.execute("SELECT user_id, role, granted_at FROM user_roles")
        return [
            {
                "user_id": r[0],
                "role": r[1],
                "granted_at": r[2].isoformat() if r[2] else "",
            }
            for r in cur.fetchall()
        ]

    # ── Upsert / Sync helpers ────────────────────────────────

    def _upsert_users(self, cur, users: list[dict]) -> None:
        for u in users:
            cur.execute(
                """
                INSERT INTO users (user_id, display_name, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name
                """,
                (u["user_id"], u["display_name"], u.get("created_at")),
            )

    def _upsert_wallets(self, cur, wallets: list[dict]) -> None:
        for w in wallets:
            cur.execute(
                """
                INSERT INTO wallets (wallet_id, user_id, model, currency,
                                     balance, auth_token, token_issued_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (wallet_id) DO UPDATE SET
                    balance = EXCLUDED.balance,
                    auth_token = EXCLUDED.auth_token,
                    token_issued_at = EXCLUDED.token_issued_at
                """,
                (
                    w["wallet_id"], w["user_id"], w["model"], w["currency"],
                    w["balance"], w["auth_token"], w["token_issued_at"],
                    w.get("created_at"),
                ),
            )

    def _upsert_policies(self, cur, policies: list[dict]) -> None:
        for p in policies:
            cur.execute(
                """
                INSERT INTO user_policies (user_id, can_transfer, daily_limit, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    can_transfer = EXCLUDED.can_transfer,
                    daily_limit = EXCLUDED.daily_limit,
                    updated_at = EXCLUDED.updated_at
                """,
                (p["user_id"], p["can_transfer"], p.get("daily_limit"), p.get("updated_at")),
            )

    def _upsert_risk_profiles(self, cur, profiles: list[dict]) -> None:
        for rp in profiles:
            cur.execute(
                """
                INSERT INTO user_risk_profiles
                    (user_id, profile_name, daily_limit,
                     transfer_alert_threshold, daily_alert_threshold, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    profile_name = EXCLUDED.profile_name,
                    daily_limit = EXCLUDED.daily_limit,
                    transfer_alert_threshold = EXCLUDED.transfer_alert_threshold,
                    daily_alert_threshold = EXCLUDED.daily_alert_threshold,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    rp["user_id"], rp["profile_name"], rp.get("daily_limit"),
                    rp.get("transfer_alert_threshold"), rp.get("daily_alert_threshold"),
                    rp.get("updated_at"),
                ),
            )

    def _sync_utxos(self, cur, utxos: list[dict]) -> None:
        cur.execute("DELETE FROM wallet_utxos")
        for u in utxos:
            cur.execute(
                """
                INSERT INTO wallet_utxos (utxo_id, wallet_id, currency, amount, source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (u["utxo_id"], u["wallet_id"], u["currency"], u["amount"], u["source"], u.get("created_at")),
            )

    def _sync_transfers(self, cur, transfers: list[dict]) -> None:
        cur.execute("DELETE FROM transfers")
        for t in transfers:
            cur.execute(
                """
                INSERT INTO transfers
                    (transfer_id, type, sender_wallet, receiver_wallet,
                     amount, fee, nonce, previous_hash, tx_hash,
                     reference, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    t["transfer_id"], t["type"],
                    t.get("sender_wallet") or None,
                    t["receiver_wallet"],
                    t["amount"], t["fee"], t.get("nonce"),
                    t.get("previous_hash") or None,
                    t.get("tx_hash") or None,
                    t.get("reference", ""), t.get("status", "SETTLED"),
                    t.get("created_at"),
                ),
            )

    def _sync_alerts(self, cur, alerts: list[dict]) -> None:
        cur.execute("DELETE FROM alerts")
        for a in alerts:
            cur.execute(
                """
                INSERT INTO alerts
                    (alert_id, user_id, profile_name, type, severity,
                     threshold, observed, transfer_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    a["alert_id"], a["user_id"], a["profile_name"],
                    a["type"], a["severity"],
                    a["threshold"], a["observed"],
                    a["transfer_id"], a.get("created_at"),
                ),
            )

    def _sync_nonces(self, cur, ledger: MultiUserWalletLedger) -> None:
        cur.execute("DELETE FROM wallet_nonces")
        for wallet_id, nonce in ledger.wallet_nonces.items():
            cur.execute(
                """
                INSERT INTO wallet_nonces (wallet_id, current_nonce)
                VALUES (%s, %s)
                """,
                (wallet_id, nonce),
            )

    def _upsert_credentials(self, cur, credentials: list[dict]) -> None:
        for c in credentials:
            if not c.get("password_hash"):
                continue
            cur.execute(
                """
                INSERT INTO user_credentials (user_id, password_hash, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    updated_at = EXCLUDED.updated_at
                """,
                (c["user_id"], c["password_hash"], c.get("created_at"), c.get("updated_at")),
            )

    def _sync_roles(self, cur, roles: list[dict]) -> None:
        cur.execute("DELETE FROM user_roles")
        for r in roles:
            cur.execute(
                """
                INSERT INTO user_roles (user_id, role, granted_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, role) DO NOTHING
                """,
                (r["user_id"], r["role"], r.get("granted_at")),
            )

    def _insert_revision(self, cur, revision_id: str, snapshot: dict) -> None:
        cur.execute(
            """
            INSERT INTO ledger_revisions (revision_id, user_count, wallet_count, transfer_count)
            VALUES (%s, %s, %s, %s)
            """,
            (
                revision_id,
                len(snapshot.get("users", [])),
                len(snapshot.get("wallets", [])),
                len(snapshot.get("transfers", [])),
            ),
        )

    # ── Utilities ────────────────────────────────────────────

    @staticmethod
    def _generate_revision_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"rev-{stamp}-{secrets.token_hex(4)}"
