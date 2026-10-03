"""Console interface. JSON stdout; success=0, failed evidence=1, usage/input=2."""
from __future__ import annotations
import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys
from .core import Limits, RestoreError, drill, plan, snapshot
from .fixture import make_fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="restoreproof", description="Bounded SQLite+asset restore drill evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    fixture = sub.add_parser("fixture", help="create a synthetic library application")
    fixture.add_argument("root")
    fixture.add_argument("--scenario", choices=["healthy", "missing_asset", "asset_mismatch", "foreign_key", "wrong_query"], default="healthy")
    snap = sub.add_parser("snapshot", help="copy quiescent standalone source to a new snapshot directory")
    snap.add_argument("--source", required=True)
    snap.add_argument("--spec", required=True)
    snap.add_argument("--out", required=True)
    for command in ("plan", "drill"):
        item = sub.add_parser(command)
        item.add_argument("--archive", required=True)
        item.add_argument("--manifest", required=True)
        if command == "drill":
            item.add_argument("--parent", required=True)
            item.add_argument("--hash-only", action="store_true", help="same extraction, omit application assertions")
            item.add_argument("--report", help="write JSON to a new report file")
        for field in fields(Limits):
            item.add_argument("--" + field.name.replace("_", "-"), type=int, default=getattr(Limits(), field.name))
    args = parser.parse_args(argv)
    try:
        if args.command == "fixture":
            result = make_fixture(args.root, args.scenario)
        elif args.command == "snapshot":
            result = snapshot(args.source, args.spec, args.out)
        else:
            limits = Limits(**{field.name: getattr(args, field.name) for field in fields(Limits)})
            if args.command == "plan":
                result = plan(args.archive, args.manifest, limits=limits)
            else:
                result = drill(args.archive, args.manifest, args.parent, limits=limits, application=not args.hash_only)
                if args.report:
                    with Path(args.report).open("x", encoding="utf-8", newline="\n") as stream:
                        json.dump(result, stream, indent=2, ensure_ascii=False)
                        stream.write("\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get("decision") == "FAILED" else 0
    except (RestoreError, OSError, ValueError) as exc:
        print(json.dumps({"error": exc.code if isinstance(exc, RestoreError) else "INPUT", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
