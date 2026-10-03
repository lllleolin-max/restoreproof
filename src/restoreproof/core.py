"""Strict ZIP32 streaming restore and bounded read-only SQLite assertions."""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import tempfile
import time
from typing import Any, BinaryIO, Iterator
import unicodedata
import zipfile
import zlib

CHUNK = 65536
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?\Z", re.I)


class RestoreError(ValueError):
    """A stable machine-readable failure code and public explanation."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise RestoreError(code, message)


@dataclass(frozen=True)
class Limits:
    """Positive integer limits, shared across the whole application check."""
    archive_bytes: int = 64 * 1024 * 1024
    manifest_bytes: int = 1024 * 1024
    members: int = 2048
    file_bytes: int = 16 * 1024 * 1024
    total_bytes: int = 64 * 1024 * 1024
    queries: int = 32
    sql_bytes: int = 16384
    vm_steps: int = 1_000_000
    rows: int = 4096
    result_bytes: int = 1024 * 1024
    cell_bytes: int = 256 * 1024
    seconds: int = 5

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value <= 0:
                fail("LIMIT", f"{field.name} must be a positive integer (not bool)")


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def portable_path(value: Any) -> str:
    """Validate original spelling; never normalize an unsafe archive name."""
    if type(value) is not str or not value:
        fail("PATH", "path must be nonempty UTF-8 and at most 240 bytes")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise RestoreError("PATH", "path contains a non-UTF-8 Unicode scalar") from exc
    if len(encoded) > 240:
        fail("PATH", "path must be nonempty UTF-8 and at most 240 bytes")
    if unicodedata.normalize("NFC", value) != value:
        fail("PATH", "path spelling must already be NFC")
    if value.startswith("/") or "\\" in value or ":" in value:
        fail("PATH", "absolute, drive, UNC, backslash and ADS paths are forbidden")
    for part in value.split("/"):
        if not part or part in (".", "..") or part[-1] in ". ":
            fail("PATH", "empty/dot components and trailing dot or space are forbidden")
        if DEVICE.fullmatch(part) or any(c in '<>"|?*' or unicodedata.category(c).startswith("C") for c in part):
            fail("PATH", "device names, Windows special and Unicode control characters are forbidden")
    return value


def validate_names(names: list[str]) -> None:
    # Implicit directory spellings participate, including Assets/a vs assets/b.
    seen: dict[str, tuple[str, bool]] = {}
    for name in names:
        portable_path(name)
        parts = name.split("/")
        for i in range(1, len(parts) + 1):
            spelling = "/".join(parts[:i])
            key = spelling.casefold()
            is_file = i == len(parts)
            if key in seen:
                original, was_file = seen[key]
                if original != spelling or was_file or is_file:
                    fail("COLLISION", "duplicate, case collision or file/directory prefix collision")
            else:
                seen[key] = (spelling, is_file)


def _keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        fail("MANIFEST", f"{where}: exact keys required: {', '.join(sorted(expected))}")
    return value


def _list(value: Any, bound: int, where: str) -> list[Any]:
    if type(value) is not list or len(value) > bound:
        fail("MANIFEST", f"{where}: bounded array required")
    return value


def typed_cell(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "value": None}
    if type(value) is int:
        return {"type": "integer", "value": value}
    if type(value) is float and math.isfinite(value):
        return {"type": "real", "value": value.hex()}
    if type(value) is str:
        return {"type": "text", "value": value}
    if type(value) is bytes:
        return {"type": "blob", "value": value.hex()}
    fail("RESULT_TYPE", "unsupported or nonfinite SQLite result")
    raise AssertionError


def _cell(value: Any) -> None:
    item = _keys(value, {"type", "value"}, "expected cell")
    typ, val = item["type"], item["value"]
    valid = ((typ == "null" and val is None) or
             (typ == "integer" and type(val) is int and -(2**63) <= val < 2**63) or
             (typ == "text" and type(val) is str) or
             (typ == "blob" and type(val) is str and re.fullmatch(r"(?:[0-9a-f]{2})*", val) is not None))
    if typ == "real" and type(val) is str:
        try:
            number = float.fromhex(val)
            valid = math.isfinite(number) and number.hex() == val
        except ValueError:
            pass
    if not valid:
        fail("MANIFEST", "expected values must use canonical exact SQLite types")


def validate_app(value: Any, limits: Limits) -> dict[str, Any]:
    app = _keys(value, {"format", "database", "queries", "assets"}, "application")
    if app["format"] != "restoreproof-app-v1":
        fail("MANIFEST", "unsupported application format")
    portable_path(app["database"])
    queries = _list(app["queries"], limits.queries, "queries")
    assets = _list(app["assets"], limits.queries, "assets")
    if not queries or not assets or len(queries) + len(assets) > limits.queries:
        fail("MANIFEST", "declare at least one consumer query and asset query within the total limit")
    ids = set()
    for group, asset in ((queries, False), (assets, True)):
        for query in group:
            _keys(query, {"id", "sql"} if asset else {"id", "sql", "expected"}, "query")
            if type(query["id"]) is not str or not IDENT.fullmatch(query["id"]) or query["id"] in ids:
                fail("MANIFEST", "unique query identifiers required")
            ids.add(query["id"])
            sql = query["sql"]
            if type(sql) is not str or not sql.strip() or len(sql.encode("utf-8")) > limits.sql_bytes:
                fail("MANIFEST", "nonempty bounded SQL required")
            if not asset:
                for row in _list(query["expected"], limits.rows, "expected rows"):
                    for cell in _list(row, 64, "expected row"):
                        _cell(cell)
    return app


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            fail("MANIFEST", "duplicate JSON object keys")
        result[key] = value
    return result


def read_json(path: Path, limits: Limits) -> dict[str, Any]:
    with path.open("rb") as stream:
        data = stream.read(limits.manifest_bytes + 1)
    if len(data) > limits.manifest_bytes:
        fail("MANIFEST_LIMIT", "JSON input exceeds byte limit")
    try:
        parsed = json.loads(data, object_pairs_hook=_pairs,
                            parse_constant=lambda _: fail("MANIFEST", "nonfinite JSON numbers forbidden"))
        # JSON escape syntax can represent lone surrogates despite a UTF-8 input.
        # Validate all strings, including keys and expectation cells, before any
        # path operation, SQLite binding or ensure_ascii=False serialization.
        pending = [parsed]
        while pending:
            item = pending.pop()
            if type(item) is str:
                item.encode("utf-8")
            elif type(item) is dict:
                pending.extend(item.keys())
                pending.extend(item.values())
            elif type(item) is list:
                pending.extend(item)
        return parsed
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RestoreError("MANIFEST", "invalid or excessively nested UTF-8 JSON") from exc


def read_manifest(path: Path, limits: Limits) -> dict[str, Any]:
    manifest = _keys(read_json(path, limits), {"format", "application", "files"}, "snapshot")
    if manifest["format"] != "restoreproof-snapshot-v1":
        fail("MANIFEST", "unsupported snapshot format")
    app = validate_app(manifest["application"], limits)
    files = _list(manifest["files"], limits.members, "files")
    for item in files:
        _keys(item, {"path", "size", "sha256"}, "file")
        portable_path(item["path"])
        if type(item["size"]) is not int or not 0 <= item["size"] <= limits.file_bytes:
            fail("MANIFEST", "file size must be a bounded nonnegative integer (not bool)")
        if type(item["sha256"]) is not str or not DIGEST.fullmatch(item["sha256"]):
            fail("MANIFEST", "file digest must be lowercase SHA-256")
    validate_names([item["path"] for item in files])
    if app["database"] not in {item["path"] for item in files}:
        fail("SNAPSHOT", "application database missing from snapshot inventory")
    return manifest


@dataclass(frozen=True)
class Member:
    name: str
    offset: int
    compressed: int
    size: int
    crc: int
    method: int


def _read(stream: BinaryIO, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        fail("ARCHIVE", "truncated archive")
    return data


def parse_archive(path: Path, limits: Limits) -> list[Member]:
    """Narrow ZIP32, no descriptors/extras/comments/links. Bound before allocation."""
    size = path.stat().st_size
    if size > limits.archive_bytes or size < 22:
        fail("ARCHIVE_LIMIT", "archive size outside supported bound")
    members: list[Member] = []
    with path.open("rb") as stream:
        stream.seek(size - 22)
        eocd = struct.unpack("<4s4H2IH", _read(stream, 22))
        sig, disk, start_disk, count_disk, count, cd_size, cd_offset, comment = eocd
        if sig != b"PK\x05\x06" or disk or start_disk or count_disk != count or comment:
            fail("ARCHIVE", "single-disk ZIP32 with no comment required")
        if count > limits.members:
            fail("MEMBER_LIMIT", "archive member count exceeds limit")
        if cd_offset + cd_size != size - 22:
            fail("ARCHIVE", "unsupported ZIP layout or ZIP64")
        stream.seek(cd_offset)
        records = []
        for _ in range(count):
            raw = struct.unpack("<4s6H3I5H2I", _read(stream, 46))
            sig, made, needed, flags, method, _time, _date, crc, compressed, actual, namelen, extra, comment, disk, internal, external, offset = raw
            if sig != b"PK\x01\x02" or needed > 20 or flags not in (0, 0x800) or method not in (0, 8):
                fail("ENTRY", "only unencrypted stored/deflate ZIP32 regular entries supported")
            if extra or comment or disk or internal or made >> 8 not in (0, 3):
                fail("ENTRY", "extra metadata, descriptors and unsupported entry systems forbidden")
            mode = external >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or external & 0x18:
                fail("ENTRY", "links, directories, devices and volume entries forbidden")
            namebytes = _read(stream, namelen)
            try:
                name = namebytes.decode("utf-8" if flags & 0x800 else "ascii")
            except UnicodeError as exc:
                raise RestoreError("PATH", "entry name must be ASCII or flagged UTF-8") from exc
            portable_path(name)
            records.append((name, namebytes, needed, flags, method, crc, compressed, actual, offset))
        if stream.tell() != cd_offset + cd_size:
            fail("ARCHIVE", "central directory size/count mismatch")
        validate_names([r[0] for r in records])
        expected_offset = 0
        for name, namebytes, needed, flags, method, crc, compressed, actual, offset in sorted(records, key=lambda r: r[-1]):
            if offset != expected_offset:
                fail("ARCHIVE", "overlapping, hidden or noncontiguous local entry data")
            stream.seek(offset)
            header = struct.unpack("<4s5H3I2H", _read(stream, 30))
            sig, local_needed, local_flags, local_method, _time, _date, local_crc, local_compressed, local_size, namelen, extra = header
            if (sig != b"PK\x03\x04" or (local_needed, local_flags, local_method, local_crc, local_compressed, local_size) !=
                    (needed, flags, method, crc, compressed, actual) or extra or namelen != len(namebytes)):
                fail("ARCHIVE", "local/central header agreement required")
            if _read(stream, namelen) != namebytes:
                fail("ARCHIVE", "local/central filename mismatch")
            offset = stream.tell()
            expected_offset = offset + compressed
            if expected_offset > cd_offset:
                fail("ARCHIVE", "truncated or overlapping compressed data")
            members.append(Member(name, offset, compressed, actual, crc, method))
        if expected_offset != cd_offset:
            fail("ARCHIVE", "hidden data before central directory")
    return members


def _plan(archive: Path, manifest: dict[str, Any], limits: Limits) -> list[Member]:
    members = parse_archive(archive, limits)
    inventory = {item["path"]: item for item in manifest["files"]}
    if {member.name for member in members} != set(inventory):
        fail("SNAPSHOT", "archive file set differs from manifest (missing or extra member)")
    for member in members:
        if member.size != inventory[member.name]["size"]:
            fail("SNAPSHOT", "declared member size differs from manifest")
    return members


def plan(archive: str | Path, manifest: str | Path, *, limits: Limits = Limits()) -> dict[str, Any]:
    """Metadata-only dry plan. Does not decompress or claim byte/application validity."""
    data = read_manifest(Path(manifest), limits)
    members = _plan(Path(archive), data, limits)
    return {"format": "restoreproof-plan-v1", "status": "PLANNED", "members": len(members),
            "declared_bytes": sum(member.size for member in members),
            "byte_integrity": "not_run", "application_assertions": "not_run"}


def _chunks(stream: BinaryIO, member: Member) -> Iterator[bytes]:
    stream.seek(member.offset)
    remaining = member.compressed
    if member.method == 0:
        while remaining:
            chunk = _read(stream, min(CHUNK, remaining))
            remaining -= len(chunk)
            yield chunk
        return
    decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    while remaining:
        compressed = _read(stream, min(CHUNK, remaining))
        remaining -= len(compressed)
        while compressed:
            chunk = decompressor.decompress(compressed, CHUNK)
            compressed = decompressor.unconsumed_tail
            if chunk:
                yield chunk
            if decompressor.unused_data:
                fail("ARCHIVE", "trailing bytes or concatenated deflate stream")
        if decompressor.eof and remaining:
            fail("ARCHIVE", "compressed extent contains trailing bytes")
    while not decompressor.eof:
        chunk = decompressor.decompress(b"", CHUNK)
        if not chunk:
            fail("ARCHIVE", "truncated deflate stream")
        yield chunk


def _extract(archive: Path, members: list[Member], manifest: dict[str, Any], destination: Path,
             limits: Limits, metrics: dict[str, Any]) -> dict[str, str]:
    inventory = {item["path"]: item for item in manifest["files"]}
    digests = {}
    with archive.open("rb") as stream:
        for member in members:
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            actual = crc = 0
            with path.open("xb") as out:
                for chunk in _chunks(stream, member):
                    actual += len(chunk)
                    metrics["decompressed_bytes"] += len(chunk)
                    if actual > limits.file_bytes or metrics["decompressed_bytes"] > limits.total_bytes:
                        fail("DECOMPRESS_LIMIT", "actual decompressed byte limit exhausted")
                    h.update(chunk)
                    crc = zlib.crc32(chunk, crc)
                    out.write(chunk)
            if actual != inventory[member.name]["size"] or actual != member.size:
                fail("SNAPSHOT", "actual decompressed size differs from declared snapshot")
            if crc != member.crc or h.hexdigest() != inventory[member.name]["sha256"]:
                fail("BYTE_INTEGRITY", "restored bytes fail ZIP CRC or manifest SHA-256")
            digests[member.name] = h.hexdigest()
            metrics["restored_files"] += 1
    return digests


def standalone_database(root: Path, database: str) -> Path:
    path = root / database
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        fail("SQLITE_SNAPSHOT", "WAL, shared-memory and journal sidecars are unsupported")
    with path.open("rb") as stream:
        header = stream.read(100)
    if len(header) != 100 or header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
        fail("SQLITE_SNAPSHOT", "quiescent standalone rollback-mode SQLite required (no WAL header)")
    return path


class _Work:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.steps = self.rows = self.bytes = 0
        self.deadline = time.monotonic() + limits.seconds
        self.exhausted = False

    def progress(self) -> int:
        self.steps += 1
        self.exhausted = self.steps > self.limits.vm_steps or time.monotonic() > self.deadline
        return int(self.exhausted)

    def check(self) -> None:
        if time.monotonic() > self.deadline:
            self.exhausted = True
        if self.exhausted or self.rows > self.limits.rows or self.bytes > self.limits.result_bytes:
            fail("QUERY_BUDGET", "shared VM/time/result budget exhausted")


SAFE_FUNCTIONS = frozenset({"count", "sum", "total", "min", "max", "avg", "length", "hex", "coalesce",
                            "ifnull", "nullif", "lower", "upper", "substr", "substring", "typeof", "abs", "round"})


def _authorizer(internal: bool):
    def allow(action: int, first: str | None, second: str | None, database: str | None, trigger: str | None) -> int:
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and database in (None, "main"):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        if internal and action == sqlite3.SQLITE_PRAGMA and first in ("integrity_check", "foreign_key_check") and second is None:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return allow


def _query(connection: sqlite3.Connection, sql: str, work: _Work, *, internal: bool = False) -> list[list[dict[str, Any]]]:
    connection.set_authorizer(_authorizer(internal))
    work.check()
    try:
        cursor = connection.execute(sql)
        rows = []
        for row in cursor:
            work.rows += 1
            converted = [typed_cell(cell) for cell in row]
            work.bytes += len(json.dumps(converted, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            work.check()
            rows.append(converted)
        work.check()
        return rows
    except sqlite3.Error as exc:
        if work.exhausted:
            raise RestoreError("QUERY_BUDGET", "shared VM/time budget exhausted") from exc
        raise RestoreError("QUERY", "SQLite rejected query, schema, result size or read-only operation") from exc


def _application(destination: Path, app: dict[str, Any], digests: dict[str, str], limits: Limits,
                 metrics: dict[str, Any]) -> list[dict[str, Any]]:
    path = standalone_database(destination, app["database"])
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0)
    work = _Work(limits)
    checks: list[dict[str, Any]] = []
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        for name, value in (("SQLITE_LIMIT_LENGTH", limits.cell_bytes), ("SQLITE_LIMIT_SQL_LENGTH", limits.sql_bytes),
                            ("SQLITE_LIMIT_COLUMN", 64), ("SQLITE_LIMIT_EXPR_DEPTH", 200),
                            ("SQLITE_LIMIT_COMPOUND_SELECT", 64), ("SQLITE_LIMIT_ATTACHED", 0)):
            connection.setlimit(getattr(sqlite3, name), value)
        connection.set_progress_handler(work.progress, 1)
        schema = _query(connection, "SELECT sql FROM sqlite_schema WHERE type='table'", work)
        if any(cell[0]["type"] == "text" and re.match(r"\s*CREATE\s+VIRTUAL\s+TABLE", cell[0]["value"], re.I) for cell in schema):
            fail("SQLITE_SCHEMA", "virtual tables unsupported")
        integrity = _query(connection, "PRAGMA integrity_check", work, internal=True)
        if integrity != [[typed_cell("ok")]]:
            fail("SQLITE_INTEGRITY", "restored SQLite integrity check failed")
        foreign_keys = _query(connection, "PRAGMA foreign_key_check", work, internal=True)
        if foreign_keys:
            fail("SQLITE_FOREIGN_KEY", "restored SQLite foreign-key check failed")
        checks.extend([{"id": "sqlite_integrity", "status": "passed"}, {"id": "sqlite_foreign_keys", "status": "passed"}])
        for assertion in app["queries"]:
            actual = _query(connection, assertion["sql"], work)
            if actual != assertion["expected"]:
                fail("QUERY_EXPECTATION", f"consumer assertion {assertion['id']} differs in type, order or value")
            checks.append({"id": assertion["id"], "status": "passed", "rows": len(actual)})
        for assertion in app["assets"]:
            actual = _query(connection, assertion["sql"], work)
            for row in actual:
                if len(row) != 2 or any(cell["type"] != "text" for cell in row):
                    fail("ASSET_REFERENCE", "asset query must return (portable_path TEXT, sha256 TEXT)")
                name, expected = row[0]["value"], row[1]["value"]
                portable_path(name)
                if not DIGEST.fullmatch(expected) or name == app["database"]:
                    fail("ASSET_REFERENCE", "asset query must reference non-database files with lowercase SHA-256")
                if name not in digests:
                    fail("ASSET_MISSING", f"asset assertion {assertion['id']} references an absent snapshot file")
                if digests[name] != expected:
                    fail("ASSET_MISMATCH", f"asset assertion {assertion['id']} disagrees with actual restored asset bytes")
            checks.append({"id": assertion["id"], "status": "passed", "rows": len(actual)})
        return checks
    finally:
        metrics["sql_vm_steps"] = work.steps
        metrics["sql_rows"] = work.rows
        metrics["sql_result_bytes"] = work.bytes
        connection.close()


def drill(archive: str | Path, manifest: str | Path, parent: str | Path, *,
          limits: Limits = Limits(), application: bool = True) -> dict[str, Any]:
    """Always return evidence. FAILED directories remain diagnostic partial state."""
    archive, manifest, parent = Path(archive), Path(manifest), Path(parent)
    started = time.monotonic()
    report: dict[str, Any] = {"format": "restoreproof-report-v1", "decision": "FAILED", "phase": "preflight",
        "destination": None, "lifecycle": "not_created", "byte_integrity": "not_run",
        "snapshot_agreement": "not_run", "application_assertions": "not_run", "assertions": [], "issues": [],
        "inputs": {}, "source_preserved": "not_verified", "limits": {field.name: getattr(limits, field.name) for field in fields(limits)},
        "metrics": {"decompressed_bytes": 0, "restored_files": 0, "sql_vm_steps": 0, "sql_rows": 0, "sql_result_bytes": 0}}
    fingerprints: dict[str, str] = {}
    try:
        if archive.stat().st_size > limits.archive_bytes or manifest.stat().st_size > limits.manifest_bytes:
            fail("INPUT_LIMIT", "input size exceeds configured limit")
        fingerprints = {"archive_sha256": digest_file(archive), "manifest_sha256": digest_file(manifest)}
        report["inputs"] = fingerprints.copy()
        data = read_manifest(manifest, limits)
        members = _plan(archive, data, limits)
        report["snapshot_agreement"] = "passed"
        if not parent.is_dir() or parent.is_symlink():
            fail("DESTINATION", "trusted parent must be an existing real directory")
        destination = Path(tempfile.mkdtemp(prefix="restoreproof-", dir=parent))
        report["destination"] = str(destination)
        report["lifecycle"] = "partial_failed"
        report["phase"] = "extraction"
        digests = _extract(archive, members, data, destination, limits, report["metrics"])
        report["byte_integrity"] = "passed"
        report["lifecycle"] = "bytes_restored"
        if application:
            report["phase"] = "application"
            report["assertions"] = _application(destination, data["application"], digests, limits, report["metrics"])
            report["application_assertions"] = "passed"
            report["decision"] = "USABLE"
            report["lifecycle"] = "restore_verified"
        else:
            report["decision"] = "BYTE_VERIFIED"
        report["phase"] = "complete"
    except (RestoreError, OSError, zlib.error, sqlite3.Error) as exc:
        code = exc.code if isinstance(exc, RestoreError) else "IO_OR_FORMAT"
        report["issues"].append({"code": code, "message": str(exc) if isinstance(exc, RestoreError) else "I/O or underlying format operation failed"})
        if report["phase"] == "application":
            report["application_assertions"] = "failed"
            report["lifecycle"] = "application_failed"
        elif report["phase"] == "extraction":
            report["byte_integrity"] = "failed"
            if code == "SNAPSHOT":
                report["snapshot_agreement"] = "failed"
        elif code in ("SNAPSHOT", "MANIFEST", "COLLISION", "PATH", "ENTRY", "ARCHIVE"):
            report["snapshot_agreement"] = "failed"
    finally:
        if fingerprints:
            try:
                unchanged = fingerprints == {"archive_sha256": digest_file(archive), "manifest_sha256": digest_file(manifest)}
                report["source_preserved"] = "passed" if unchanged else "failed"
                if not unchanged:
                    report["decision"] = "FAILED"
                    report["issues"].append({"code": "SOURCE_CHANGED", "message": "source inputs changed during drill"})
            except OSError:
                report["source_preserved"] = "failed"
                report["decision"] = "FAILED"
        report["metrics"]["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return report


def _source_files(root: Path, limits: Limits) -> list[tuple[str, Path]]:
    files = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                fail("SOURCE_ENTRY", "source links/reparse points unsupported")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                files.append((path.relative_to(root).as_posix(), path))
                if len(files) > limits.members or info.st_size > limits.file_bytes:
                    fail("SOURCE_LIMIT", "source file count or size exceeds limit")
            else:
                fail("SOURCE_ENTRY", "source devices and hard links unsupported")
    validate_names([name for name, _ in files])
    return sorted(files)


def snapshot(source: str | Path, spec: str | Path, output: str | Path, *, limits: Limits = Limits()) -> dict[str, Any]:
    """Copy a declared quiescent source into a new ZIP32+manifest directory."""
    source, spec, output = Path(source).resolve(), Path(spec).resolve(), Path(output).absolute()
    if not source.is_dir() or source.is_symlink() or output.is_relative_to(source):
        fail("SOURCE", "source directory required and output must be outside it")
    if spec.is_relative_to(source):
        fail("SOURCE", "application spec must be outside source inventory")
    app = validate_app(read_json(spec, limits), limits)
    standalone_database(source, app["database"])
    entries = _source_files(source, limits)
    before = {name: digest_file(path) for name, path in entries}
    files = []
    total = 0
    output.mkdir(parents=False, exist_ok=False)
    try:
        with zipfile.ZipFile(output / "snapshot.zip", "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
            for name, path in entries:
                h = hashlib.sha256()
                actual = 0
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                with path.open("rb") as stream, archive.open(info, "w") as writer:
                    for chunk in iter(lambda: stream.read(CHUNK), b""):
                        total += len(chunk)
                        actual += len(chunk)
                        if actual > limits.file_bytes or total > limits.total_bytes:
                            fail("SOURCE_LIMIT", "actual source byte limit exhausted")
                        h.update(chunk)
                        writer.write(chunk)
                if h.hexdigest() != before[name]:
                    fail("SOURCE_CHANGED", "source changed during snapshot copy")
                files.append({"path": name, "size": actual, "sha256": h.hexdigest()})
        after_entries = _source_files(source, limits)
        if [name for name, _ in after_entries] != [name for name, _ in entries] or any(digest_file(path) != before[name] for name, path in after_entries):
            fail("SOURCE_CHANGED", "source inventory or bytes changed during snapshot")
        standalone_database(source, app["database"])
        manifest = {"format": "restoreproof-snapshot-v1", "application": app, "files": files}
        with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        # The writer must produce the same strict format the reader supports.
        plan(output / "snapshot.zip", output / "manifest.json", limits=limits)
        return {"format": "restoreproof-snapshot-result-v1", "status": "SNAPSHOT_CREATED", "files": len(files),
                "source_preserved": "passed", "archive_sha256": digest_file(output / "snapshot.zip")}
    except BaseException:
        with (output / "FAILED").open("x", encoding="utf-8") as stream:
            stream.write("Snapshot creation failed; contents are incomplete and must not be used.\n")
        raise
