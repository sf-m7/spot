"""Supabase access + run bookkeeping.

Every job opens a scrape_run row and closes it with an explicit status.
'empty' is a first-class status, not a silent success - that is the exact
failure mode that bit Khabar (pipeline green, zero rows, nobody noticed).
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from supabase import Client, create_client

from . import config

_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        if not config.SUPABASE_SERVICE_KEY:
            raise RuntimeError("SPOT_SUPABASE_SERVICE_KEY is not set")
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _client


def payload_hash(payload: dict) -> str:
    """Stable hash so unchanged records are never re-stored (free-tier discipline)."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Run:
    """Handle for one job execution."""

    def __init__(self, run_id: int, job: str):
        self.id = run_id
        self.job = job
        self.rows_seen = 0
        self.rows_new = 0
        self.notes: list[str] = []

    def note(self, msg: str) -> None:
        self.notes.append(msg)
        print(f"[{self.job}] {msg}", flush=True)


@contextmanager
def run(job: str):
    """Open a scrape_run, always close it, never leave it 'running'."""
    res = client().table("scrape_run").insert({"job": job, "status": "running"}).execute()
    r = Run(res.data[0]["id"], job)
    status, error = "ok", None
    try:
        yield r
    except Exception as exc:  # noqa: BLE001 - we want the message persisted
        status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if status == "ok" and r.rows_seen == 0:
            status = "empty"  # loud, not silent
        client().table("scrape_run").update(
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "rows_seen": r.rows_seen,
                "rows_new": r.rows_new,
                "notes": "\n".join(r.notes)[:20000] or None,
                "error": error,
            }
        ).eq("id", r.id).execute()


def store_snapshot(etimad_tender_id: str, source: str, payload: dict) -> bool:
    """Append a raw snapshot. Returns True if it was new (payload actually changed)."""
    row = {
        "etimad_tender_id": etimad_tender_id,
        "source": source,
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }
    try:
        client().table("tender_snapshot").insert(row).execute()
        return True
    except Exception as exc:  # duplicate hash = unchanged record, expected
        if "duplicate key" in str(exc).lower() or "23505" in str(exc):
            return False
        raise
