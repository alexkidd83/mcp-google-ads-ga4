"""AdLoop — MCP server connecting Google Ads + GA4 + codebase."""

import sys

__version__ = "0.6.4"

# Module-level read-only flag. When True, all write tools reject execution.
_read_only: bool = False


def main() -> None:
    """Entry point for `adloop` console script.

    Routes to the setup wizard when called as ``adloop init``,
    otherwise starts the MCP server.

    Flags:
        --read-only  Start in read-only mode — write tools are visible but
                     reject execution.
    """
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"adloop {__version__}")
        return

    global _read_only

    if "--read-only" in sys.argv:
        _read_only = True
        sys.argv.remove("--read-only")

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        from adloop.cli import run_init_wizard

        try:
            run_init_wizard()
        except KeyboardInterrupt:
            print("\n\n  Setup cancelled.\n")
            sys.exit(130)
    else:
        from adloop.server import mcp

        mcp.run()
