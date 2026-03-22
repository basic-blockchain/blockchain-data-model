"""PostgreSQL implementation of WalletLedgerRepository."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.interfaces import WalletLedgerRepository
from persistence.pg_connection import get_connection


class PgMultiUserWalletStore(WalletLedgerRepository):

    REQUIRED_TABLES = (
        "users",
        "wallets",
        "user_policies",
        "user_risk_profiles",
        "wallet_nonces",
        "wallet_utxos",
        "transfers",
        "alerts",
        "ledger_revisions",
    )

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
                # Backward compatibility: old PG schemas may not have auth/RBAC tables yet.
                if self._table_exists(cur, "user_credentials"):
                    self._upsert_credentials(cur, snapshot.get("credentials", []))
                if self._table_exists(cur, "user_roles"):
                    self._sync_roles(cur, snapshot.get("roles", []))
                if self._table_exists(cur, "admin_invitation_tokens"):
                    self._sync_invitation_tokens(cur, snapshot.get("admin_invitation_tokens", []))
                if self._table_exists(cur, "activation_codes"):
                    self._sync_activation_codes(cur, snapshot.get("activation_codes", []))
                if self._table_exists(cur, "exchange_rates"):
                    self._sync_exchange_rates(cur, snapshot.get("exchange_rates", []))
                if self._table_exists(cur, "role_permissions"):
                    self._sync_role_permission_overrides(cur, snapshot.get("role_permission_overrides", {}))
                if self._table_exists(cur, "user_permissions"):
                    self._sync_user_permission_overrides(cur, snapshot.get("user_permission_overrides", {}))
                if self._table_exists(cur, "audit_log"):
                    self._sync_audit_log(cur, snapshot.get("audit_log", []))
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
                missing_required = [name for name in self.REQUIRED_TABLES if not self._table_exists(cur, name)]
                if missing_required:
                    missing = ", ".join(missing_required)
                    raise RuntimeError(
                        "Esquema PostgreSQL incompleto. Faltan tablas requeridas: "
                        f"{missing}. Ejecuta: PYTHONPATH=. py migrations/migrate.py"
                    )
                users = self._fetch_users(cur)
                wallets = self._fetch_wallets(cur)
                policies = self._fetch_policies(cur)
                risk_profiles = self._fetch_risk_profiles(cur)
                utxos = self._fetch_utxos(cur)
                transfers = self._fetch_transfers(cur)
                alerts = self._fetch_alerts(cur)
                if self._table_exists(cur, "user_credentials"):
                    credentials = self._fetch_credentials(cur)
                else:
                    credentials = []
                if self._table_exists(cur, "user_roles"):
                    roles = self._fetch_roles(cur)
                else:
                    roles = []
                if self._table_exists(cur, "admin_invitation_tokens"):
                    invitation_tokens = self._fetch_invitation_tokens(cur)
                else:
                    invitation_tokens = []
                if self._table_exists(cur, "activation_codes"):
                    activation_codes = self._fetch_activation_codes(cur)
                else:
                    activation_codes = []
                if self._table_exists(cur, "exchange_rates"):
                    exchange_rates = self._fetch_exchange_rates(cur)
                else:
                    exchange_rates = []
                if self._table_exists(cur, "role_permissions"):
                    role_permission_overrides = self._fetch_role_permission_overrides(cur)
                else:
                    role_permission_overrides = {}
                if self._table_exists(cur, "user_permissions"):
                    user_permission_overrides = self._fetch_user_permission_overrides(cur)
                else:
                    user_permission_overrides = {}
                if self._table_exists(cur, "audit_log"):
                    audit_log = self._fetch_audit_log(cur)
                else:
                    audit_log = []

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
            "admin_invitation_tokens": invitation_tokens,
            "activation_codes": activation_codes,
            "exchange_rates": exchange_rates,
            "role_permission_overrides": role_permission_overrides,
            "user_permission_overrides": user_permission_overrides,
            "audit_log": audit_log,
        }

    def _fetch_users(self, cur) -> list[dict]:
        has_banned = self._column_exists(cur, "users", "banned")
        has_updated = self._column_exists(cur, "users", "updated_at")
        has_deleted = self._column_exists(cur, "users", "deleted_at")
        has_profile = self._column_exists(cur, "users", "first_name")
        cols = ["user_id", "display_name", "created_at"]
        if has_banned:
            cols.append("banned")
        if has_updated:
            cols.append("updated_at")
        if has_deleted:
            cols.append("deleted_at")
        if has_profile:
            cols.extend(["first_name", "last_name", "email", "username"])
        cur.execute(f"SELECT {', '.join(cols)} FROM users ORDER BY created_at")
        results = []
        for r in cur.fetchall():
            rec = {
                "user_id": r[0],
                "display_name": r[1],
                "created_at": r[2].isoformat() if r[2] else "",
                "wallet_ids": [],
            }
            idx = 3
            if has_banned:
                rec["banned"] = bool(r[idx]); idx += 1
            if has_updated:
                rec["updated_at"] = r[idx].isoformat() if r[idx] else ""; idx += 1
            if has_deleted:
                rec["deleted_at"] = r[idx].isoformat() if r[idx] else ""; idx += 1
            if has_profile:
                rec["first_name"] = r[idx] or ""; idx += 1
                rec["last_name"] = r[idx] or ""; idx += 1
                rec["email"] = r[idx] or ""; idx += 1
                rec["username"] = r[idx] or ""; idx += 1
            results.append(rec)
        return results

    def _fetch_wallets(self, cur) -> list[dict]:
        has_frozen = self._column_exists(cur, "wallets", "frozen")
        if has_frozen:
            cur.execute(
                """
                SELECT wallet_id, user_id, model, currency, balance,
                       auth_token, token_issued_at, token_expires_at, created_at, frozen
                FROM wallets ORDER BY created_at
                """
            )
        else:
            cur.execute(
                """
                SELECT wallet_id, user_id, model, currency, balance,
                       auth_token, token_issued_at, token_expires_at, created_at
                FROM wallets ORDER BY created_at
                """
            )
        results = []
        for r in cur.fetchall():
            rec = {
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
            if has_frozen:
                rec["frozen"] = bool(r[9])
            results.append(rec)
        return results

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
        has_exchange_cols = self._column_exists(cur, "transfers", "sender_currency")
        if has_exchange_cols:
            cur.execute(
                """
                SELECT transfer_id, type, sender_wallet, receiver_wallet,
                       amount, fee, nonce, previous_hash, tx_hash,
                       reference, status, created_at,
                       sender_currency, receiver_currency,
                       exchange_rate, exchange_commission, converted_amount
                FROM transfers ORDER BY created_at
                """
            )
        else:
            cur.execute(
                """
                SELECT transfer_id, type, sender_wallet, receiver_wallet,
                       amount, fee, nonce, previous_hash, tx_hash,
                       reference, status, created_at
                FROM transfers ORDER BY created_at
                """
            )
        results = []
        for r in cur.fetchall():
            rec = {
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
            if has_exchange_cols:
                if r[12]:
                    rec["sender_currency"] = r[12]
                if r[13]:
                    rec["receiver_currency"] = r[13]
                if r[14] is not None:
                    rec["exchange_rate"] = str(r[14])
                if r[15] is not None:
                    rec["exchange_commission"] = str(r[15])
                if r[16] is not None:
                    rec["converted_amount"] = str(r[16])
            results.append(rec)
        return results

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
        has_temp = self._column_exists(cur, "user_credentials", "password_temp")
        if has_temp:
            cur.execute("SELECT user_id, password_hash, created_at, updated_at, password_temp, token_temp FROM user_credentials")
        else:
            cur.execute("SELECT user_id, password_hash, created_at, updated_at FROM user_credentials")
        results = []
        for r in cur.fetchall():
            rec = {
                "user_id": r[0],
                "password_hash": r[1],
                "created_at": r[2].isoformat() if r[2] else "",
                "updated_at": r[3].isoformat() if r[3] else "",
            }
            if has_temp:
                rec["password_temp"] = bool(r[4])
                rec["token_temp"] = r[5] or ""
            results.append(rec)
        return results

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

    def _fetch_invitation_tokens(self, cur) -> list[dict]:
        cur.execute("SELECT token, created_by, created_at, used, used_by FROM admin_invitation_tokens")
        return [
            {"token": r[0], "created_by": r[1], "created_at": r[2].isoformat() if r[2] else "", "used": r[3], "used_by": r[4] or ""}
            for r in cur.fetchall()
        ]

    def _fetch_activation_codes(self, cur) -> list[dict]:
        cur.execute("SELECT user_id, code, activated, created_at FROM activation_codes")
        return [
            {"user_id": r[0], "code": r[1], "activated": r[2], "created_at": r[3].isoformat() if r[3] else ""}
            for r in cur.fetchall()
        ]

    # ── Upsert / Sync helpers ────────────────────────────────

    def _upsert_users(self, cur, users: list[dict]) -> None:
        has_banned = self._column_exists(cur, "users", "banned")
        has_updated = self._column_exists(cur, "users", "updated_at")
        has_deleted = self._column_exists(cur, "users", "deleted_at")
        for u in users:
            cols = ["user_id", "display_name", "created_at"]
            vals = [u["user_id"], u["display_name"], u.get("created_at")]
            updates = ["display_name = EXCLUDED.display_name"]
            if has_banned:
                cols.append("banned"); vals.append(u.get("banned", False)); updates.append("banned = EXCLUDED.banned")
            if has_updated:
                cols.append("updated_at"); vals.append(u.get("updated_at") or None); updates.append("updated_at = EXCLUDED.updated_at")
            if has_deleted:
                cols.append("deleted_at"); vals.append(u.get("deleted_at") or None); updates.append("deleted_at = EXCLUDED.deleted_at")
            if self._column_exists(cur, "users", "first_name"):
                for field in ("first_name", "last_name", "email", "username"):
                    cols.append(field); vals.append(u.get(field, "")); updates.append(f"{field} = EXCLUDED.{field}")
            placeholders = ", ".join(["%s"] * len(vals))
            col_names = ", ".join(cols)
            update_clause = ", ".join(updates)
            cur.execute(
                f"INSERT INTO users ({col_names}) VALUES ({placeholders}) ON CONFLICT (user_id) DO UPDATE SET {update_clause}",
                vals,
            )

    def _upsert_wallets(self, cur, wallets: list[dict]) -> None:
        has_frozen = self._column_exists(cur, "wallets", "frozen")
        for w in wallets:
            if has_frozen:
                cur.execute(
                    """
                    INSERT INTO wallets (wallet_id, user_id, model, currency,
                                         balance, auth_token, token_issued_at, created_at, frozen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (wallet_id) DO UPDATE SET
                        balance = EXCLUDED.balance,
                        auth_token = EXCLUDED.auth_token,
                        token_issued_at = EXCLUDED.token_issued_at,
                        frozen = EXCLUDED.frozen
                    """,
                    (
                        w["wallet_id"], w["user_id"], w["model"], w["currency"],
                        w["balance"], w["auth_token"], w["token_issued_at"],
                        w.get("created_at"), w.get("frozen", False),
                    ),
                )
            else:
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
        has_exchange_cols = self._column_exists(cur, "transfers", "sender_currency")
        for t in transfers:
            if has_exchange_cols:
                cur.execute(
                    """
                    INSERT INTO transfers
                        (transfer_id, type, sender_wallet, receiver_wallet,
                         amount, fee, nonce, previous_hash, tx_hash,
                         reference, status, created_at,
                         sender_currency, receiver_currency,
                         exchange_rate, exchange_commission, converted_amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)
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
                        t.get("sender_currency"),
                        t.get("receiver_currency"),
                        t.get("exchange_rate"),
                        t.get("exchange_commission"),
                        t.get("converted_amount"),
                    ),
                )
            else:
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
        has_temp = self._column_exists(cur, "user_credentials", "password_temp")
        for c in credentials:
            if not c.get("password_hash"):
                continue
            if has_temp:
                cur.execute(
                    """
                    INSERT INTO user_credentials (user_id, password_hash, created_at, updated_at, password_temp, token_temp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        updated_at = EXCLUDED.updated_at,
                        password_temp = EXCLUDED.password_temp,
                        token_temp = EXCLUDED.token_temp
                    """,
                    (c["user_id"], c["password_hash"], c.get("created_at"), c.get("updated_at"), c.get("password_temp", False), c.get("token_temp", "") or None),
                )
            else:
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

    def _sync_invitation_tokens(self, cur, tokens: list[dict]) -> None:
        cur.execute("DELETE FROM admin_invitation_tokens")
        for t in tokens:
            cur.execute(
                "INSERT INTO admin_invitation_tokens (token, created_by, created_at, used, used_by) VALUES (%s, %s, %s, %s, %s)",
                (t["token"], t["created_by"], t.get("created_at"), t.get("used", False), t.get("used_by", "") or None),
            )

    def _fetch_role_permission_overrides(self, cur) -> dict[str, list[str]]:
        cur.execute("SELECT role, permission_id FROM role_permissions ORDER BY role, permission_id")
        result: dict[str, list[str]] = {}
        for r in cur.fetchall():
            result.setdefault(r[0], []).append(r[1])
        return result

    def _sync_role_permission_overrides(self, cur, overrides: dict[str, list[str]]) -> None:
        cur.execute("DELETE FROM role_permissions")
        for role, perms in overrides.items():
            for perm in perms:
                cur.execute(
                    "INSERT INTO role_permissions (role, permission_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (role, perm),
                )

    def _fetch_user_permission_overrides(self, cur) -> dict[str, list[str]]:
        cur.execute("SELECT user_id, permission_id FROM user_permissions ORDER BY user_id, permission_id")
        result: dict[str, list[str]] = {}
        for r in cur.fetchall():
            result.setdefault(r[0], []).append(r[1])
        return result

    def _sync_user_permission_overrides(self, cur, overrides: dict[str, list[str]]) -> None:
        cur.execute("DELETE FROM user_permissions")
        for user_id, perms in overrides.items():
            for perm in perms:
                cur.execute(
                    "INSERT INTO user_permissions (user_id, permission_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, perm),
                )

    def _fetch_audit_log(self, cur) -> list[dict]:
        cur.execute(
            "SELECT log_id, timestamp, actor_id, action, target_type, target_id, details FROM audit_log ORDER BY timestamp"
        )
        return [
            {
                "log_id": r[0],
                "timestamp": r[1].isoformat() if r[1] else "",
                "actor_id": r[2],
                "action": r[3],
                "target_type": r[4],
                "target_id": r[5],
                "details": r[6] if isinstance(r[6], dict) else {},
            }
            for r in cur.fetchall()
        ]

    def _sync_audit_log(self, cur, logs: list[dict]) -> None:
        for entry in logs:
            import json as _json
            details_val = entry.get("details", {})
            if isinstance(details_val, dict):
                details_val = _json.dumps(details_val)
            cur.execute(
                """
                INSERT INTO audit_log (log_id, timestamp, actor_id, action, target_type, target_id, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (log_id) DO NOTHING
                """,
                (
                    entry["log_id"], entry.get("timestamp"), entry["actor_id"],
                    entry["action"], entry["target_type"], entry["target_id"],
                    details_val,
                ),
            )

    def _fetch_exchange_rates(self, cur) -> list[dict]:
        cur.execute(
            "SELECT pair_id, from_currency, to_currency, rate, commission_pct, updated_at FROM exchange_rates"
        )
        return [
            {
                "pair_id": r[0],
                "from_currency": r[1],
                "to_currency": r[2],
                "rate": str(r[3]),
                "commission_pct": str(r[4]),
                "updated_at": r[5].isoformat() if r[5] else "",
            }
            for r in cur.fetchall()
        ]

    def _sync_exchange_rates(self, cur, rates: list[dict]) -> None:
        cur.execute("DELETE FROM exchange_rates")
        for er in rates:
            cur.execute(
                """
                INSERT INTO exchange_rates (pair_id, from_currency, to_currency, rate, commission_pct, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    er["pair_id"], er["from_currency"], er["to_currency"],
                    er["rate"], er["commission_pct"], er.get("updated_at"),
                ),
            )

    def _sync_activation_codes(self, cur, codes: list[dict]) -> None:
        cur.execute("DELETE FROM activation_codes")
        for c in codes:
            cur.execute(
                "INSERT INTO activation_codes (user_id, code, activated, created_at) VALUES (%s, %s, %s, %s)",
                (c["user_id"], c["code"], c.get("activated", False), c.get("created_at")),
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

    @staticmethod
    def _table_exists(cur, table_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s)", (table_name,))
        return cur.fetchone()[0] is not None

    @staticmethod
    def _column_exists(cur, table_name: str, column_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table_name, column_name),
        )
        return cur.fetchone() is not None
