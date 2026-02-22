"""
uup_builder.output
------------------
Shared console helpers and logging setup.
Falls back gracefully if ``rich`` is not installed.
"""

from __future__ import annotations

import logging
import sys

try:
    from rich.console import Console
    from rich.logging import RichHandler

    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None  # type: ignore[assignment]

__all__ = [
    "HAS_RICH",
    "console",
    "setup_logging",
    "print_msg",
    "print_ok",
    "print_err",
    "print_info",
    "bail",
]


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging. Call once at CLI startup."""
    level = logging.DEBUG if verbose else logging.INFO
    if HAS_RICH:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )


def print_msg(msg: str, style: str = "") -> None:
    if HAS_RICH:
        console.print(msg, style=style)
    else:
        print(msg)


def print_ok(msg: str) -> None:
    print_msg(f"[green]✔[/green] {msg}" if HAS_RICH else f"✔ {msg}")


def print_err(msg: str) -> None:
    print_msg(f"[bold red]ERROR:[/bold red] {msg}" if HAS_RICH else f"ERROR: {msg}")


def print_info(msg: str) -> None:
    print_msg(f"[cyan]ℹ[/cyan] {msg}" if HAS_RICH else f"ℹ {msg}")


def bail(msg: str) -> None:
    """Print an error and exit with code 1."""
    print_err(msg)
    sys.exit(1)