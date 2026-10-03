"""Fair synthetic same-archive ablation; does not run or rank restic."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from restoreproof import Limits, drill, make_fixture, snapshot
from restoreproof.core import digest_file


def run():
    rows = []
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        for name in ("healthy", "missing_asset", "asset_mismatch", "foreign_key", "wrong_query", "budget_exhausted", "digest_corrupt"):
            folder = base / name
            folder.mkdir()
            fixture = folder / "app"
            make_fixture(fixture, "healthy" if name in ("budget_exhausted", "digest_corrupt") else name)
            snapshot(fixture / "source", fixture / "application.json", folder / "backup")
            archive, manifest = folder / "backup/snapshot.zip", folder / "backup/manifest.json"
            if name == "digest_corrupt":
                data = json.loads(manifest.read_text())
                data["files"][0]["sha256"] = "0" * 64
                manifest.write_text(json.dumps(data))
            source_before = {p.relative_to(folder).as_posix(): digest_file(p) for p in folder.rglob("*") if p.is_file()}
            parent = folder / "restores"
            parent.mkdir()
            limits = replace(Limits(), vm_steps=1) if name == "budget_exhausted" else Limits()
            baseline = drill(archive, manifest, parent, limits=limits, application=False)
            full = drill(archive, manifest, parent, limits=limits)
            unchanged = all(digest_file(folder / path) == value for path, value in source_before.items())
            rows.append({"case": name, "hash_only": baseline["decision"], "application_aware": full["decision"],
                         "byte_integrity": full["byte_integrity"], "snapshot_agreement": full["snapshot_agreement"],
                         "reason": full["issues"][0]["code"] if full["issues"] else "all_declared_checks_passed",
                         "source_unchanged": unchanged,
                         "baseline_seconds": baseline["metrics"]["elapsed_seconds"],
                         "application_seconds": full["metrics"]["elapsed_seconds"]})
    assert rows[0]["application_aware"] == "USABLE"
    assert rows[-1]["hash_only"] == "FAILED"
    assert all(row["source_unchanged"] for row in rows)
    assert all(row["hash_only"] == "BYTE_VERIFIED" and row["application_aware"] == "FAILED" for row in rows[1:-1])
    return {"fixture": "synthetic SQLite document library", "baseline": "same strict extraction and digest checks; application assertions disabled", "incumbent_executed": False, "cases": rows}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
