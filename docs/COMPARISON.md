# Established features, measured distinction and pilot economics

Primary sources checked 2026-10-03:

- [restic restoration](https://restic.readthedocs.io/en/stable/050_restore.html) documents real restores, overwrite policies, dry runs, restored-content checks and snapshot selection. These are established backup capabilities. RestoreProof is a narrow application drill tool and does not replace that repository/storage/backup system.
- [SQLite PRAGMA documentation](https://sqlite.org/pragma.html) distinguishes integrity from foreign-key checking. Both existing SQLite checks are used here; neither is a new validation algorithm.
- [SQLite authorizer](https://sqlite.org/c3ref/set_authorizer.html) supplies prepare-time access control; [Python sqlite3](https://docs.python.org/3/library/sqlite3.html) exposes authorizer/progress/limit APIs. They support a restricted local query runner, not an OS sandbox.
- [SQLite backup guidance](https://sqlite.org/backup.html) provides the established Online Backup API for live databases. This project instead requires a stopped, standalone rollback-mode source and makes no live consistency claim.

`python tools/contrast.py` executes the identical archive and manifest twice with identical extraction limits. Baseline is RestoreProof's actual strict extraction/CRC/SHA path with application checks disabled. Full mode adds actual restored SQLite consumer/integrity/FK queries and referenced-asset checks. It does **not execute restic**, and supplies no superiority or incumbent-absence claim.

Seven disclosed synthetic cases: healthy (both byte verification and full checks pass); missing asset reference; mismatched database-recorded asset digest; broken foreign key; wrong consumer query expectation; application VM budget exhausted; corrupted manifest digest (both modes fail). All source application/archive/manifest hashes are independently checked unchanged. The application-inconsistent cases are byte-valid archives; this is the useful decision difference. Exhaustion is an adverse limitation, not evidence a legitimate app is broken. A complete correct backup still passes both paths; this is the favorable baseline case.

Prospective user/buyer: the maintainer or small platform team responsible for SQLite-backed document/artifact applications with side files. Concrete cost mechanism: byte-only drills can miss a restored index that points to absent payloads, requiring a separate manual opening/join/file audit. This tool folds declared consumer assertions into a repeatable run with machine-readable issue codes and failed destination diagnosis.

Pilot proposal (reasoned, not measured customer economics): define three meaningful queries and a complete asset-reference query for one stopped small application; run the seven-case contrast; schedule actual own-data drills externally; measure operator time and false-negative references over several known injected faults. If manual validation takes 15 minutes and maintained automation saves 10 minutes per weekly drill, gross labor saved is about 8.7 hours/year/app. At an assumed labor cost of $50/hour that is ~$435/year before assertion maintenance, review, storage and support costs. None of those assumptions is validated here. Local synthetic durations prove execution only, not economic savings, RTO or RPO.

中文：为什么做——文件校验无法发现“数据库索引与附件不匹配”的逻辑问题；该工具把恢复、查询和附件检查串成可重复流程。怎样试用——给自己的停止写入的小型应用声明查询和附件引用规则，先用合成故障演练，再测量真实人工核验时间。使用价值仍需要用户验证，收入、客户和付费意愿均未知。
