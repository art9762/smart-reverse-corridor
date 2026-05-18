"""Storage backends: SQLite (events + config) and InfluxDB (metrics).

Both backends are best-effort: failures are logged and swallowed so the
controller keeps running when external storage is unavailable.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

import structlog

log = structlog.get_logger("storage")


class SQLiteStore:
    """Tiny thread-safe SQLite wrapper for events and config."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._ensure_dir()
        self._init_schema()

    def _ensure_dir(self) -> None:
        d = os.path.dirname(self.path) or "."
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as exc:
            log.warning("sqlite.mkdir_failed", path=d, error=str(exc))

    @contextmanager
    def _conn(self):
        with self._lock:
            con = sqlite3.connect(self.path, timeout=5)
            con.row_factory = sqlite3.Row
            try:
                yield con
                con.commit()
            finally:
                con.close()

    def _init_schema(self) -> None:
        try:
            with self._conn() as con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        kind TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS config_kv (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)"
                )
        except sqlite3.Error as exc:
            log.warning("sqlite.init_failed", error=str(exc))

    def log_event(self, kind: str, payload: Dict[str, Any]) -> None:
        try:
            with self._conn() as con:
                con.execute(
                    "INSERT INTO events(ts, kind, payload) VALUES (?, ?, ?)",
                    (time.time(), kind, json.dumps(payload, default=str)),
                )
        except sqlite3.Error as exc:
            log.warning("sqlite.log_event_failed", kind=kind, error=str(exc))

    def get_config(self, key: str) -> Optional[str]:
        try:
            with self._conn() as con:
                row = con.execute(
                    "SELECT value FROM config_kv WHERE key = ?", (key,)
                ).fetchone()
                return row["value"] if row else None
        except sqlite3.Error as exc:
            log.warning("sqlite.get_config_failed", key=key, error=str(exc))
            return None

    def set_config(self, key: str, value: str) -> None:
        try:
            with self._conn() as con:
                con.execute(
                    """
                    INSERT INTO config_kv(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        updated_at=excluded.updated_at
                    """,
                    (key, value, time.time()),
                )
        except sqlite3.Error as exc:
            log.warning("sqlite.set_config_failed", key=key, error=str(exc))


class InfluxWriter:
    """Optional InfluxDB sink for tick metrics.

    The constructor never raises — if `influxdb_client` is unavailable
    or the connection fails, writes degrade to no-ops.
    """

    def __init__(
        self,
        url: Optional[str],
        token: Optional[str],
        org: Optional[str],
        bucket: Optional[str],
    ) -> None:
        self.enabled = bool(url and token and org and bucket)
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client = None
        self._write_api = None
        if not self.enabled:
            log.info("influx.disabled")
            return
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            self._client = InfluxDBClient(url=url, token=token, org=org)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            log.info("influx.connected", url=url, bucket=bucket)
        except Exception as exc:  # pragma: no cover - depends on remote
            log.warning("influx.connect_failed", error=str(exc))
            self.enabled = False

    def write_metrics(self, measurement: str, fields: Dict[str, Any],
                      tags: Optional[Dict[str, str]] = None) -> None:
        if not self.enabled or self._write_api is None:
            return
        try:
            from influxdb_client import Point

            p = Point(measurement)
            for k, v in (tags or {}).items():
                p.tag(k, v)
            for k, v in fields.items():
                if v is None:
                    continue
                p.field(k, v)
            self._write_api.write(bucket=self.bucket, org=self.org, record=p)
        except Exception as exc:  # pragma: no cover - depends on remote
            log.warning("influx.write_failed", error=str(exc))

    def write_many(self, points: Iterable[Any]) -> None:
        if not self.enabled or self._write_api is None:
            return
        try:
            self._write_api.write(bucket=self.bucket, org=self.org, record=list(points))
        except Exception as exc:  # pragma: no cover
            log.warning("influx.write_many_failed", error=str(exc))

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
        except Exception:  # pragma: no cover
            pass
