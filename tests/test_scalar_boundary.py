"""Actual manifest SDK/console boundaries and an independent SQLite value oracle."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import struct
import subprocess
import sys
import sysconfig
import tempfile
import unittest

from restoreproof import Limits, RestoreError, drill, make_fixture, plan, snapshot


class ScalarBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        make_fixture(self.root / "app")
        snapshot(self.root / "app/source", self.root / "app/application.json", self.root / "backup")
        self.archive = self.root / "backup/snapshot.zip"
        self.manifest = self.root / "backup/manifest.json"
        self.original = self.manifest.read_text(encoding="utf-8")
        self.parent = self.root / "restores"
        self.parent.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def payload(self, cell):
        data = json.loads(self.original)
        data["application"]["queries"][0]["expected"] = [[cell]]
        return json.dumps(data)

    def fingerprints(self):
        return [hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.archive, self.manifest)]

    def size_token(self, token):
        number = json.loads(self.original)["files"][0]["size"]
        return self.original.replace('"size": ' + str(number), '"size": ' + token, 1)

    def reject(self, payload, *, console=False):
        self.manifest.write_bytes(payload if type(payload) is bytes else payload.encode("utf-8"))
        before = self.fingerprints()
        report = drill(self.archive, self.manifest, self.parent)
        self.assertEqual(report["decision"], "FAILED", report)
        self.assertEqual(report["issues"][0]["code"], "MANIFEST", report)
        self.assertEqual(report["phase"], "preflight")
        self.assertEqual(report["lifecycle"], "not_created")
        self.assertIsNone(report["destination"])
        self.assertEqual(report["source_preserved"], "passed")
        self.assertEqual(report["byte_integrity"], "not_run")
        self.assertEqual(report["application_assertions"], "not_run")
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual(before, self.fingerprints())
        # Planning remains metadata-only and rejects invalid data by RestoreError,
        # instead of becoming a misleading PLANNED or drill-success response.
        with self.assertRaises(RestoreError) as error:
            plan(self.archive, self.manifest)
        self.assertEqual(error.exception.code, "MANIFEST")
        if console:
            command = Path(sysconfig.get_path("scripts")) / ("restoreproof.exe" if sys.platform == "win32" else "restoreproof")
            self.assertTrue(command.is_file(), "tests require an ordinary console install")
            result = subprocess.run([str(command), "drill", "--archive", str(self.archive),
                                     "--manifest", str(self.manifest), "--parent", str(self.parent)],
                                    capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 1, (result.stdout, result.stderr))
            self.assertEqual(result.stderr, "")
            cli = json.loads(result.stdout)
            self.assertEqual(cli["decision"], "FAILED")
            self.assertEqual(cli["issues"][0]["code"], "MANIFEST")
            self.assertEqual(cli["lifecycle"], "not_created")
            self.assertEqual(before, self.fingerprints())
            self.assertEqual(list(self.parent.iterdir()), [])

    def test_peer_real_overflow_sdk_and_actual_console(self):
        self.reject(self.payload({"type": "real", "value": "0x1p+9999999999"}), console=True)

    def test_peer_5000_digit_integer_sdk_and_actual_console(self):
        self.reject(self.original.replace('"size": ', '"size": ' + "9" * 5000, 1), console=True)

    def test_bounded_real_overflow_underflow_nonfinite_and_noncanonical(self):
        for value in ("0x1.0000000000000p+9999", "-0x1.0000000000000p+9999",
                      "0x1.0000000000000p-9999", "-0x1.0000000000000p-9999",
                      "0x1.fffffffffffffp+1024", "0x1.0000000000000p-1023",
                      "inf", "-inf", "Infinity", "NaN", "nan", "1.0", "0X1.0P+0",
                      "0x1.0p+0", "0x0.0000000000000p+0", "0x1.0000000000000p+0001"):
            with self.subTest(value=value):
                self.reject(self.payload({"type": "real", "value": value}))

    def test_enormous_real_tokens_rejected_without_native_conversion(self):
        for value in ("0x1p+" + "9" * 100_000, "0x1p-" + "9" * 100_000,
                      "0x1." + "0" * 100_000 + "p+0"):
            with self.subTest(prefix=value[:6]):
                self.reject(self.payload({"type": "real", "value": value}))

    def test_signed_integer_range_enforced_before_decimal_conversion(self):
        for token in (str(1 << 63), str(-(1 << 63) - 1), "9" * 100_000, "-" + "9" * 100_000):
            with self.subTest(prefix=token[:20]):
                self.reject(self.size_token(token))

    def test_json_float_tokens_cannot_be_raw_exact_integer_or_real_values(self):
        for token in ("1.0", "1e309", "-1e9999999999", "1e-9999999999",
                      "9" * 5000 + ".0", "0.1e" + "9" * 5000):
            with self.subTest(prefix=token[:20]):
                self.reject(self.size_token(token))

    def test_json_integer_limit_is_independent_of_global_digit_configuration(self):
        original_limit = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(0)
            self.reject(self.original.replace('"size": ', '"size": ' + "9" * 5000, 1))
        finally:
            sys.set_int_max_str_digits(original_limit)

    def test_nested_decoder_invalid_unicode_and_syntax_still_report_failures(self):
        for payload in (b"\xff", b'{"format": "\xff"}', "[" * 6000 + "0" + "]" * 6000,
                        self.payload({"type": "text", "value": "\ud800"}), "{", "[] trailing"):
            with self.subTest(prefix=str(payload)[:20]):
                self.reject(payload)

    def test_utf16_utf32_byte_autodetection_is_rejected_in_sdk_and_console(self):
        for encoding in ("utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
            with self.subTest(encoding=encoding):
                self.reject(self.original.encode(encoding), console=True)

    def test_utf8_bom_and_unescaped_text_preserve_legal_manifest_behavior(self):
        data = json.loads(self.original)
        data["application"]["queries"][0].update(sql="SELECT '恢复文档'", expected=[[{"type": "text", "value": "恢复文档"}]])
        self.manifest.write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8-sig"))
        report = drill(self.archive, self.manifest, self.parent)
        self.assertEqual(report["decision"], "USABLE", report)
        self.assertEqual(report["source_preserved"], "passed")

    def test_nonfinite_json_constants_and_wrong_cell_types(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.reject(self.size_token(token))
        for cell in ({"type": "integer", "value": False}, {"type": "integer", "value": True},
                     {"type": "real", "value": 1.0}, {"type": "real", "value": None},
                     {"type": "blob", "value": "ABC"}, {"type": "integer", "value": 1 << 63},
                     {"type": "integer", "value": -(1 << 63) - 1}):
            with self.subTest(cell=cell):
                self.reject(self.payload(cell))

    def test_canonical_real_integer_blob_and_null_values_use_sqlite_oracle(self):
        # Compute expectations with an independent direct SQLite connection. It
        # observes SQLite's actual real/subnormal/negative-zero return behavior.
        sql = "SELECT 1.7976931348623157e308, 2.2250738585072014e-308, 4.9406564584124654e-324, -0.0, 0.0, -9223372036854775808, 9223372036854775807, X'00ff', NULL, '中文'"
        with closing(sqlite3.connect(":memory:")) as connection:
            row = connection.execute(sql).fetchone()
        cells = []
        for value in row:
            typ = "null" if value is None else {float: "real", int: "integer", bytes: "blob", str: "text"}[type(value)]
            encoded = value.hex() if type(value) in (float, bytes) else value
            cells.append({"type": typ, "value": encoded})
        data = json.loads(self.original)
        data["application"]["queries"][0].update(sql=sql, expected=[cells])
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(plan(self.archive, self.manifest)["status"], "PLANNED")
        report = drill(self.archive, self.manifest, self.parent)
        self.assertEqual(report["decision"], "USABLE", report)

    def test_ieee_finite_real_canonical_spelling_roundtrips(self):
        values = [0.0, -0.0, sys.float_info.max, -sys.float_info.max, sys.float_info.min,
                  float.fromhex("0x0.0000000000001p-1022")]
        rng = random.Random(109)
        while len(values) < 512:
            value = struct.unpack("!d", rng.getrandbits(64).to_bytes(8, "big"))[0]
            if math.isfinite(value):
                values.append(value)
        # A valid plan is enough to establish canonical parser acceptance; this
        # does not invent a consumer SQL result for these arbitrary finite bits.
        data = json.loads(self.original)
        data["application"]["queries"][0]["expected"] = [[{"type": "real", "value": value.hex()}] for value in values]
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(plan(self.archive, self.manifest)["status"], "PLANNED")

    def test_representable_resource_limits_reject_sqlite_abi_overflow(self):
        for field in ("sql_bytes", "cell_bytes"):
            with self.subTest(field=field), self.assertRaises(RestoreError) as error:
                replace(Limits(), **{field: 1 << 31})
            self.assertEqual(error.exception.code, "LIMIT")
        for field in ("seconds", "vm_steps", "manifest_bytes", "file_bytes", "rows"):
            with self.subTest(field=field), self.assertRaises(RestoreError) as error:
                replace(Limits(), **{field: 1 << 10000})
            self.assertEqual(error.exception.code, "LIMIT")

    def test_large_representable_manifest_read_and_native_limits_do_not_overflow(self):
        limits = replace(Limits(), manifest_bytes=(1 << 63) - 1,
                         sql_bytes=(1 << 31) - 1, cell_bytes=(1 << 31) - 1)
        report = drill(self.archive, self.manifest, self.parent, limits=limits)
        self.assertEqual(report["decision"], "USABLE", report)
        self.assertEqual(report["source_preserved"], "passed")

    def test_integer_zero_spelling_retains_legal_semantics(self):
        data = json.loads(self.original)
        data["application"]["queries"][0].update(sql="SELECT 0", expected=[[{"type": "integer", "value": 0}]])
        payload = json.dumps(data).replace('"value": 0', '"value": -0')
        self.manifest.write_text(payload, encoding="utf-8")
        report = drill(self.archive, self.manifest, self.parent)
        self.assertEqual(report["decision"], "USABLE", report)


if __name__ == "__main__":
    unittest.main()
