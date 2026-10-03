# Contributing

Keep the supported ZIP32/SQLite subset explicit. Extend it only with original-spelling/path/streaming resource tests and a consumer-useful oracle. Do not broaden SQL/function capabilities without reviewing authorizer and work limits. Preserve input bytes and existing destination files.

Build and install an ordinary wheel, run `python -m unittest discover -s tests -v`, `python tools/verify_workflow.py`, and `python tools/contrast.py`. The workflow harness must discover console scripts with the executing interpreter's `sysconfig.get_path('scripts')`; never infer their location from the Python executable. Do not commit raw logs, private filesystem paths or generated fixtures.

Changes should explain the actual problem, affected invariant, reproducible before/after probe and useful tradeoff. Contributions must not invent incumbent feature absence, production safety, customers or revenue. CI matrix is Ubuntu/Windows with Python 3.11 and 3.14; YAML is configuration until a run is observed.

Python files use tracked LF checkout attributes so module/probe fingerprints survive Windows `core.autocrlf=true` checkouts. Historical exact archives are exported with `git -c core.autocrlf=false archive` in the boundary driver. Do not change peer probe bytes to obtain a passing result.
