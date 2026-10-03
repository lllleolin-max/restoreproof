"""Exercise the installed console and separately inspect restored app correctness."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import sysconfig
import tempfile
import restoreproof


def main():
    module = Path(restoreproof.__file__).resolve()
    assert any(module.is_relative_to(Path(sysconfig.get_path(name)).resolve()) for name in ("purelib", "platlib")), "ordinary wheel install required"
    command = Path(sysconfig.get_path("scripts")) / ("restoreproof.exe" if sys.platform == "win32" else "restoreproof")
    assert command.is_file(), "console script missing from target interpreter scripts directory"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        def cli(*args, expected=0):
            result = subprocess.run([str(command), *map(str, args)], capture_output=True, text=True, encoding="utf-8", check=False)
            assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
            return json.loads(result.stdout)
        cli("fixture", root / "app")
        cli("snapshot", "--source", root / "app/source", "--spec", root / "app/application.json", "--out", root / "backup")
        (root / "restores").mkdir()
        common = ["--archive", root / "backup/snapshot.zip", "--manifest", root / "backup/manifest.json"]
        planned = cli("plan", *common)
        assert planned["byte_integrity"] == "not_run"
        report = cli("drill", *common, "--parent", root / "restores")
        assert report["decision"] == "USABLE"
        restored = Path(report["destination"])
        with closing(sqlite3.connect(restored.joinpath("library.sqlite").as_uri() + "?mode=ro", uri=True)) as connection:
            docs = connection.execute("SELECT path,sha256,bytes FROM documents ORDER BY id").fetchall()
        assert len(docs) == 2
        for path, digest, size in docs:
            payload = (restored / path).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == digest and len(payload) == size
        cli("fixture", root / "broken", "--scenario", "missing_asset")
        cli("snapshot", "--source", root / "broken/source", "--spec", root / "broken/application.json", "--out", root / "broken-backup")
        common = ["--archive", root / "broken-backup/snapshot.zip", "--manifest", root / "broken-backup/manifest.json", "--parent", root / "restores"]
        assert cli("drill", *common, "--hash-only")["decision"] == "BYTE_VERIFIED"
        assert cli("drill", *common, expected=1)["issues"][0]["code"] == "ASSET_MISSING"
        print(json.dumps({"ordinary_install": True, "console_script_discovered_with_sysconfig": True, "independent_asset_oracle": "passed", "console_cases": 8}))


if __name__ == "__main__":
    main()
