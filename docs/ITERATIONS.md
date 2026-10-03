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

Correction: resolve the destination before overlap checks and before any creation; inspect the original source root before resolving so a root symlink/reparse point cannot disappear from the link check. Added a source-inventory-preservation regression and a valid outside-source dot-alias case. Archive names still validate original spelling; only operator filesystem paths are resolved. After: `ddc59c10d03405ac32de7eafbaa7e6b9c5d5f4e1`, direct child of the before state. Newly built ordinary wheel: same probe PASS, **43 tests** PASS, ordinary console workflow and seven-case contrast PASS.

## Exact historical archive replay

`python tools/replay_history.py --out .local/history` actually rebuilt all four exact Git archives into separate ordinary virtual-environment wheels, then ran **each archive's own tests, console workflow and contrast**. It also ran the same current portable probe bytes against every historical installed wheel. Raw logs/paths are ignored; [sanitized machine evidence](evidence/history.json) records archive/wheel SHA-256 and probe fingerprints.

| Exact source commit | Archive's tests | Own console/contrast | Probe 1 exit | Probe 2 exit | Probe 3 exit |
|---|---:|---|---:|---:|---:|
| `ec5681706a1c023ea58df62bbd28bd8cbc440c23` | 38 PASS | PASS / PASS | 1 | 1 | 1 |
| `75d3703ad6eeda3ebfb02c0bfc6fe0d794d98b29` | 40 PASS | PASS / PASS | 0 | 1 | 1 |
| `4ab9053790b645e9cc61ec14277398d8b9f30b93` | 41 PASS | PASS / PASS | 0 | 0 | 1 |
| `ddc59c10d03405ac32de7eafbaa7e6b9c5d5f4e1` | 43 PASS | PASS / PASS | 0 | 0 | 0 |

Exit 1 is the intended probe assertion failure exposing an unresolved historical defect, not a passed run. Counts above are attached only to the named archived source states. Later tests were not copied into earlier suites. This replay is local Windows/Python 3.14.3 evidence; it does not claim remote CI or Python 3.11/Linux execution.

## Round 4: independent numeric-boundary rejection bypassed drill evidence

Before: rejected frozen commit `b7ae9be639e2ac45f5c8c693ed76a267c1618169`, version 0.1.0. The independent reviewer found (1) REAL expectation `0x1p+9999999999` leaking `OverflowError` and an actual console traceback, and (2) a 5,000-digit JSON file-size token leaking integer-conversion `ValueError` and console exit 2 without a drill report. These are genuine failed evidence guarantees; source preservation and normal application checks did not excuse them. The original rejected review remains unchanged outside this repository.

The peer-authored unchanged probe is preserved as [round4.py](../tools/probes/round4.py), source SHA-256 `88162b9c958e87bafca682d2cfd65a19f57ae9bcb4664d5ceceba886d113c99e`. Before correction, an ordinary wheel built from the exact rejected Git archive reproduced both SDK exceptions and console outcomes, and the probe returned 1. No source/destination corruption was observed; no failed probe was described as passing.

Correction: bound signed-64-bit integer token length/range before calling `int`, reject raw JSON floating tokens because the existing schema represents REALs as exact strings, constrain canonical finite binary64 hexadecimal spellings before `float.fromhex` and normalize its specific `ValueError`/`OverflowError` failures. Streaming JSON input reads avoid an oversized single native read request, and resource configurations reject unrepresentable JSON/native SQLite integer limits. No broad exception catch was added to `drill`; SQLite read-only/authorizer and phase semantics are unchanged. Version is 0.1.1.

The expanded suite adds 14 test methods (57 total) covering actual SDK/registered-console failures, long exponents/mantissas, signed integer overflow, huge raw float tokens, decoder nesting/Unicode/syntax, digit-limit independence, invalid constants/types, safe resource limits, 512 independently generated finite binary64 canonical strings, and actual extreme/subnormal/zero/integer/blob/null SQLite results from a separate SQLite connection. The dev ordinary wheel passed all 57, unchanged round4 probe, actual console workflow, peer consumer oracle and seven-case contrast. Exact after commit and final archived-wheel observations are recorded after committing and replaying, not assumed from this development run.

The peer-authored [consumer oracle](../tools/peer_consumer_oracle.py) is also copied byte-identically (SHA-256 `062f86d216570ff9451776bf6d2b0d6368a796bdb602286bc0fd159911a181a6`) with credit to the independent reviewer. It directly inspects 20 real restored synthetic SQLite applications and asset bytes without importing package validators/type converters. These are peer-authored checks executed by the builder, not newly independent acceptance or a self-score. [replay_boundary.py](../tools/replay_boundary.py) rebuilds the two exact ordinary wheels, binds all four installed module byte hashes to Git and archive bytes, and executes each state's own suite plus the unchanged probes/oracle/contrast. The original three-cycle historical evidence above is retained as its past actual run; it is not relabeled as a new full historical audit.
