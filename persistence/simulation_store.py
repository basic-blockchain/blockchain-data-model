from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


from persistence.interfaces import SimulationRunRepository


class JsonSimulationStore(SimulationRunRepository):
    """File-based JSON persistence for simulation runs and movement history."""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    def save_run(self, run_payload: dict) -> str:
        doc = self._load_document()
        run_id = self._generate_run_id()
        created_at = self._timestamp()

        run_record = {
            "run_id": run_id,
            "created_at": created_at,
            "payload": run_payload,
        }

        doc["runs"].append(run_record)
        doc["updated_at"] = created_at
        self._save_document(doc)
        return run_id

    def list_runs(self, limit: int = 20) -> list[dict]:
        doc = self._load_document()
        runs = doc.get("runs", [])
        selected = runs[-limit:] if limit > 0 else runs
        selected = list(reversed(selected))

        summary = []
        for run in selected:
            payload = run.get("payload", {})
            summary.append(
                {
                    "run_id": run.get("run_id"),
                    "created_at": run.get("created_at"),
                    "model": payload.get("model"),
                    "scenario": payload.get("scenario"),
                    "result_count": len(payload.get("results", [])),
                }
            )
        return summary

    def get_run(self, run_id: str) -> dict | None:
        doc = self._load_document()
        for run in doc.get("runs", []):
            if run.get("run_id") == run_id:
                return run
        return None

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
        parsed.setdefault("runs", [])

        if not isinstance(parsed.get("runs"), list):
            parsed["runs"] = []

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
    def _generate_run_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"run-{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _empty_document() -> dict:
        return {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "runs": [],
        }
