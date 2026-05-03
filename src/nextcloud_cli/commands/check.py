"""Connectivity self-check."""

from __future__ import annotations

import time

import click
import httpx

from nextcloud_cli.client import http_client
from nextcloud_cli.config import load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, verbose_option


@click.command(context_settings=CONTEXT_SETTINGS)
@verbose_option
@click.option("--timeout", default=10.0, type=float, help="Per-endpoint timeout (seconds).")
def check(timeout: float) -> None:
    """Verify configuration and reachability of each Nextcloud endpoint."""
    cfg = load()
    results = {
        "url": cfg.url,
        "username": cfg.username,
        "timezone": cfg.timezone,
        "timeout": timeout,
        "endpoints": {},
    }

    # For Notes, exclude every field so the server returns just `[{id}, ...]`
    # instead of serializing every note's content. Keeps the probe meaningful
    # (the app still iterates notes) without paying the full payload cost.
    notes_probe_url = f"{cfg.notes_api_url}?exclude=title,content,category,modified,favorite,etag"

    probes = [
        ("webdav", f"{cfg.webdav_files_url}/", "PROPFIND"),
        ("notes", notes_probe_url, "GET"),
        ("caldav", f"{cfg.caldav_url}/principals/users/{cfg.username}/", "PROPFIND"),
        ("carddav", cfg.carddav_principal, "PROPFIND"),
    ]

    with http_client(cfg) as http:
        for label, url, method in probes:
            started = time.monotonic()
            try:
                response = http.request(
                    method,
                    url,
                    headers={"Depth": "0"} if method == "PROPFIND" else {},
                    timeout=timeout,
                )
                results["endpoints"][label] = {
                    "url": url,
                    "method": method,
                    "status": response.status_code,
                    "ok": response.status_code < 400,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                }
            except httpx.HTTPError as exc:
                results["endpoints"][label] = {
                    "url": url,
                    "method": method,
                    "status": None,
                    "ok": False,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

    emit(results)
