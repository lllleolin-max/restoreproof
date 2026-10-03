"""Unchanged before/after oracle: a dotted output alias must not pollute source."""
from pathlib import Path
import tempfile
from restoreproof import RestoreError, make_fixture, snapshot
from restoreproof.core import digest_file


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        make_fixture(root / "app")
        (root / "spare").mkdir()
        source = root / "app/source"
        before = {p.relative_to(source).as_posix(): digest_file(p) for p in source.rglob("*") if p.is_file()}
        alias = root / "spare" / ".." / "app/source/inside-backup"
        code = None
        try:
            snapshot(source, root / "app/application.json", alias)
        except RestoreError as error:
            code = error.code
        after = {p.relative_to(source).as_posix(): digest_file(p) for p in source.rglob("*") if p.is_file()}
        assert before == after, "output alias wrote new backup artifacts into source before rejection"
        assert code == "SOURCE" and not (source / "inside-backup").exists(), (code, list(after))
    print("PASS: dotted destination alias rejected before source mutation")


if __name__ == "__main__":
    main()
