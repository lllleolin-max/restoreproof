"""Unchanged before/after oracle: malformed UTF-8 scalar must fail as evidence."""
import json
from pathlib import Path
import tempfile
from restoreproof import drill, make_fixture, snapshot


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        make_fixture(root / "app")
        snapshot(root / "app/source", root / "app/application.json", root / "backup")
        manifest = root / "backup/manifest.json"
        data = json.loads(manifest.read_text())
        data["files"][0]["path"] = "\ud800"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        (root / "restores").mkdir()
        try:
            report = drill(root / "backup/snapshot.zip", manifest, root / "restores")
        except Exception as error:
            raise AssertionError("malformed JSON scalar escaped structured failure: " + type(error).__name__) from error
        assert report["decision"] == "FAILED" and report["issues"][0]["code"] in ("MANIFEST", "PATH"), report
        assert not list((root / "restores").iterdir())
    print("PASS: escaped surrogate rejected as structured preflight failure")


if __name__ == "__main__":
    main()
