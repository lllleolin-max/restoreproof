"""Unchanged before/after oracle: partial extraction is not snapshot agreement."""
from dataclasses import replace
from pathlib import Path
import tempfile
from restoreproof import Limits, drill, make_fixture, snapshot


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        make_fixture(root / "app")
        snapshot(root / "app/source", root / "app/application.json", root / "backup")
        (root / "restores").mkdir()
        report = drill(root / "backup/snapshot.zip", root / "backup/manifest.json", root / "restores",
                       limits=replace(Limits(), total_bytes=1))
        assert report["decision"] == "FAILED" and report["lifecycle"] == "partial_failed", report
        assert report["snapshot_agreement"] != "passed", "metadata preflight falsely certified actual snapshot agreement"
        assert report["application_assertions"] == "not_run"
    print("PASS: partial extraction does not certify snapshot agreement")


if __name__ == "__main__":
    main()
