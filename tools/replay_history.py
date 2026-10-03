"""Build exact Git archives as ordinary wheels and replay unchanged probe files.

Raw logs/paths stay under ignored .local. Historical suites run from each exact
archive; later-expanded suites are never attributed to earlier commits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

STATES = [
    ("ec5681706a1c023ea58df62bbd28bd8cbc440c23", 38),
    ("75d3703ad6eeda3ebfb02c0bfc6fe0d794d98b29", 40),
    ("4ab9053790b645e9cc61ec14277398d8b9f30b93", 41),
    ("ddc59c10d03405ac32de7eafbaa7e6b9c5d5f4e1", 43),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=".local/history")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    out = (repository / args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    probes = [repository / f"tools/probes/round{number}.py" for number in (1, 2, 3)]
    records = []
    for index, (commit, expected_count) in enumerate(STATES):
        root = out / commit[:7]
        root.mkdir()
        archive = root / "source.zip"
        subprocess.run(["git", "archive", "--format=zip", "--output", str(archive), commit], cwd=repository, check=True)
        source = root / "source"
        source.mkdir()
        # This archive is created from our own named Git commit, never user input.
        with zipfile.ZipFile(archive) as file:
            file.extractall(source)
        environment = root / "ordinary"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        def execute(name, command, expected=0):
            result = subprocess.run(list(map(str, command)), cwd=source, capture_output=True, text=True, encoding="utf-8", errors="replace")
            (root / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
            assert result.returncode == expected, (commit, name, result.returncode, expected)
            return result.stdout + result.stderr
        execute("build", [python, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", root / "wheels"])
        wheel = next((root / "wheels").glob("*.whl"))
        execute("install", [python, "-m", "pip", "install", "--no-deps", str(wheel)])
        tests = execute("tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"])
        count = int(re.search(r"Ran (\d+) tests", tests).group(1))
        assert count == expected_count
        execute("console", [python, "tools/verify_workflow.py"])
        execute("contrast", [python, "tools/contrast.py"])
        results = []
        for number, probe in enumerate(probes, 1):
            expected = 0 if index >= number else 1
            execute(f"round{number}", [python, probe], expected=expected)
            results.append({"round": number, "exit": expected, "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest()})
        records.append({"commit": commit, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "historical_tests": count,
                        "historical_suite": "passed", "ordinary_console": "passed", "same_archive_contrast": "passed", "probes": results})
        print(json.dumps({"historical_commit": commit, "tests": count, "probes": [r["exit"] for r in results]}), flush=True)
    result = {"environment": "actual executing Python " + sys.version.split()[0], "mode": "separate ordinary venv/site-packages per exact Git archive", "states": records}
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
