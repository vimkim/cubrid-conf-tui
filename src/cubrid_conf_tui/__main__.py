"""Installable CLI entry point."""

import argparse
import sys

from .app import ConfigurationApp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edit existing [common] settings in limited offline mode."
    )
    parser.parse_args()
    app = ConfigurationApp()
    if app.error:
        print(f"cubrid-conf-tui: {app.error}", file=sys.stderr)
        raise SystemExit(2)
    app.run()


if __name__ == "__main__":
    main()
