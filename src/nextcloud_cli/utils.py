"""Small helpers shared across command modules."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from typing import Any, Iterator

import click
from dateutil import parser as date_parser
from rich.console import Console
from rich.logging import RichHandler

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

console = Console()
err_console = Console(stderr=True)


def configure_logging(verbosity: int) -> None:
    """Configure stderr logging based on a -v / -vv counter.

    - 0: WARNING (default — silent on success)
    - 1: INFO    (one line per HTTP request)
    - 2+: DEBUG  (full request/response headers via httpx)
    """
    if verbosity <= 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    handler: logging.Handler
    if err_console.is_terminal:
        handler = RichHandler(
            console=err_console,
            show_path=False,
            markup=False,
            rich_tracebacks=True,
            log_time_format="[%X]",
        )
        fmt = "%(name)s: %(message)s"
    else:
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    if verbosity < 2:
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def _verbose_callback(ctx: click.Context, param: click.Parameter, value: int) -> int:
    if value:
        configure_logging(value)
    return value


verbose_option = click.option(
    "-v",
    "--verbose",
    count=True,
    expose_value=False,
    is_eager=True,
    callback=_verbose_callback,
    help="Increase log verbosity (-v: HTTP requests, -vv: full headers).",
)

json_option = click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit raw JSON to stdout (machine-readable, no spinner, no colors).",
)


def parse_datetime(value: str, default_tz: str = "UTC") -> datetime:
    """Parse an ISO 8601 string into an aware datetime."""
    dt = date_parser.isoparse(value)
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo

            dt = dt.replace(tzinfo=ZoneInfo(default_tz))
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


@contextmanager
def spinner(message: str, json_output: bool = False) -> Iterator[None]:
    """Show a Rich spinner on stderr while a block runs.

    Suppressed in --json mode and when stderr is not a TTY (CI logs stay clean).
    """
    if json_output or not err_console.is_terminal:
        with nullcontext():
            yield
        return
    with err_console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
        yield


def emit(payload: Any) -> None:
    """Print JSON to stdout. Used in --json mode and as a fallback."""
    json.dump(payload, sys.stdout, indent=2, default=str, ensure_ascii=False)
    sys.stdout.write("\n")


def fail(message: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    if err_console.is_terminal:
        err_console.print(f"[bold red]error:[/bold red] {message}")
    else:
        sys.stderr.write(f"error: {message}\n")
    sys.exit(code)
