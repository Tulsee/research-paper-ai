"""Console entry point: ``research-paper-ai <command> [args]``."""

from __future__ import annotations

import sys

COMMANDS = {
    "inspect": "Parse a PDF and dump pages, blocks and offsets.",
    "process": "Run the full stage-1 pipeline (parse, enrich, chunk).",
    "check": "Measure stage-1 output against its exit criteria.",
}


def _usage() -> None:
    print("Usage: research-paper-ai <command> [args]")
    print()
    print("Commands:")

    for name, description in COMMANDS.items():
        print(f"  {name:9} {description}")

    print()
    print("Run a command with --help for its own options.")


def main() -> int:
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        _usage()
        return 0 if argv else 1

    command, rest = argv[0], argv[1:]

    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print()
        _usage()
        return 1

    if command == "inspect":
        from app.cli.inspect_pdf import main as run
    elif command == "process":
        from app.cli.process_pdf import main as run
    else:
        from app.eval.stage1_check import main as run

    return run(rest) or 0


if __name__ == "__main__":
    sys.exit(main())
