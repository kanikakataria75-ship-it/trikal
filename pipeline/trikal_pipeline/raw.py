"""Raw zone: content-addressed, immutable copies of every fetched byte (ARCHITECTURE §3.1).

The SHA-256 is computed over the bytes exactly as received. Uncompressed payloads are gzip-wrapped
on disk to save space; `read()` always returns the original bytes.

The raw index lives in SQLite (WAL) rather than the canonical DuckDB file so that several fetchers
can run as separate processes while parsing/loading proceeds (ADR-010).
"""

from __future__ import annotations

import gzip
import hashlib
import sqlite3
from pathlib import Path

from trikal_core.db import data_dir
from trikal_core.timeutil import utcnow

_COMPRESSED_MAGIC = (b"PK\x03\x04", b"\x1f\x8b", b"%PDF")

_DDL = """
CREATE TABLE IF NOT EXISTS raw_object (
    sha256 TEXT PRIMARY KEY, source_key TEXT NOT NULL, url TEXT NOT NULL, fetched_at TEXT NOT NULL,
    n_bytes INTEGER NOT NULL, content_type TEXT, path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fetch_log (
    source_key TEXT NOT NULL, partition_key TEXT NOT NULL, url TEXT NOT NULL, attempted_at TEXT NOT NULL,
    status TEXT NOT NULL,            -- ok | not_found | error
    http_status INTEGER, sha256 TEXT, note TEXT
);
CREATE INDEX IF NOT EXISTS fetch_log_sp ON fetch_log (source_key, partition_key);
"""


class RawStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_dir() / "raw"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "index.sqlite", timeout=60, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(_DDL)

    def put(self, source_key: str, url: str, body: bytes, content_type: str | None, ext: str) -> str:
        sha = hashlib.sha256(body).hexdigest()
        if self.db.execute("SELECT 1 FROM raw_object WHERE sha256 = ?", (sha,)).fetchone():
            return sha
        wrap = not body.startswith(_COMPRESSED_MAGIC)
        rel = Path(source_key) / sha[:2] / f"{sha}.{ext}{'.gz' if wrap else ''}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(gzip.compress(body, compresslevel=6) if wrap else body)
        tmp.replace(path)
        self.db.execute(
            "INSERT OR IGNORE INTO raw_object VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sha, source_key, url, utcnow().isoformat(), len(body), content_type, rel.as_posix()),
        )
        return sha

    def read(self, sha: str) -> bytes:
        row = self.db.execute("SELECT path FROM raw_object WHERE sha256 = ?", (sha,)).fetchone()
        if not row:
            raise KeyError(sha)
        data = (self.root / row[0]).read_bytes()
        return gzip.decompress(data) if row[0].endswith(".gz") else data

    def log(self, source_key: str, partition: str, url: str, status: str,
            http_status: int | None, sha: str | None, note: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO fetch_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (source_key, partition, url, utcnow().isoformat(), status, http_status, sha, note),
        )

    def latest_ok(self, source_key: str) -> dict[str, str]:
        """partition -> sha of the most recent successful fetch."""
        rows = self.db.execute(
            """SELECT partition_key, sha256 FROM fetch_log f
               WHERE source_key = ? AND status = 'ok'
                 AND attempted_at = (SELECT MAX(attempted_at) FROM fetch_log g
                                     WHERE g.source_key = f.source_key AND g.partition_key = f.partition_key
                                       AND g.status = 'ok')""",
            (source_key,),
        ).fetchall()
        return {p: s for p, s in rows}

    def done_partitions(self, source_key: str) -> set[str]:
        """Partitions with a definitive answer (ok, or not_found which we read as 'no file that day')."""
        rows = self.db.execute(
            "SELECT DISTINCT partition_key FROM fetch_log WHERE source_key = ? AND status IN ('ok','not_found')",
            (source_key,),
        ).fetchall()
        return {r[0] for r in rows}

    def status_counts(self) -> list[tuple]:
        return self.db.execute(
            """SELECT source_key, status, COUNT(DISTINCT partition_key), MIN(partition_key), MAX(partition_key)
               FROM fetch_log GROUP BY 1, 2 ORDER BY 1, 2"""
        ).fetchall()
