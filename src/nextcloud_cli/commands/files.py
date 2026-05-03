"""File operations against the user's Nextcloud WebDAV root."""

from __future__ import annotations

from pathlib import Path

import click
from webdav4.client import ResourceAlreadyExists, ResourceNotFound

from nextcloud_cli.client import webdav_client
from nextcloud_cli.config import load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, fail, format_size, verbose_option


@click.group(context_settings=CONTEXT_SETTINGS)
def files() -> None:
    """Manage files via WebDAV."""


@verbose_option
@files.command("list")
@click.option("--path", default="/", help="Remote directory path.")
def list_(path: str) -> None:
    """List files in a remote directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        entries = client.ls(path, detail=True)
    except ResourceNotFound:
        fail(f"path not found: {path}")
    items = [
        {
            "name": Path(entry["name"]).name or entry["name"],
            "path": entry["name"],
            "type": entry["type"],
            "size": entry.get("content_length") or 0,
            "size_human": format_size(entry.get("content_length") or 0),
            "modified": str(entry.get("modified")) if entry.get("modified") else None,
        }
        for entry in entries
    ]
    emit(items)


@verbose_option
@files.command()
@click.option("--local", "local", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--remote", required=True, help="Destination path on the server.")
def upload(local: str, remote: str) -> None:
    """Upload a local file to the server."""
    cfg = load()
    client = webdav_client(cfg)
    client.upload_file(from_path=local, to_path=remote, overwrite=True)
    emit({"status": "uploaded", "local": local, "remote": remote})


@verbose_option
@files.command()
@click.option("--remote", required=True, help="Source path on the server.")
@click.option("--local", "local", required=True, type=click.Path(dir_okay=False))
def download(remote: str, local: str) -> None:
    """Download a remote file to the local filesystem."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        client.download_file(from_path=remote, to_path=local)
    except ResourceNotFound:
        fail(f"remote file not found: {remote}")
    emit({"status": "downloaded", "remote": remote, "local": local})


@verbose_option
@files.command()
@click.option("--path", required=True, help="Path to delete.")
def delete(path: str) -> None:
    """Delete a remote file or directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        client.remove(path)
    except ResourceNotFound:
        fail(f"path not found: {path}")
    emit({"status": "deleted", "path": path})


@verbose_option
@files.command()
@click.option("--src", required=True, help="Current remote path.")
@click.option("--dst", required=True, help="New remote path.")
def move(src: str, dst: str) -> None:
    """Move or rename a file."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        client.move(src, dst)
    except ResourceNotFound:
        fail(f"source not found: {src}")
    emit({"status": "moved", "src": src, "dst": dst})


@verbose_option
@files.command()
@click.option("--path", required=True, help="Directory to create.")
def mkdir(path: str) -> None:
    """Create a remote directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        client.mkdir(path)
    except ResourceAlreadyExists:
        fail(f"already exists: {path}")
    emit({"status": "created", "path": path})


@verbose_option
@files.command()
@click.option("--query", required=True, help="Substring to search for in filenames.")
@click.option("--path", default="/", help="Root path to search under.")
def search(query: str, path: str) -> None:
    """Recursive substring search by filename."""
    cfg = load()
    client = webdav_client(cfg)
    matches: list[dict] = []
    needle = query.lower()

    def walk(current: str) -> None:
        try:
            for entry in client.ls(current, detail=True):
                name = entry["name"]
                base = Path(name).name or name
                if needle in base.lower():
                    matches.append(
                        {
                            "path": name,
                            "type": entry["type"],
                            "size": entry.get("content_length") or 0,
                        }
                    )
                if entry["type"] == "directory" and name.rstrip("/") != current.rstrip("/"):
                    walk(name)
        except ResourceNotFound:
            pass

    walk(path)
    emit(matches)
