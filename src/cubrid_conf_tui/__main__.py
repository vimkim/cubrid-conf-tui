"""Installable CLI entry point."""

import argparse
import sys

from .app import ConfigurationApp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edit [common] with live discovery or limited offline mode."
    )
    parser.add_argument(
        "database",
        nargs="?",
        help="Database to observe; omitted: registry picker or offline editing",
    )
    args = parser.parse_args()
    if args.database and (
        args.database.startswith("-")
        or any(char.isspace() or ord(char) < 32 for char in args.database)
    ):
        parser.error(
            "database must be a non-option name without whitespace or controls"
        )
    app = ConfigurationApp(database=args.database)
    if app.error:
        print(f"cubrid-conf-tui: {app.error}", file=sys.stderr)
        raise SystemExit(2)
    app.run()


if __name__ == "__main__":
    main()
