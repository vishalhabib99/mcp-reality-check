from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp_reality_check.engine import DEFAULT_TIMEOUT_SECONDS, run_reality_check
from mcp_reality_check.report import build_report, render_text, to_dict


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcp-reality-check",
        description="Checks whether an MCP server's successful tool responses actually reflect reality.",
    )
    parser.add_argument(
        "--include-destructive",
        action="store_true",
        help="Also call tools not annotated readOnlyHint=true. Only use against a server you're "
        "confident is safe to call blindly (a local sandbox, a test/staging backend).",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text.")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero if response sanity is below this percentage.",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Per-call timeout in seconds."
    )
    parser.add_argument(
        "--env", action="append", default=[], metavar="KEY=VALUE",
        help="pass an environment variable through to the target server (repeatable), e.g. "
        "--env BRAVE_API_KEY=... . Without this, only a safe minimal set (PATH, HOME, ...) "
        "is inherited — many real servers need an API key to start at all.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to launch the target MCP server, e.g. -- python server.py",
    )
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a target server command is required, e.g. mcp-reality-check -- python server.py")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    command, *rest = args.command

    env = {}
    for pair in args.env:
        key, sep, value = pair.partition("=")
        if not sep:
            print(f"error: --env expects KEY=VALUE, got {pair!r}", file=sys.stderr)
            return 2
        env[key] = value

    raw = asyncio.run(run_reality_check(
        command, rest, env=env or None, include_destructive=args.include_destructive, timeout=args.timeout
    ))
    report = build_report(raw)

    if args.json:
        print(json.dumps(to_dict(report), indent=2))
    else:
        print(render_text(report))

    if report.connect_error:
        return 2
    if args.fail_under is not None and report.sanity_percent is not None and report.sanity_percent < args.fail_under:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
