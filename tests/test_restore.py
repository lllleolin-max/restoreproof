from __future__ import annotations
from dataclasses import replace
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import struct
import tempfile
import unittest
import zipfile

from restoreproof import Limits, RestoreError, drill, make_fixture, plan, snapshot
from restoreproof.core import digest_file, portable_path, typed_cell, validate_names


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.parent = self.root / "restores"
        self.parent.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, scenario="healthy"):
        make_fixture(self.root / "app", scenario)
        snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        return self.root / "backup/snapshot.zip", self.root / "backup/manifest.json"

    def run_drill(self, paths, **kwargs):
        return drill(*paths, self.parent, **kwargs)

    def update_app(self, paths, edit):
        data = json.loads(paths[1].read_text(encoding="utf-8"))
        edit(data["application"])
        paths[1].write_text(json.dumps(data), encoding="utf-8")

    def assert_failed(self, report, code):
        self.assertEqual(report["decision"], "FAILED")
        self.assertEqual(report["issues"][0]["code"], code)

    def test_real_restored_app_independent_oracle(self):
        paths = self.fixture()
        before = {p.relative_to(self.root).as_posix(): digest_file(p) for p in (self.root / "app").rglob("*") if p.is_file()}
        before.update({"zip": digest_file(paths[0]), "manifest": digest_file(paths[1])})
        report = self.run_drill(paths)
        self.assertEqual(report["decision"], "USABLE", report)
        dest = Path(report["destination"])
        with closing(sqlite3.connect(dest.joinpath("library.sqlite").as_uri() + "?mode=ro", uri=True)) as con:
            rows = con.execute("SELECT c.title,d.path,d.sha256,d.bytes FROM documents d JOIN collections c ON c.id=d.collection_id ORDER BY d.id").fetchall()
        self.assertEqual(len(rows), 2)
        for title, name, expected, length in rows:
            payload = (dest / name).read_bytes()
            self.assertEqual(title, "Recovery handbook")
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)
            self.assertEqual(len(payload), length)
        after = {p.relative_to(self.root).as_posix(): digest_file(p) for p in (self.root / "app").rglob("*") if p.is_file()}
        after.update({"zip": digest_file(paths[0]), "manifest": digest_file(paths[1])})
        self.assertEqual(before, after)
        self.assertEqual(report["source_preserved"], "passed")

    def test_missing_asset_changes_decision_with_all_archive_hashes_valid(self):
        paths = self.fixture("missing_asset")
        baseline = self.run_drill(paths, application=False)
        report = self.run_drill(paths)
        self.assertEqual(baseline["decision"], "BYTE_VERIFIED")
        self.assert_failed(report, "ASSET_MISSING")
        self.assertEqual(report["byte_integrity"], "passed")
        self.assertEqual(report["snapshot_agreement"], "passed")

    def test_mismatched_asset_changes_decision(self):
        paths = self.fixture("asset_mismatch")
        self.assertEqual(self.run_drill(paths, application=False)["decision"], "BYTE_VERIFIED")
        self.assert_failed(self.run_drill(paths), "ASSET_MISMATCH")

    def test_foreign_key_in_restored_database(self):
        paths = self.fixture("foreign_key")
        self.assert_failed(self.run_drill(paths), "SQLITE_FOREIGN_KEY")

    def test_consumer_expected_results(self):
        self.assert_failed(self.run_drill(self.fixture("wrong_query")), "QUERY_EXPECTATION")

    def test_manifest_digest_corruption(self):
        paths = self.fixture()
        data = json.loads(paths[1].read_text())
        data["files"][0]["sha256"] = "0" * 64
        paths[1].write_text(json.dumps(data))
        report = self.run_drill(paths)
        self.assert_failed(report, "BYTE_INTEGRITY")
        self.assertEqual(report["lifecycle"], "partial_failed")
        self.assertEqual(report["application_assertions"], "not_run")

    def test_source_archive_byte_corruption(self):
        paths = self.fixture()
        data = bytearray(paths[0].read_bytes())
        name_length = struct.unpack_from("<H", data, 26)[0]
        data[30 + name_length + 3] ^= 1
        paths[0].write_bytes(data)
        report = self.run_drill(paths)
        self.assertEqual(report["decision"], "FAILED")
        self.assertIn(report["issues"][0]["code"], ("BYTE_INTEGRITY", "IO_OR_FORMAT", "SNAPSHOT", "ARCHIVE"))

    def test_file_set_missing_or_extra(self):
        paths = self.fixture()
        data = json.loads(paths[1].read_text())
        data["files"].append({"path": "extra", "size": 0, "sha256": hashlib.sha256(b"").hexdigest()})
        paths[1].write_text(json.dumps(data))
        self.assert_failed(self.run_drill(paths), "SNAPSHOT")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_existing_parent_files_are_untouched_and_new_destination_each_time(self):
        paths = self.fixture()
        sentinel = self.parent / "keep"
        sentinel.write_bytes(b"existing user data")
        one, two = self.run_drill(paths), self.run_drill(paths)
        self.assertNotEqual(one["destination"], two["destination"])
        self.assertEqual(sentinel.read_bytes(), b"existing user data")

    def test_declared_size_bool_rejected(self):
        paths = self.fixture()
        data = json.loads(paths[1].read_text())
        data["files"][0]["size"] = True
        paths[1].write_text(json.dumps(data))
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_duplicate_manifest_paths(self):
        paths = self.fixture()
        data = json.loads(paths[1].read_text())
        data["files"].append(data["files"][0])
        paths[1].write_text(json.dumps(data))
        self.assert_failed(self.run_drill(paths), "COLLISION")

    def test_duplicate_json_keys(self):
        paths = self.fixture()
        paths[1].write_text('{"format":"first","format":"second"}')
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_nonfinite_json_rejected(self):
        paths = self.fixture()
        paths[1].write_text('{"format":NaN}')
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_escaped_surrogate_returns_structured_failure(self):
        paths = self.fixture()
        data = json.loads(paths[1].read_text())
        data["files"][0]["path"] = "\ud800"
        paths[1].write_text(json.dumps(data))
        self.assert_failed(self.run_drill(paths), "MANIFEST")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_escaped_surrogate_in_expected_text_is_rejected(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app["queries"][0].update(expected=[[{"type": "text", "value": "\udfff"}]]))
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_untrusted_extra_manifest_keys(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app.update(shell="echo unsafe"))
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_metadata_plan_does_not_claim_integrity(self):
        report = plan(*self.fixture())
        self.assertEqual(report["status"], "PLANNED")
        self.assertEqual(report["byte_integrity"], "not_run")

    def test_shared_vm_budget(self):
        paths = self.fixture()
        report = self.run_drill(paths, limits=replace(Limits(), vm_steps=1))
        self.assert_failed(report, "QUERY_BUDGET")
        self.assertEqual(report["byte_integrity"], "passed")
        self.assertEqual(report["application_assertions"], "failed")

    def test_recursive_query_budget(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app["queries"][0].update(sql="WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n"))
        self.assert_failed(self.run_drill(paths, limits=replace(Limits(), vm_steps=5000)), "QUERY_BUDGET")

    def test_shared_result_row_budget(self):
        paths = self.fixture()
        self.assert_failed(self.run_drill(paths, limits=replace(Limits(), rows=1)), "QUERY_BUDGET")

    def test_shared_result_byte_budget(self):
        paths = self.fixture()
        self.assert_failed(self.run_drill(paths, limits=replace(Limits(), result_bytes=1)), "QUERY_BUDGET")

    def test_sql_unsafe_operations_are_denied(self):
        paths = self.fixture()
        original = paths[1].read_text()
        for sql in ("ATTACH DATABASE ':memory:' AS hostile", "DELETE FROM documents", "PRAGMA journal_mode=WAL", "SELECT load_extension('x')", "SELECT randomblob(1000000)", "VACUUM", "SELECT 1; SELECT 2"):
            with self.subTest(sql=sql):
                paths[1].write_text(original)
                self.update_app(paths, lambda app: app["queries"][0].update(sql=sql))
                self.assert_failed(self.run_drill(paths), "QUERY")

    def test_type_exact_results_integer_vs_real(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app["queries"][0].update(sql="SELECT 1.0", expected=[[typed_cell(1)]]))
        self.assert_failed(self.run_drill(paths), "QUERY_EXPECTATION")

    def test_blob_null_text_real_expected_supported(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app["queries"][0].update(sql="SELECT X'00ff',NULL,'中文',1.5", expected=[[typed_cell(b"\x00\xff"), typed_cell(None), typed_cell("中文"), typed_cell(1.5)]]))
        self.assertEqual(self.run_drill(paths)["decision"], "USABLE")

    def test_boolean_expected_integer_rejected(self):
        paths = self.fixture()
        self.update_app(paths, lambda app: app["queries"][0].update(expected=[[{"type": "integer", "value": True}]]))
        self.assert_failed(self.run_drill(paths), "MANIFEST")

    def test_asset_query_invalid_shape_and_path(self):
        paths = self.fixture()
        original = paths[1].read_text()
        for sql, code in (("SELECT 1", "ASSET_REFERENCE"), ("SELECT '../escape','" + "0" * 64 + "'", "PATH")):
            paths[1].write_text(original)
            self.update_app(paths, lambda app: app["assets"][0].update(sql=sql))
            self.assert_failed(self.run_drill(paths), code)

    def test_snapshot_no_overwrite(self):
        self.fixture()
        before = digest_file(self.root / "backup/snapshot.zip")
        with self.assertRaises(FileExistsError):
            snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        self.assertEqual(before, digest_file(self.root / "backup/snapshot.zip"))

    def test_snapshot_wal_header_rejected_even_without_sidecars(self):
        make_fixture(self.root / "app")
        db = self.root / "app/source/library.sqlite"
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        with self.assertRaises(RestoreError) as error:
            snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        self.assertEqual(error.exception.code, "SQLITE_SNAPSHOT")

    def test_snapshot_sidecar_rejected(self):
        make_fixture(self.root / "app")
        (self.root / "app/source/library.sqlite-journal").write_bytes(b"pending")
        with self.assertRaises(RestoreError) as error:
            snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        self.assertEqual(error.exception.code, "SQLITE_SNAPSHOT")

    def test_corrupt_sqlite_hash_valid_rejected(self):
        make_fixture(self.root / "app")
        db = self.root / "app/source/library.sqlite"
        data = bytearray(db.read_bytes())
        data[100:110] = b"\xff" * 10
        db.write_bytes(data)
        snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        report = self.run_drill((self.root / "backup/snapshot.zip", self.root / "backup/manifest.json"))
        self.assertEqual(report["decision"], "FAILED")
        self.assertEqual(report["byte_integrity"], "passed")

    def test_snapshot_source_total_cap_actual(self):
        make_fixture(self.root / "app")
        with self.assertRaises(RestoreError) as error:
            snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup", limits=replace(Limits(), total_bytes=10))
        self.assertEqual(error.exception.code, "SOURCE_LIMIT")
        self.assertTrue((self.root / "backup/FAILED").is_file())

    def hostile(self, entries):
        archive = self.root / "hostile.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name, payload, mode in entries:
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = mode << 16
                out.writestr(info, payload)
        # A minimal manifest can reference one entry as a DB; paths get validated
        # in both representations, so hostile archive spellings must stand alone.
        return archive

    def test_hostile_original_path_spellings(self):
        from restoreproof.core import parse_archive
        for name in ("../escape", "/absolute", "C:/drive", "//server/share", "a\\b", "a//b", "a/./b", "a/../b", "a/", "CON", "com1.txt", "LPT¹", "file:stream", "dot.", "space ", "e\u0301.txt", "nul\x00tail"):
            with self.subTest(name=name):
                # ZIP writers themselves truncate NUL. Test the original spelling directly.
                if "\x00" in name:
                    with self.assertRaises(RestoreError):
                        portable_path(name)
                else:
                    archive = self.hostile([(name.replace("\\", "/"), b"x", stat.S_IFREG | 0o600)])
                    if "\\" in name:
                        archive.write_bytes(archive.read_bytes().replace(b"a/b", b"a\\b"))
                    with self.assertRaises(RestoreError):
                        parse_archive(archive, Limits())

    def test_case_unicode_and_prefix_collisions(self):
        for names in (["A", "a"], ["a", "a/x"], ["a/x", "a"], ["Assets/a", "assets/b"], ["Straße", "STRASSE"], ["same", "same"]):
            with self.subTest(names=names), self.assertRaises(RestoreError):
                validate_names(names)

    def test_unicode_safe_names(self):
        validate_names(["文档/恢复.txt", "文档/说明.txt"])

    def test_link_device_directory_entries_rejected(self):
        from restoreproof.core import parse_archive
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFCHR | 0o600, stat.S_IFDIR | 0o700, stat.S_IFIFO | 0o600):
            with self.subTest(mode=mode):
                path = self.hostile([("unsafe", b"target", mode)])
                with self.assertRaises(RestoreError) as error:
                    parse_archive(path, Limits())
                self.assertEqual(error.exception.code, "ENTRY")

    def test_archive_member_cap(self):
        from restoreproof.core import parse_archive
        path = self.hostile([("a", b"a", stat.S_IFREG), ("b", b"b", stat.S_IFREG)])
        with self.assertRaises(RestoreError) as error:
            parse_archive(path, replace(Limits(), members=1))
        self.assertEqual(error.exception.code, "MEMBER_LIMIT")

    def test_decompression_total_limit(self):
        paths = self.fixture()
        report = self.run_drill(paths, limits=replace(Limits(), total_bytes=10))
        self.assert_failed(report, "DECOMPRESS_LIMIT")
        self.assertEqual(report["lifecycle"], "partial_failed")
        self.assertEqual(report["metadata_plan"], "passed")
        self.assertEqual(report["snapshot_agreement"], "not_run")

    def test_snapshot_agreement_requires_all_actual_sizes(self):
        paths = self.fixture()
        report = self.run_drill(paths, limits=replace(Limits(), total_bytes=1))
        self.assert_failed(report, "DECOMPRESS_LIMIT")
        self.assertNotEqual(report["snapshot_agreement"], "passed")
        self.assertEqual(report["metrics"]["restored_files"], 0)
        self.assertEqual(report["application_assertions"], "not_run")

    def test_actual_decompression_not_advertised_size(self):
        paths = self.fixture()
        # An attacker advertises one byte yet supplies a 1 MiB deflate stream.
        payload = b"A" * (1024 * 1024)
        malicious = self.hostile([("library.sqlite", payload, stat.S_IFREG | 0o600)])
        raw = bytearray(malicious.read_bytes())
        central = raw.find(b"PK\x01\x02")
        struct.pack_into("<I", raw, 22, 1)
        struct.pack_into("<I", raw, central + 24, 1)
        malicious.write_bytes(raw)
        data = json.loads(paths[1].read_text())
        data["files"] = [{"path": "library.sqlite", "size": 1, "sha256": hashlib.sha256(b"A").hexdigest()}]
        paths[1].write_text(json.dumps(data))
        report = self.run_drill((malicious, paths[1]), limits=replace(Limits(), file_bytes=1024))
        self.assert_failed(report, "DECOMPRESS_LIMIT")
        self.assertGreater(report["metrics"]["decompressed_bytes"], 1024)

    def test_truncated_archive(self):
        paths = self.fixture()
        paths[0].write_bytes(paths[0].read_bytes()[:-7])
        self.assertEqual(self.run_drill(paths)["decision"], "FAILED")

    def test_limits_reject_bool_zero_negative(self):
        for value in (True, 0, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(RestoreError):
                Limits(vm_steps=value)


if __name__ == "__main__":
    unittest.main()
