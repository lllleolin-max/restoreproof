# Review/correction evidence

Initial implementation `ec5681706a1c023ea58df62bbd28bd8cbc440c23` passed its own 38-test suite, ordinary installed console workflow and seven-case contrast on Windows/Python 3.14.3. Initial development had a failed run: SQLite fixture/oracle connections were not explicitly closed, causing Windows cleanup errors (31 errors), and the hostile-path writer normalized a backslash (one failed assertion). These were fixed before that initial commit; they are not counted as review cycles.

## Round 1: JSON escape scalars escaped the failure state machine

Before: `ec5681706a1c023ea58df62bbd28bd8cbc440c23`. Self-review injected a JSON-escaped lone surrogate in a manifest filename. `python tools/probes/round1.py` against the installed initial wheel exited 1 with `AssertionError: malformed JSON scalar escaped structured failure: UnicodeEncodeError`. The probe is unchanged across verification (source SHA-256 `174ecd601f355293044bb5ff796c34c3c1294f6852c19fc8a3ae26d0312fa7d8`).

Correction: validate every parsed JSON string/key for UTF-8 scalar encodability, including typed expected text; separately make SDK path validation emit `PATH` for invalid scalars. This prevents exceptions escaping `drill` and prevents malformed spec strings reaching Unicode serialization. After: `75d3703ad6eeda3ebfb02c0bfc6fe0d794d98b29`, direct child of the before state. Newly built ordinary wheel: same probe PASS, **40 tests** PASS, ordinary console workflow PASS. Only that state's 40 tests are attributed to this correction.

## Round 2: metadata agreement was misreported after incomplete extraction

Before: `75d3703ad6eeda3ebfb02c0bfc6fe0d794d98b29`. Review of report semantics found that metadata preflight set `snapshot_agreement=passed` before actual extraction, so exhausting the decompression cap left a partial restore claiming completed snapshot agreement. Unchanged `python tools/probes/round2.py` exited 1 with `AssertionError: metadata preflight falsely certified actual snapshot agreement` on that ordinary wheel. Probe SHA-256: `9ea5f5a977e59d246bbdf23d1302b5baa704109e030a4967205148fd97bb4ac2`.

Correction: report metadata planning independently and defer actual snapshot agreement until all members have been decompressed and verified. Partial extraction stays `not_run` for agreement unless a concrete discrepancy is found. Added a partial-first-file regression and strengthened the existing decompression test. After: `4ab9053790b645e9cc61ec14277398d8b9f30b93`, direct child of the before state. Newly built ordinary wheel: same probe PASS; **41 tests** PASS; ordinary console workflow and seven-case contrast PASS. This changes actual machine-readable acceptance evidence, not just prose. The later 43-test suite is not attributed to this SHA.

## Round 3: destination dot alias contaminated the source inventory

Before: `4ab9053790b645e9cc61ec14277398d8b9f30b93`. Self-review exercised an output path spelling `spare/../app/source/inside-backup`. The lexical absolute-path containment test did not normalize `..`; snapshot creation wrote a ZIP and failure marker into the source tree before detecting inventory changes. Unchanged `python tools/probes/round3.py` exited 1 with `AssertionError: output alias wrote new backup artifacts into source before rejection`. Probe SHA-256: `2fa3ca93e7d2fec6fc659ddcbd4ae10191adeeb1519f7f2fa84f797efc108e01`.

Correction: resolve the destination before overlap checks and before any creation; inspect the original source root before resolving so a root symlink/reparse point cannot disappear from the link check. Added a source-inventory-preservation regression and a valid outside-source dot-alias case. Archive names still validate original spelling; only operator filesystem paths are resolved. After-state SHA and actual ordinary-wheel results follow after the correction commit.
