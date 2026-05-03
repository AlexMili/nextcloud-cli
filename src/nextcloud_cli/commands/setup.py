"""Login / logout commands."""

from __future__ import annotations

import os

import click
import httpx

from nextcloud_cli import config as cfg_module
from nextcloud_cli.rendering import render_status
from nextcloud_cli.utils import CONTEXT_SETTINGS, json_option, spinner, verbose_option


def _resolve(flag_value: str | None, env_var: str, prompt: str, *, hidden: bool = False, default: str | None = None) -> str:
    """flag value > env var > interactive prompt."""
    if flag_value:
        return flag_value
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value
    return click.prompt(prompt, hide_input=hidden, default=default, type=str)


@click.command(context_settings=CONTEXT_SETTINGS)
@verbose_option
@json_option
@click.option("--url", default=None, help="Nextcloud server URL.")
@click.option("--username", default=None, help="Nextcloud username.")
@click.option("--password", default=None, help="App password (NOT your account password).")
@click.option("--timezone", default=None, help="IANA timezone (e.g. Europe/Paris).")
def login(url: str | None, username: str | None, password: str | None, timezone: str | None, json_output: bool) -> None:
    """Log in to a Nextcloud server."""
    url = _resolve(url, "NEXTCLOUD_URL", "Nextcloud URL").rstrip("/")
    username = _resolve(username, "NEXTCLOUD_USER", "Username")
    password = _resolve(password, "NEXTCLOUD_TOKEN", "App password", hidden=True)
    timezone = _resolve(timezone, "NEXTCLOUD_TIMEZONE", "Timezone", default="UTC")

    test_url = f"{url}/remote.php/dav/files/{username}/"
    try:
        with spinner(f"Authenticating to {url}", json_output):
            response = httpx.request(
                "PROPFIND",
                test_url,
                auth=(username, password),
                headers={"Depth": "0"},
                timeout=15.0,
            )
    except httpx.HTTPError as exc:
        raise click.ClickException(f"could not reach server: {exc}") from exc
    if response.status_code in (401, 403):
        raise click.ClickException("authentication failed — check your username and app password")
    if response.status_code >= 400:
        raise click.ClickException(f"server returned HTTP {response.status_code}")

    cfg_module.save(url=url, username=username, password=password, timezone=timezone)
    render_status("logged-in", json_output, url=url, username=username, timezone=timezone)


@click.command(context_settings=CONTEXT_SETTINGS)
@verbose_option
@json_option
def logout(json_output: bool) -> None:
    """Erase stored credentials."""
    cfg_module.clear()
    render_status("logged-out", json_output)
