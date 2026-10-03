"""Unchanged encoding audit: declared UTF-8 input must not autodetect UTF-16."""
from pathlib import Path
import tempfile
from restoreproof import drill, make_fixture, snapshot


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_fixture(root / "app")
        snapshot(root / "app/source", root / "app/application.json", root / "backup")
        manifest = root / "backup/manifest.json"
        manifest.write_bytes(manifest.read_text(encoding="utf-8").encode("utf-16"))
        parent = root / "restores"
        parent.mkdir()
        report = drill(root / "backup/snapshot.zip", manifest, parent)
        assert report["decision"] == "FAILED", "JSON byte autodetection accepted unsupported UTF-16 manifest"
        assert report["issues"][0]["code"] == "MANIFEST"
        assert report["source_preserved"] == "passed" and not list(parent.iterdir())
    print("PASS: unsupported JSON encoding rejected before restoration")


if __name__ == "__main__":
    main()
