# Show available commands.
default:
    @just --list

# Install or refresh an independent user-level cubrid-conf-tui command.
sync:
    uv tool install --reinstall .
    @"$(uv tool dir --bin)/cubrid-conf-tui" --help >/dev/null
