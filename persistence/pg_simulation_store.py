"""PostgreSQL implementation of SimulationRunRepository."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from persistence.interfaces import SimulationRunRepository
from persistence.pg_connection import get_connection


class _DecimalEncoder(json.JSONEncoder):
    """Encode Decimal values as strings for JSONB storage."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class PgSimulationStore(SimulationRunRepository):

    def save_run(self, run_payload: dict) -> str:
        run_id = self._generate_run_id()
        created_at = self._timestamp()
        model = run_payload.get("model", "unknown")
        scenario = run_payload.get("scenario", "unknown")
        payload_json = json.dumps(run_payload, cls=_DecimalEncoder, ensure_ascii=False)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO simulation_runs (run_id, model, scenario, payload, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    """,
                    (run_id, model, scenario, payload_json, created_at),
                )

        return run_id

    def list_runs(self, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, created_at, payload
                    FROM simulation_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            {
                "run_id": row[0],
                "created_at": row[1].isoformat() if row[1] else "",
                "model": row[2].get("model") if row[2] else None,
                "scenario": row[2].get("scenario") if row[2] else None,
                "result_count": len(row[2].get("results", [])) if row[2] else 0,
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> dict | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, created_at, payload
                    FROM simulation_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return {
            "run_id": row[0],
            "created_at": row[1].isoformat() if row[1] else "",
            "payload": row[2] if row[2] else {},
        }

    @staticmethod
    def _generate_run_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"run-{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
