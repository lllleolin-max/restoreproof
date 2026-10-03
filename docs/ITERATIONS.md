# Review/correction evidence

Initial implementation `ec5681706a1c023ea58df62bbd28bd8cbc440c23` passed its own 38-test suite, ordinary installed console workflow and seven-case contrast on Windows/Python 3.14.3. Initial development had a failed run: SQLite fixture/oracle connections were not explicitly closed, causing Windows cleanup errors (31 errors), and the hostile-path writer normalized a backslash (one failed assertion). These were fixed before that initial commit; they are not counted as review cycles.

## Round 1: JSON escape scalars escaped the failure state machine

Before: `ec5681706a1c023ea58df62bbd28bd8cbc440c23`. Self-review injected a JSON-escaped lone surrogate in a manifest filename. `python tools/probes/round1.py` against the installed initial wheel exited 1 with `AssertionError: malformed JSON scalar escaped structured failure: UnicodeEncodeError`. The probe is unchanged across verification (source SHA-256 `174ecd601f355293044bb5ff796c34c3c1294f6852c19fc8a3ae26d0312fa7d8`).

Correction: validate every parsed JSON string/key for UTF-8 scalar encodability, including typed expected text; separately make SDK path validation emit `PATH` for invalid scalars. This prevents exceptions escaping `drill` and prevents malformed spec strings reaching Unicode serialization. Verification uses a newly built ordinary wheel, the same portable probe and two added regression cases. Exact after SHA and observed suite count are recorded after committing the correction, not guessed here.
