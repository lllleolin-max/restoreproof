"""Synthetic document library with relational references and actual asset bytes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing
from typing import Any
from .core import typed_cell


def make_fixture(root: str | Path, scenario: str = "healthy") -> dict[str, Any]:
    if scenario not in ("healthy", "missing_asset", "asset_mismatch", "foreign_key", "wrong_query"):
        raise ValueError("unsupported fixture scenario")
    root = Path(root)
    root.mkdir(parents=False, exist_ok=False)
    source = root / "source"
    (source / "assets").mkdir(parents=True)
    payloads = {"assets/guide.txt": b"Restore the index and the referenced documents together.\n",
                "assets/checklist.txt": b"Validate consumer joins after checking archive bytes.\n"}
    for name, payload in payloads.items():
        (source / name).write_bytes(payload)
    with closing(sqlite3.connect(source / "library.sqlite")) as conn:
        conn.executescript("""PRAGMA journal_mode=DELETE;
        CREATE TABLE collections(id INTEGER PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE documents(id INTEGER PRIMARY KEY, collection_id INTEGER REFERENCES collections(id),
          path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL);
        INSERT INTO collections VALUES(1,'Recovery handbook');""")
        for i, (name, payload) in enumerate(payloads.items(), 1):
            ref = "assets/absent.txt" if scenario == "missing_asset" and i == 1 else name
            digest = "0" * 64 if scenario == "asset_mismatch" and i == 1 else hashlib.sha256(payload).hexdigest()
            conn.execute("INSERT INTO documents VALUES(?,?,?,?,?)", (i, 99 if scenario == "foreign_key" and i == 1 else 1,
                         ref, digest, len(payload)))
        conn.commit()
    expected = [[typed_cell("Recovery handbook"), typed_cell(3 if scenario == "wrong_query" else 2),
                 typed_cell(sum(map(len, payloads.values())))]]
    app = {"format": "restoreproof-app-v1", "database": "library.sqlite",
           "queries": [{"id": "library_summary", "sql": "SELECT c.title,count(d.id),sum(d.bytes) FROM collections c JOIN documents d ON c.id=d.collection_id GROUP BY c.id ORDER BY c.id", "expected": expected}],
           "assets": [{"id": "document_payloads", "sql": "SELECT path,sha256 FROM documents ORDER BY id"}]}
    (root / "application.json").write_text(json.dumps(app, indent=2) + "\n", encoding="utf-8")
    return {"scenario": scenario, "source": str(source), "spec": str(root / "application.json")}
