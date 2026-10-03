# Verification evidence

## Current corrected 0.1.1

Current library/tests source is `8b67f210469a9652a052a45920f0bc25e2ebc323`; the later documentation/evidence commit changes no package code or tests. Local environment: Windows/Python 3.14.3. The rejected 0.1.0 state below remains historical evidence, not current acceptance.

The actual exact-Git-archive ordinary-wheel replay is [recorded in JSON](evidence/scalar-correction.json). Source archive SHA-256: `0c4525b8c762275f3049beb761b8ca5ef238a8f0dc62f9ac91a3b06aa8de8bf5`; measured wheel SHA-256: `1ab47c1b12d76c7bc5021d270d278c5338345aec3a3edd77925e008fc5775595`; core module SHA-256: `62117a312114d762f2791f5bad218833e3ecbd003dbbc904cc6f6f21deae4176`. All four installed `.py` module bytes matched both exact Git blobs and archive files. Rebuilding at another timestamp need not reproduce the wheel container hash.

Observed at that exact source: **59 tests PASS** (its own archived suite); registered console workflow PASS; independent restored SQLite/asset oracle PASS; unchanged peer scalar probe PASS; unchanged encoding probe PASS; original three probes PASS; peer-authored 20-app direct consumer oracle **20/20 PASS**; seven same-archive contrasts PASS. The original peer scalar probe remains byte-identical at SHA-256 `88162b9c958e87bafca682d2cfd65a19f57ae9bcb4664d5ceceba886d113c99e`, and was also executed from its untouched external review location during development. Both malformed inputs now yield SDK `FAILED`, actual CLI exit 1/JSON `FAILED`, no traceback, unchanged input hashes and no destination child.

Reproduce normal installation and current checks:

```console
python -m pip wheel . --no-deps --wheel-dir dist
python -c "import glob,subprocess,sys; subprocess.check_call([sys.executable,'-m','pip','install','--force-reinstall',*glob.glob('dist/restoreproof-0.1.1-*.whl')])"
python -m unittest discover -s tests -v
python tools/verify_workflow.py
python tools/probes/round4.py
python tools/probes/round5.py
python tools/peer_consumer_oracle.py
python tools/contrast.py
```

`tools/replay_boundary.py` additionally rebuilds the exact rejected/numeric/encoding commits and records 43/57/59 historical suite sizes. Its normal installs use separate fresh site-packages, and its actual consoles use the executing interpreter's `sysconfig.get_path('scripts')`; virtual-environment success is not used as proof of a current global installation. The old full three-cycle history was not silently reclassified as a new full run; its old evidence remains below and in `history.json`.

No re-review score, successful remote CI, public publication, real customer, revenue, authenticity or RPO/RTO fact follows from these local checks. The independent reviewer can still reject this corrected artifact; fixing the earlier cap does not automatically establish a score above 80.

Final checkout reproducibility check found that a real `core.autocrlf=true` clone converted the unchanged peer script to CRLF, making a raw hash guard fail before any product probe. Tracked Python LF attributes correct that checkout setup problem; it is not counted as another application-code correction. Ordinary wheel/module byte association and numeric/encoding probe results above refer to the named source states, independent of wheel timestamp hashes.

## Historical 0.1.0 build observations

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
