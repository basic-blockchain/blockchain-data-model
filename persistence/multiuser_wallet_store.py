from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


class JsonMultiUserWalletStore:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    def load_ledger(self) -> MultiUserWalletLedger:
        doc = self._load_document()
        snapshot = doc.get("snapshot", {})
        return MultiUserWalletLedger.from_snapshot(snapshot)

    def save_ledger(self, ledger: MultiUserWalletLedger) -> str:
        doc = self._load_document()
        revision_id = self._generate_revision_id()
        updated_at = self._timestamp()

        snapshot = ledger.state_snapshot()
        doc["snapshot"] = snapshot
        doc["updated_at"] = updated_at
        doc["current_revision_id"] = revision_id
        doc.setdefault("revisions", []).append(
            {
                "revision_id": revision_id,
                "created_at": updated_at,
                "snapshot": snapshot,
            }
        )

        self._save_document(doc)
        return revision_id

    def list_revisions(self, limit: int = 20) -> list[dict]:
        doc = self._load_document()
        revisions = doc.get("revisions", [])
        selected = revisions[-limit:] if limit > 0 else revisions
        selected = list(reversed(selected))
        return [
            {
                "revision_id": item.get("revision_id"),
                "created_at": item.get("created_at"),
                "users": len(item.get("snapshot", {}).get("users", [])),
                "wallets": len(item.get("snapshot", {}).get("wallets", [])),
                "transfers": len(item.get("snapshot", {}).get("transfers", [])),
            }
            for item in selected
        ]

    def _load_document(self) -> dict:
        if not self.file_path.exists():
            return self._empty_document()

        try:
            raw = self.file_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return self._empty_document()

        if not isinstance(parsed, dict):
            return self._empty_document()

        parsed.setdefault("schema_version", 1)
        parsed.setdefault("updated_at", self._timestamp())
        parsed.setdefault("current_revision_id", "")
        parsed.setdefault("snapshot", {"users": [], "wallets": [], "transfers": []})
        parsed.setdefault("revisions", [])
        if not isinstance(parsed.get("revisions"), list):
            parsed["revisions"] = []
        return parsed

    def _save_document(self, document: dict) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(self.file_path)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _generate_revision_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"rev-{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _empty_document() -> dict:
        return {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "current_revision_id": "",
            "snapshot": {"users": [], "wallets": [], "transfers": []},
            "revisions": [],
        }
