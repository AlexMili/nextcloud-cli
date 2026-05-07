"""Factory for the various protocol clients used by the CLI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import caldav
import httpx
from webdav4.client import Client as WebDAVClient

from nextcloud_cli.config import Config

DEFAULT_TIMEOUT = 30.0


def http_client(cfg: Config, *, accept: str = "application/json") -> httpx.Client:
    """HTTP client preconfigured with Basic auth and sensible defaults."""
    return httpx.Client(
        auth=(cfg.username, cfg.password),
        headers={"Accept": accept, "OCS-APIRequest": "true"},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


def webdav_client(cfg: Config) -> WebDAVClient:
    """WebDAV client scoped to the user's files endpoint."""
    return WebDAVClient(
        cfg.webdav_files_url,
        auth=(cfg.username, cfg.password),
        timeout=DEFAULT_TIMEOUT,
    )


@contextmanager
def caldav_principal(cfg: Config) -> Iterator[caldav.Principal]:
    """Context manager yielding the user's CalDAV principal."""
    with caldav.DAVClient(
        url=cfg.caldav_url,
        username=cfg.username,
        password=cfg.password,
    ) as client:
        yield client.principal()
