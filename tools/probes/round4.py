"""Public SDK/actual-console scalar counterexamples; use installed interpreter.

python restoreproof_scalar_boundary_probe.py
Exit zero only when BOTH malformed inputs become structured FAILED evidence.
No machine-specific paths are printed; temporary files are preserved by hashes.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
from restoreproof import drill, make_fixture, snapshot


def main():
    command = Path(sysconfig.get_path("scripts")) / ("restoreproof.exe" if sys.platform == "win32" else "restoreproof")
    assert command.is_file(), "registered console unavailable: harness cannot evaluate"
    results = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_fixture(root / "app")
        snapshot(root / "app/source", root / "app/application.json", root / "backup")
        archive, manifest = root / "backup/snapshot.zip", root / "backup/manifest.json"
        original = manifest.read_text(encoding="utf-8")
        for case in ("overlarge_real_exponent", "overlarge_json_integer"):
            data = json.loads(original)
            if case == "overlarge_real_exponent":
                data["application"]["queries"][0]["expected"] = [[{"type":"real", "value":"0x1p+9999999999"}]]
                payload = json.dumps(data)
            else:
                payload = original.replace('"size": ', '"size": ' + "9" * 5000, 1)
            manifest.write_text(payload, encoding="utf-8")
            parent = root / case
            parent.mkdir()
            before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, manifest)]
            sdk = None
            escaped = None
            try:
                sdk = drill(archive, manifest, parent)
            except Exception as error:
                escaped = type(error).__name__
            cli = subprocess.run([str(command), "drill", "--archive", str(archive), "--manifest", str(manifest), "--parent", str(parent)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            try:
                output = json.loads(cli.stdout)
                decision = output.get("decision")
            except json.JSONDecodeError:
                decision = None
            preserved = before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, manifest)]
            row = {"case":case, "sdk_escaped_exception":escaped,
                   "sdk_decision":sdk.get("decision") if sdk else None,
                   "cli_exit":cli.returncode,"cli_stdout_decision":decision,
                   "cli_traceback":"Traceback (most recent call last)" in cli.stderr,
                   "input_preserved":preserved,"destination_not_created":not list(parent.iterdir())}
            row["passed"] = escaped is None and row["sdk_decision"] == "FAILED" and cli.returncode == 1 and decision == "FAILED" and not row["cli_traceback"] and preserved and row["destination_not_created"]
            results.append(row)
    print(json.dumps({"cases":results,"passed":all(row["passed"] for row in results)}, indent=2))
    return 0 if all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
