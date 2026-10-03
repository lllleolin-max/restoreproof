# RestoreProof

Restore a small declared SQLite application and its assets into a fresh directory, then decide whether its **declared consumer behavior** survived. A byte-valid archive can still contain a database that references an absent document. RestoreProof reports that difference.

For maintainers of local document libraries, artifact catalogs and SQLite-backed desktop tools, the pilot job is a repeatable restore drill with actionable JSON evidence. This is a bounded local tool; it has no proven customers, revenue or willingness to pay.

中文：面向小型 SQLite+文件应用维护者，演练备份恢复后数据库、引用资源与声明查询是否一起可用。适合已停止写入的本地应用；运行中的 WAL 数据库、任意 ZIP 或通用灾备认证不在支持范围内。

## Quickstart / 快速开始

With Git installed, start from a new checkout / 首次使用先克隆并进入目录：

```console
git clone https://github.com/lllleolin-max/restoreproof.git
cd restoreproof
```

Python 3.11 or newer; standard-library runtime. Run from a clone in the intended environment. For an isolated install, run `python -m venv .venv`, then `.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in Bash. Start with an ordinary wheel install:

```console
python -m pip install .
```

With the target interpreter's scripts directory in PATH (or replace `restoreproof` with `python -m restoreproof.cli`):

```console
mkdir pilot
restoreproof fixture pilot/app
restoreproof snapshot --source pilot/app/source --spec pilot/app/application.json --out pilot/backup
mkdir pilot/restores
restoreproof plan --archive pilot/backup/snapshot.zip --manifest pilot/backup/manifest.json
restoreproof drill --archive pilot/backup/snapshot.zip --manifest pilot/backup/manifest.json --parent pilot/restores --report pilot/result.json
```

The fixture creates **synthetic** SQLite collections/documents and two actual text assets. `snapshot` accepts a quiescent standalone database, copies bytes and checks the source inventory/hashes afterward. `plan` checks metadata only (`PLANNED`, never integrity success). `drill` creates a randomly named new directory and returns `USABLE` only after byte, inventory, integrity, foreign-key, exact consumer-query and referenced-asset checks pass. Existing files in `pilot/restores` remain untouched. Failed partial restores remain available for diagnosis; the report labels them explicitly. Snapshot output directories and report files must be new.

中文：这个项目用于演练“备份恢复后，数据库与资源文件能否共同支持声明的应用行为”。先生成示例应用，再制作快照，最后恢复到新建隔离目录并执行只读查询。哈希正确只说明字节与清单一致；数据库指向丢失或错误资源时，应用层仍会失败。`tools/contrast.py` 使用同一份真实归档分别执行哈希校验和应用校验，展示这一决策差异。

CLI exit codes: `0` for successful operation (`USABLE`, `BYTE_VERIFIED`, `PLANNED`, snapshot/fixture creation); `1` for a failed drill report; `2` for invocation/input errors. Hash-only `BYTE_VERIFIED` explicitly leaves application assertions `not_run`.

## SDK

```python
from pathlib import Path
from restoreproof import Limits, drill, make_fixture, snapshot

root = Path("pilot")
root.mkdir(exist_ok=True)
make_fixture(root / "app")
snapshot(root / "app/source", root / "app/application.json", root / "backup")
(root / "restores").mkdir()
report = drill(root / "backup/snapshot.zip", root / "backup/manifest.json",
               root / "restores", limits=Limits(vm_steps=500_000))
assert report["decision"] == "USABLE", report["issues"]
```

Use a new `pilot` directory for the SDK example if you already ran the CLI example; `app` and `backup` must be new. On your own application, write a descriptor modeled on `pilot/app/application.json`, name the quiescent source database, and declare exact read-only consumer queries and asset-reference queries ([field reference](docs/FORMAT.md)). Keep the archive, manifest and JSON drill report together. Review `decision`, `issues` and `destination`; only `USABLE` confirms those declared assertions. Add missing consumer checks to your descriptor before relying on a drill for a release decision.

Public interfaces are `Limits`, `RestoreError.code`, `snapshot`, `plan`, `drill`, and `make_fixture`. See [format](docs/FORMAT.md), [architecture](docs/ARCHITECTURE.md), [comparison/pilot rationale](docs/COMPARISON.md), [iteration evidence](docs/ITERATIONS.md), [security](SECURITY.md), and [contributing](CONTRIBUTING.md).

Optional verification: `python tools/verify_workflow.py` discovers the real console script with the **target interpreter's** `sysconfig.get_path('scripts')`, verifies a site-packages install, runs source → snapshot → isolated restore, independently queries SQLite and hashes restored assets, and exercises a missing-asset failure. Run `python tools/contrast.py` for the synthetic comparison and `python -m unittest discover -s tests -v` for the suite. For a distributable wheel, use `python -m pip wheel . --no-deps --wheel-dir dist`.

CI installs into the runner interpreter on Ubuntu/Windows and Python 3.11/3.14. A local virtual-environment install is an isolated ordinary install, not proof that a global installation succeeded. Remote CI remains unverified until executed.

Version 0.1.1 normalizes malformed manifest numeric/encoding boundaries into preflight failed evidence. The unchanged peer-authored counterexample is runnable as `python tools/probes/round4.py`; `python tools/peer_consumer_oracle.py` separately inspects 20 synthetic restored applications. These checks support correction verification; an independent re-review decides acceptance.

## Supported boundary / 支持边界

- Strict single-disk ZIP32 with regular stored/deflate files, no ZIP64, directory entries, descriptors, extras or comments. This is a deliberately narrow generated/importable format, not a general ZIP extractor.
- Conservative portable NFC paths reject traversal, absolute/drive/UNC paths, backslashes, empty/dot components, duplicate/case/prefix collisions, Windows devices/ADS and trailing dots/spaces. Unicode controls and alternate NFC spelling are rejected.
- One quiescent rollback-mode SQLite database, no WAL/journal/shm sidecars; no live backup or filesystem-wide atomic snapshot claim. Source quiescence is an operator obligation; hash rechecks do not establish a simultaneous point in time.
- Declared read-only SQLite queries with an authorizer allowlist, cooperative VM/time bounds and shared result budgets; no shell assertions. Unsupported SQL and exhaustion fail the drill.
- Trusted local host and destination parent; directory isolation is not an OS sandbox. No RPO/RTO, disaster-readiness, authenticity, origin identity or customer guarantees. A digest proves neither who created a manifest nor whether its assertions are sufficient.

中文：适合小型、已停止写入的 SQLite+文件应用的恢复演练。它不替代 restic 等备份产品，不支持任意 ZIP、运行中的 WAL 数据库或任意程序执行。未声明的应用逻辑不在结论范围内，演练耗时也不等于灾备 RTO。

MIT licensed. Current verified artifact/commands and local limitations are recorded in [verification](docs/VERIFICATION.md). Independent evaluation can reject the project; no builder score is asserted.
