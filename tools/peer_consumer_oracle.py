"""Independent SQLite/asset usability oracle, using only public RestoreProof API.

Run with the ordinary installed wheel's Python. Twenty synthetic app snapshots
vary size and actual failure mechanism; expected answers do not use core helpers.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from restoreproof import drill, snapshot


def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oracle(root, expected):
    with closing(sqlite3.connect((root / "catalog.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        fk = not db.execute("PRAGMA foreign_key_check").fetchall()
        count, size = db.execute("SELECT count(*),sum(nbytes) FROM docs").fetchone()
        rows = db.execute("SELECT path,digest,nbytes FROM docs ORDER BY id").fetchall()
    assets = all((root / p).is_file() and h(root / p) == d and (root / p).stat().st_size == n for p,d,n in rows)
    return integrity and fk and (count, size) == expected and assets


def main():
    records = []
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        for n in range(1, 5):
            for scenario in ("healthy", "missing", "digest", "foreign_key", "query"):
                root = base / f"{scenario}{n}"
                source = root / "source"
                (source / "payload").mkdir(parents=True)
                docs = []
                for i in range(n):
                    name = f"payload/doc{i}.bin"
                    data = bytes([i+1]) * (13 + i * 17) + f"case-{n}".encode()
                    (source / name).write_bytes(data)
                    docs.append((i+1, 999 if scenario == "foreign_key" and i == 0 else 1,
                                 "payload/absent.bin" if scenario == "missing" and i == 0 else name,
                                 "0" * 64 if scenario == "digest" and i == 0 else hashlib.sha256(data).hexdigest(), len(data)))
                with closing(sqlite3.connect(source / "catalog.sqlite")) as db:
                    db.executescript("CREATE TABLE parents(id INTEGER PRIMARY KEY); INSERT INTO parents VALUES(1); CREATE TABLE docs(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parents(id),path TEXT,digest TEXT,nbytes INTEGER);")
                    db.executemany("INSERT INTO docs VALUES(?,?,?,?,?)", docs)
                    db.commit()
                expected = (n + (scenario == "query"), sum(row[4] for row in docs))
                app = {"format":"restoreproof-app-v1", "database":"catalog.sqlite",
                       "queries":[{"id":"consumer_totals", "sql":"SELECT count(*),sum(nbytes) FROM docs",
                                   "expected":[[{"type":"integer","value":v} for v in expected]]}],
                       "assets":[{"id":"all_payloads", "sql":"SELECT path,digest FROM docs ORDER BY id"}]}
                spec = root / "application.json"
                spec.write_text(json.dumps(app), encoding="utf-8")
                before = {p.relative_to(root).as_posix():h(p) for p in root.rglob("*") if p.is_file()}
                expected_usable = oracle(source, expected)
                snapshot(source, spec, root / "backup")
                parent = root / "restores"
                parent.mkdir()
                paths = (root / "backup/snapshot.zip", root / "backup/manifest.json")
                inputs_before = [h(p) for p in paths]
                baseline = drill(*paths, parent, application=False)
                full = drill(*paths, parent)
                assert baseline["decision"] == "BYTE_VERIFIED", baseline
                assert (full["decision"] == "USABLE") == expected_usable, full
                assert full["byte_integrity"] == full["snapshot_agreement"] == "passed"
                restored_oracle = oracle(Path(full["destination"]), expected)
                assert restored_oracle == expected_usable
                assert before == {name:h(root / name) for name in before}
                assert inputs_before == [h(p) for p in paths]
                records.append({"case":scenario, "documents":n, "oracle_usable":expected_usable,
                                "hash_only":baseline["decision"], "full":full["decision"],
                                "reason":full["issues"][0]["code"] if full["issues"] else None,
                                "source_preserved":True,"restored_oracle_agrees":True})
    print(json.dumps({"cases":len(records),"passed":True,"records":records}, indent=2))


if __name__ == "__main__":
    main()
