"""Private, bounded raw-research journal. Never opens application stores on import."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import uuid
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # no thread-only ownership fallback
    fcntl = None

APP_ID = 0x46575231
PARSER_ID = "public-option-contract+strict-research.v2"
DEFAULT_LIMITS = {
    "max_attempts": 8, "max_body_bytes": 1048576, "max_total_body_bytes": 8388608,
    "max_rows": 4000, "max_db_pages": 4096, "max_chunk_bytes": 65536,
    "max_total_read_bytes": 8912896, "request_timeout_s": 5.0, "cycle_timeout_s": 60.0,
}
SENSITIVE = re.compile(
    rb'(?i)(["\x27](?:authorization|authentication|(?:access|refresh|id|session)[_ -]?token|token|(?:x[_ -]?)?api[_ -]?key|(?:client[_ -]?)?secret|password|cookie|credential|account(?:[_ -]?(?:id|number|uuid))?)["\x27]\s*:|bearer\s+)'
)
FILES = {"writer.lock", "manifest.json", "collector.sqlite3", "collector.sqlite3-journal"}
ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
SHA = re.compile(r"[0-9a-f]{64}")


class ResearchRefusal(RuntimeError):
    """Stable non-sensitive refusal code."""


def contains_sensitive(body):
    # Inspect ASCII JSON escapes without replacing the retained original bytes.
    inspected = re.sub(rb"\\u00([0-9a-fA-F]{2})", lambda match: bytes([int(match[1], 16)]), body)
    return bool(SENSITIVE.search(inspected))


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ResearchRefusal("payload_invalid") from None


def validate_manifest(value):
    try:
        value = json.loads(canonical(value))
        if set(value) != {"schema", "parser_id", "symbols", "expiries", "research_only",
                         "trusted_for_admission", "executable", "limits"}:
            raise ValueError
        if (value["schema"] != "public-raw-research.v1" or value["symbols"] != ["SPY", "QQQ"]
                or value["parser_id"] != PARSER_ID
                or value["research_only"] is not True or value["trusted_for_admission"] is not False
                or value["executable"] is not False):
            raise ValueError
        dates = value["expiries"]
        if not isinstance(dates, list) or not 1 <= len(dates) <= 2 or dates != sorted(set(dates)):
            raise ValueError
        for date in dates:
            if not isinstance(date, str) or datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
                raise ValueError
        limits = value["limits"]
        if not isinstance(limits, dict) or set(limits) != set(DEFAULT_LIMITS):
            raise ValueError
        for name, ceiling in DEFAULT_LIMITS.items():
            number = limits[name]
            if name.endswith("_s"):
                if type(number) not in (int, float) or not math.isfinite(number) or not 0 < number <= ceiling:
                    raise ValueError
            elif type(number) is not int or not 0 < number <= ceiling:
                raise ValueError
        if limits["max_db_pages"] < 32:
            raise ValueError
        if limits["max_total_body_bytes"] < limits["max_body_bytes"]:
            raise ValueError
        if limits["max_total_read_bytes"] < limits["max_body_bytes"] + limits["max_chunk_bytes"]:
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError, ResearchRefusal):
        raise ResearchRefusal("manifest_invalid") from None


def _stamp(value, optional=False):
    if value is None and optional:
        return
    try:
        if not isinstance(value, str) or len(value) > 48:
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ResearchRefusal("metadata_invalid") from None


def _safe_json(value, maximum):
    text = canonical(value)
    if len(text.encode()) > maximum or contains_sensitive(text.encode()):
        raise ResearchRefusal("metadata_invalid")
    return text


class ResearchStore:
    """One local writer; the guard inode persists and remains locked until close."""

    def __init__(self, directory, manifest):
        self._manifest = validate_manifest(manifest)
        self._limits = self._manifest["limits"]
        self.directory = Path(directory)
        self._conn = None
        self._guard = None
        self._pending = 0
        self._closing = False
        self.closed = False
        if fcntl is None:
            raise ResearchRefusal("multiprocess_lock_unavailable")
        if not self.directory.is_absolute() or self.directory != self.directory.resolve():
            raise ResearchRefusal("canonical_private_path_required")
        forbidden = [Path(__file__).resolve().parents[2], Path.home() / "Documents/GitHub",
                     Path.home() / "Library/Application Support/FLOWW",
                     Path.home() / ".hermes", Path.home() / ".codex", Path.home() / ".config"]
        if any(self.directory == root or root in self.directory.parents for root in forbidden):
            raise ResearchRefusal("protected_path")
        try:
            self.directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError:
            raise ResearchRefusal("private_directory_unavailable") from None
        info = self.directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ResearchRefusal("private_directory_invalid")
        self._directory_id = (info.st_dev, info.st_ino)
        self._db = self.directory / "collector.sqlite3"
        self._lock = self.directory / "writer.lock"
        self._marker = self.directory / "manifest.json"
        self._check_files()
        fresh = not any(self.directory.iterdir())
        marker = None
        if not fresh:
            if not all(path.is_file() for path in (self._db, self._lock, self._marker)):
                raise ResearchRefusal("foreign_or_incomplete_store")
            marker = self._read_marker()
            if marker.get("manifest") != self._manifest:
                raise ResearchRefusal("manifest_mismatch")
            if marker.get("guard") != self._identity(self._lock):
                raise ResearchRefusal("guard_identity_mismatch")
            if marker.get("database") != self._identity(self._db):
                raise ResearchRefusal("database_identity_mismatch")
            with self._db.open("rb") as stream:
                header = stream.read(100)
            if header[:16] != b"SQLite format 3\0" or int.from_bytes(header[68:72], "big") != APP_ID:
                raise ResearchRefusal("foreign_store")
        try:
            self._guard = os.open(self._lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self._check_file(self._lock)
            try:
                fcntl.flock(self._guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ResearchRefusal("writer_held") from None
            if fresh:
                fd = os.open(self._db, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            self._database_id = self._identity(self._db)
            self._guard_id = self._identity(self._lock)
            self._conn = sqlite3.connect(self._db, timeout=0, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            if fresh:
                self._conn.execute("PRAGMA page_size=4096")
            if self._conn.execute("PRAGMA page_size").fetchone()[0] != 4096:
                raise ResearchRefusal("page_size_unavailable")
            self._conn.execute("PRAGMA journal_mode=DELETE")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA trusted_schema=OFF")
            cap = self._conn.execute("PRAGMA max_page_count=" + str(self._limits["max_db_pages"])).fetchone()[0]
            if cap != self._limits["max_db_pages"]:
                raise ResearchRefusal("page_ceiling_unavailable")
            if fresh:
                with self._transaction(check_marker=False):
                    self._conn.execute("PRAGMA application_id=" + str(APP_ID))
                    for statement in (
                        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                        "CREATE TABLE cycles (cycle_id TEXT PRIMARY KEY, session TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT)",
                        "CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, read_reserved INTEGER NOT NULL, started_at TEXT, response TEXT, body BLOB, body_sha256 TEXT, parsed TEXT)",
                        "CREATE TABLE observations (attempt_id TEXT NOT NULL, row_index INTEGER NOT NULL, value TEXT NOT NULL, PRIMARY KEY(attempt_id,row_index))",
                    ):
                        self._conn.execute(statement)
                    self._conn.execute("INSERT INTO meta VALUES ('manifest',?)", (canonical(self._manifest),))
                marker = {"schema": 1, "manifest": self._manifest,
                          "guard": self._guard_id, "database": self._database_id}
                fd = os.open(self._marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(canonical(marker))
                    stream.flush()
                    os.fsync(stream.fileno())
                fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            else:
                tables = {row[0] for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables != {"meta", "cycles", "attempts", "observations"}:
                    raise ResearchRefusal("foreign_schema")
                if self._conn.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('view','trigger')").fetchone()[0]:
                    raise ResearchRefusal("foreign_schema")
                stored = self._conn.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
                if not stored or stored[0] != canonical(self._manifest):
                    raise ResearchRefusal("manifest_mismatch")
                with self._transaction():
                    for row in self._conn.execute("SELECT cycle_id FROM cycles WHERE status='collecting'").fetchall():
                        receipt = canonical({"cycle_id": row[0], "status": "interrupted",
                                             "research_only": True, "trusted_for_admission": False,
                                             "executable": False, "has_gaps": True})
                        self._conn.execute("UPDATE cycles SET status='interrupted',receipt=? WHERE cycle_id=?", (receipt, row[0]))
                    self._conn.execute("UPDATE attempts SET status='interrupted' WHERE status IN ('reserved','dispatching','raw_committed')")
        except (sqlite3.Error, OSError) as exc:
            self._close_now()
            raise ResearchRefusal("store_unavailable") from exc
        except BaseException:
            self._close_now()
            raise

    @property
    def manifest(self):
        return json.loads(canonical(self._manifest))

    @staticmethod
    def _identity(path):
        info = path.lstat()
        return [info.st_dev, info.st_ino]

    @staticmethod
    def _check_file(path):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ResearchRefusal("unsafe_store_file")

    def _check_files(self):
        for path in self.directory.iterdir():
            if path.name not in FILES:
                raise ResearchRefusal("unexpected_store_file")
            self._check_file(path)

    def _read_marker(self):
        self._check_file(self._marker)
        if self._marker.stat().st_size > 8192:
            raise ResearchRefusal("store_marker_invalid")
        try:
            value = json.loads(self._marker.read_bytes())
        except (ValueError, OSError):
            raise ResearchRefusal("store_marker_invalid") from None
        if not isinstance(value, dict) or set(value) != {"schema", "manifest", "guard", "database"} or value["schema"] != 1:
            raise ResearchRefusal("store_marker_invalid")
        return value

    def _check_owner(self, check_marker=True):
        if self.closed or self._closing:
            raise ResearchRefusal("store_closed")
        info = self.directory.lstat()
        if [info.st_dev, info.st_ino] != list(self._directory_id):
            raise ResearchRefusal("directory_identity_mismatch")
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ResearchRefusal("private_directory_invalid")
        self._check_files()
        if self._identity(self._lock) != self._guard_id:
            raise ResearchRefusal("guard_identity_mismatch")
        if self._identity(self._db) != self._database_id:
            raise ResearchRefusal("database_identity_mismatch")
        held = os.fstat(self._guard)
        if [held.st_dev, held.st_ino] != self._guard_id:
            raise ResearchRefusal("guard_identity_mismatch")
        if check_marker and self._read_marker() != {
                "schema": 1, "manifest": self._manifest, "guard": self._guard_id, "database": self._database_id}:
            raise ResearchRefusal("store_marker_invalid")

    def ensure_dispatch(self):
        self._check_owner()
        if self._pending:
            raise ResearchRefusal("transport_unsettled")

    @contextlib.contextmanager
    def _transaction(self, check_marker=True):
        self._check_owner(check_marker)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            yield
            self._check_owner(check_marker)
            self._conn.execute("COMMIT")
        except (sqlite3.Error, OSError):
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise ResearchRefusal("store_commit_failed") from None
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise

    def begin_cycle(self, cycle_id, session):
        if not isinstance(cycle_id, str) or not ID.fullmatch(cycle_id):
            raise ResearchRefusal("cycle_invalid")
        if not isinstance(session, str) or not re.fullmatch(r"XNYS:\d{4}-\d{2}-\d{2}", session):
            raise ResearchRefusal("session_invalid")
        self.ensure_dispatch()
        row = self._conn.execute("SELECT status,receipt,session FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
        if row:
            if row["session"] != session:
                raise ResearchRefusal("cycle_session_mismatch")
            return json.loads(row["receipt"]) if row["receipt"] else {
                "cycle_id": cycle_id, "status": row["status"], "research_only": True,
                "trusted_for_admission": False, "executable": False, "has_gaps": True}
        with self._transaction():
            if self._conn.execute("SELECT 1 FROM cycles WHERE status='collecting' LIMIT 1").fetchone():
                raise ResearchRefusal("cycle_in_progress")
            self._conn.execute("INSERT INTO cycles VALUES (?,?,'collecting',NULL)", (cycle_id, session))
        return None

    def reserve_attempt(self, cycle_id, request):
        self.ensure_dispatch()
        if (not isinstance(request, dict) or set(request) != {"kind", "symbol", "expiry"}
                or request["kind"] not in {"quotes", "expirations", "chain"}
                or request["symbol"] not in ("SPY", "QQQ")
                or (request["kind"] == "chain" and request["expiry"] not in self._manifest["expiries"])
                or (request["kind"] != "chain" and request["expiry"] is not None)):
            raise ResearchRefusal("request_scope_invalid")
        attempt_id = uuid.uuid4().hex
        reservation = self._limits["max_body_bytes"] + self._limits["max_chunk_bytes"]
        with self._transaction():
            cycle = self._conn.execute("SELECT status FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            if not cycle or cycle[0] != "collecting":
                raise ResearchRefusal("cycle_not_collecting")
            count, read_bytes, retained = self._conn.execute(
                "SELECT count(*),coalesce(sum(read_reserved),0),coalesce(sum(length(body)),0) FROM attempts").fetchone()
            if retained >= self._limits["max_total_body_bytes"]:
                raise ResearchRefusal("retained_byte_cap")
            if count >= self._limits["max_attempts"]:
                raise ResearchRefusal("attempt_cap")
            if read_bytes + reservation > self._limits["max_total_read_bytes"]:
                raise ResearchRefusal("read_byte_cap")
            self._conn.execute("INSERT INTO attempts (attempt_id,cycle_id,request,status,read_reserved) VALUES (?,?,?,'reserved',?)",
                               (attempt_id, cycle_id, canonical(request), reservation))
        return {"attempt_id": attempt_id, "max_body_bytes": self._limits["max_body_bytes"],
                "max_chunk_bytes": self._limits["max_chunk_bytes"], "read_reserved": reservation}

    def mark_dispatch(self, attempt_id, started_at):
        _stamp(started_at)
        self.ensure_dispatch()
        with self._transaction():
            changed = self._conn.execute("UPDATE attempts SET status='dispatching',started_at=? WHERE attempt_id=? AND status='reserved'",
                                         (started_at, attempt_id)).rowcount
            if changed != 1:
                raise ResearchRefusal("attempt_not_reserved")

    def fail_attempt(self, attempt_id, status):
        if status not in {"budget_refused", "pre_dispatch_stopped", "transport_failed", "cancelled", "timeout", "unsettled"}:
            raise ResearchRefusal("attempt_status_invalid")
        with self._transaction():
            self._conn.execute("UPDATE attempts SET status=? WHERE attempt_id=? AND status IN ('reserved','dispatching')",
                               (status, attempt_id))

    def record_response(self, attempt_id, metadata, body):
        allowed = {"http_status", "source_delivery", "media_type", "content_encoding", "started_at",
                   "body_completed_at", "wall_clock_regressed", "body_complete", "bytes_observed",
                   "source_body_sha256", "withholding_reason", "error_code", "response_closed_at", "closure_gate_reason"}
        reasons = {None, "body_limit_exceeded", "chunk_limit_exceeded", "incomplete_body",
                   "unsupported_encoding", "unsupported_media", "invalid_utf8", "sensitive_body"}
        errors = {None, "transport_failed", "body_limit", "chunk_limit", "timeout", "http_error", "clock_invalid"}
        if not isinstance(metadata, dict) or set(metadata) != allowed or type(body) is not bytes:
            raise ResearchRefusal("metadata_invalid")
        if (type(metadata["http_status"]) is not int or not 100 <= metadata["http_status"] <= 599
                or metadata["source_delivery"] not in {"network", "cache", "unknown"}
                or metadata["media_type"] not in {"json", "unsupported"}
                or metadata["content_encoding"] not in {"identity", "unsupported"}
                or type(metadata["body_complete"]) is not bool or type(metadata["wall_clock_regressed"]) is not bool
                or type(metadata["bytes_observed"]) is not int or not 0 <= metadata["bytes_observed"] < 2**63
                or metadata["closure_gate_reason"] not in {None, "clock_invalid", "clock_regressed", "cycle_deadline",
                                                         "gate_unknown", "paused", "session_closed_or_unknown"}
                or metadata["withholding_reason"] not in reasons or metadata["error_code"] not in errors):
            raise ResearchRefusal("metadata_invalid")
        _stamp(metadata["started_at"])
        _stamp(metadata["body_completed_at"], True)
        _stamp(metadata["response_closed_at"], True)
        source_hash = metadata["source_body_sha256"]
        if source_hash is not None and (not isinstance(source_hash, str) or not SHA.fullmatch(source_hash)):
            raise ResearchRefusal("metadata_invalid")
        if not metadata["body_complete"] and source_hash is not None:
            raise ResearchRefusal("metadata_invalid")
        if len(body) > self._limits["max_body_bytes"]:
            raise ResearchRefusal("response_byte_cap")
        if metadata["withholding_reason"] is not None or not metadata["body_complete"]:
            if body:
                raise ResearchRefusal("withheld_body_required")
        elif hashlib.sha256(body).hexdigest() != source_hash:
            raise ResearchRefusal("response_hash_mismatch")
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            raise ResearchRefusal("invalid_utf8_body") from None
        if contains_sensitive(body):
            raise ResearchRefusal("sensitive_body")
        text = _safe_json(metadata, 4096)
        with self._transaction():
            row = self._conn.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if not row or row[0] != "dispatching":
                raise ResearchRefusal("attempt_not_dispatching")
            total = self._conn.execute("SELECT coalesce(sum(length(body)),0) FROM attempts").fetchone()[0]
            if total + len(body) > self._limits["max_total_body_bytes"]:
                raise ResearchRefusal("retained_byte_cap")
            self._conn.execute("UPDATE attempts SET status='raw_committed',response=?,body=?,body_sha256=? WHERE attempt_id=?",
                               (text, body, hashlib.sha256(body).hexdigest(), attempt_id))

    def record_parsed(self, attempt_id, rows, metadata):
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows) or not isinstance(metadata, dict):
            raise ResearchRefusal("parsed_payload_invalid")
        if set(metadata) != {"status", "parsed_at", "errors", "truncated"}:
            raise ResearchRefusal("parsed_payload_invalid")
        if (metadata["status"] not in {"parsed", "empty", "parse_failed", "unavailable"}
                or type(metadata["errors"]) is not int or metadata["errors"] < 0
                or type(metadata["truncated"]) is not bool):
            raise ResearchRefusal("parsed_payload_invalid")
        _stamp(metadata["parsed_at"])
        values = [_safe_json(row, 4096) for row in rows]
        text = _safe_json(metadata, 4096)
        with self._transaction():
            row = self._conn.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if not row or row[0] != "raw_committed":
                raise ResearchRefusal("raw_receipt_required")
            count = self._conn.execute("SELECT count(*) FROM observations").fetchone()[0]
            if count + len(values) > self._limits["max_rows"]:
                raise ResearchRefusal("row_cap")
            self._conn.executemany("INSERT INTO observations VALUES (?,?,?)",
                                   [(attempt_id, index, value) for index, value in enumerate(values)])
            self._conn.execute("UPDATE attempts SET status='committed',parsed=? WHERE attempt_id=?", (text, attempt_id))

    def finish_cycle(self, cycle_id, receipt):
        text = _safe_json(receipt, 16384)
        with self._transaction():
            if self._conn.execute("UPDATE cycles SET status=?,receipt=? WHERE cycle_id=? AND status='collecting'",
                                  (receipt.get("status", "failed"), text, cycle_id)).rowcount != 1:
                raise ResearchRefusal("cycle_not_collecting")

    def attempts(self, cycle_id):
        self._check_owner()
        result = []
        for row in self._conn.execute("SELECT * FROM attempts WHERE cycle_id=? ORDER BY rowid", (cycle_id,)):
            value = dict(row)
            for key in ("request", "response", "parsed"):
                value[key] = json.loads(value[key]) if value[key] is not None else None
            value["retained_body_sha256"] = value.pop("body_sha256")
            result.append(value)
        return result

    def observations(self, attempt_id):
        self._check_owner()
        return [json.loads(row[0]) for row in self._conn.execute(
            "SELECT value FROM observations WHERE attempt_id=? ORDER BY row_index", (attempt_id,))]

    def status(self):
        self._check_owner()
        row = self._conn.execute("SELECT count(*),coalesce(sum(read_reserved),0),coalesce(sum(length(body)),0) FROM attempts").fetchone()
        return {"reserved_attempts": row[0], "reserved_read_bytes": row[1], "retained_body_bytes": row[2],
                "rows": self._conn.execute("SELECT count(*) FROM observations").fetchone()[0],
                "page_count": self._conn.execute("PRAGMA page_count").fetchone()[0],
                "pending_transports": self._pending}

    def retain_transport(self):
        self.ensure_dispatch()
        self._pending += 1

    def release_transport(self):
        if self._pending != 1:
            raise ResearchRefusal("transport_owner_invalid")
        self._pending = 0
        if self._closing:
            self._close_now()

    def _close_now(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._guard is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._guard, fcntl.LOCK_UN)
            os.close(self._guard)
            self._guard = None
        self.closed = True

    def close(self):
        self._closing = True
        if self._pending:
            return False
        self._close_now()
        return True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
