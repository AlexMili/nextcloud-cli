"""Credential and configuration storage.

Credentials (app password) are stored in the OS keyring when available, with a
chmod 0600 JSON file fallback for systems without a keyring backend.

Non-secret config (URL, username, timezone) lives in
``~/.config/nextcloud-cli/config.json``.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import click
import keyring
from keyring.errors import KeyringError

KEYRING_SERVICE = "nextcloud-cli"
CONFIG_DIR = Path(os.environ.get("NEXTCLOUD_CLI_HOME", Path.home() / ".config" / "nextcloud-cli"))
CONFIG_FILE = CONFIG_DIR / "config.json"
SECRETS_FALLBACK_FILE = CONFIG_DIR / "secrets.json"


@dataclass
class Config:
    url: str
    username: str
    password: str
    timezone: str = "UTC"

    @property
    def webdav_files_url(self) -> str:
        return f"{self.url.rstrip('/')}/remote.php/dav/files/{self.username}"

    @property
    def caldav_url(self) -> str:
        return f"{self.url.rstrip('/')}/remote.php/dav"

    @property
    def carddav_principal(self) -> str:
        return f"{self.url.rstrip('/')}/remote.php/dav/addressbooks/users/{self.username}/"

    @property
    def notes_api_url(self) -> str:
        return f"{self.url.rstrip('/')}/index.php/apps/notes/api/v1/notes"


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, stat.S_IRWXU)
    except OSError:
        pass


def _write_secure(path: Path, data: dict) -> None:
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save(url: str, username: str, password: str, timezone: str = "UTC") -> None:
    """Persist credentials and configuration."""
    _ensure_dir()
    _write_secure(CONFIG_FILE, {"url": url, "username": username, "timezone": timezone})

    account = f"{username}@{url}"
    try:
        keyring.set_password(KEYRING_SERVICE, account, password)
        if SECRETS_FALLBACK_FILE.exists():
            SECRETS_FALLBACK_FILE.unlink()
    except KeyringError:
        _write_secure(SECRETS_FALLBACK_FILE, {account: password})


def _load_password(username: str, url: str) -> str | None:
    account = f"{username}@{url}"
    try:
        pwd = keyring.get_password(KEYRING_SERVICE, account)
        if pwd:
            return pwd
    except KeyringError:
        pass
    fallback = _read_json(SECRETS_FALLBACK_FILE)
    return fallback.get(account)


def load() -> Config:
    """Load full configuration. Falls back to environment variables when
    no on-disk config is present, matching the original hermes-nextcloud
    contract (``NEXTCLOUD_URL`` / ``NEXTCLOUD_USER`` / ``NEXTCLOUD_TOKEN``).
    """
    cfg = _read_json(CONFIG_FILE)
    url = cfg.get("url") or os.environ.get("NEXTCLOUD_URL")
    username = cfg.get("username") or os.environ.get("NEXTCLOUD_USER")
    timezone = cfg.get("timezone") or os.environ.get("NEXTCLOUD_TIMEZONE", "UTC")

    if not url or not username:
        raise ConfigError(
            "not logged in — run `nxcloud login` "
            "or set NEXTCLOUD_URL / NEXTCLOUD_USER / NEXTCLOUD_TOKEN"
        )

    password = os.environ.get("NEXTCLOUD_TOKEN") or _load_password(username, url)
    if not password:
        raise ConfigError(
            "no app password available — re-run `nxcloud login` or set NEXTCLOUD_TOKEN"
        )

    return Config(url=url, username=username, password=password, timezone=timezone)


def clear() -> None:
    """Remove stored credentials and configuration."""
    cfg = _read_json(CONFIG_FILE)
    username = cfg.get("username")
    url = cfg.get("url")
    if username and url:
        try:
            keyring.delete_password(KEYRING_SERVICE, f"{username}@{url}")
        except KeyringError:
            pass
    for path in (CONFIG_FILE, SECRETS_FALLBACK_FILE):
        if path.exists():
            path.unlink()


class ConfigError(click.ClickException):
    """Raised when configuration is missing or invalid.

    Inheriting from :class:`click.ClickException` lets the CLI print a clean
    one-line error and exit with status 1 instead of a Python traceback.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
