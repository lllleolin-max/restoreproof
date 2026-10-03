# Verification evidence

Verified locally 2026-10-03, Windows/Python 3.14.3, version 0.1.0. Core correction source state: `ddc59c10d03405ac32de7eafbaa7e6b9c5d5f4e1`. The subsequent documentation/evidence commit does not change package code/tests. Final repository HEAD is obtained with `git rev-parse HEAD`; verification at that frozen HEAD is reported separately by the builder.

Actual ordinary **global interpreter install**:

```console
python -m pip wheel . --no-deps --wheel-dir .local/final-wheels
python -m pip install --force-reinstall .local/final-wheels/restoreproof-0.1.0-py3-none-any.whl
python -m unittest discover -s tests -v
python tools/verify_workflow.py
python tools/contrast.py
```

Observed: 43 tests PASS (1.411 seconds in this run); real console workflow PASS, module checked under target interpreter site-packages, console discovered using `sysconfig.get_path('scripts')`, independent SQLite/asset oracle PASS, eight console invocations; seven-case same-archive contrast PASS. No editable install was used. This global install was actually executed, not inferred from a virtual environment.

Also executed in a **new isolated ordinary environment**:

```console
python -m venv .local/fresh-current
# Run the following with that environment's Python, not the global interpreter:
python -m pip install --no-deps .local/final-wheels/restoreproof-0.1.0-py3-none-any.whl
python -m unittest discover -s tests -v
python tools/verify_workflow.py
python tools/contrast.py
```

Observed: 43 tests PASS (1.526 seconds), console/independent oracle PASS, contrast PASS. Windows environment interpreter is `.local/fresh-current/Scripts/python.exe`; POSIX is `.local/fresh-current/bin/python`. Those paths are environment layout only; **console discovery never assumes adjacency to Python**.

Actual [contrast output](evidence/contrast.json) discloses synthetic inputs and local durations. Both modes restore exactly the same archive/manifest under the same extraction bounds. Healthy: hash-only `BYTE_VERIFIED`, full `USABLE`. Missing asset, asset digest mismatch, foreign-key failure and wrong expected consumer result: all file hashes pass, but full mode fails with specific application issue codes. VM exhaustion: full mode fails as `QUERY_BUDGET`, not a claim of inconsistent data. Corrupted manifest digest: both fail. All independent source application/archive/manifest hashes remain unchanged.

[Historical evidence](evidence/history.json) and [iterations](ITERATIONS.md) preserve exact archive states, historical suite sizes, wheel hashes and unchanged probe boundaries. Initial failed development runs and their cleanup/writer setup mistakes are explicitly disclosed there.

CI config has ordinary runner wheel installs on Ubuntu/Windows and Python 3.11/3.14. Only local Windows/Python 3.14.3 was available in this build environment. Actual remote CI, independent axis scores and public GitHub publication are not established by these local results. No customer/adoption/revenue facts are claimed. Raw logs and generated artifacts remain ignored under `.local/`.
