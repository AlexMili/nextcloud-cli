"""File operations against the user's Nextcloud WebDAV root."""

from __future__ import annotations

from pathlib import Path

import click
from webdav4.client import ResourceAlreadyExists, ResourceNotFound

from nextcloud_cli.client import webdav_client
from nextcloud_cli.config import load
from nextcloud_cli.rendering import render_files_list, render_status
from nextcloud_cli.utils import (
    CONTEXT_SETTINGS,
    fail,
    format_size,
    json_option,
    spinner,
    verbose_option,
)


@click.group(context_settings=CONTEXT_SETTINGS)
def files() -> None:
    """Manage files via WebDAV."""


@verbose_option
@json_option
@files.command("list")
@click.option("--path", default="/", help="Remote directory path.")
def list_(path: str, json_output: bool) -> None:
    """List files in a remote directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        with spinner(f"Listing {path}", json_output):
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
    render_files_list(items, path, json_output)


@verbose_option
@json_option
@files.command()
@click.option("--local", "local", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--remote", required=True, help="Destination path on the server.")
def upload(local: str, remote: str, json_output: bool) -> None:
    """Upload a local file to the server."""
    cfg = load()
    client = webdav_client(cfg)
    with spinner(f"Uploading {local} → {remote}", json_output):
        client.upload_file(from_path=local, to_path=remote, overwrite=True)
    render_status("uploaded", json_output, local=local, remote=remote)


@verbose_option
@json_option
@files.command()
@click.option("--remote", required=True, help="Source path on the server.")
@click.option("--local", "local", required=True, type=click.Path(dir_okay=False))
def download(remote: str, local: str, json_output: bool) -> None:
    """Download a remote file to the local filesystem."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        with spinner(f"Downloading {remote} → {local}", json_output):
            client.download_file(from_path=remote, to_path=local)
    except ResourceNotFound:
        fail(f"remote file not found: {remote}")
    render_status("downloaded", json_output, remote=remote, local=local)


@verbose_option
@json_option
@files.command()
@click.option("--path", required=True, help="Path to delete.")
def delete(path: str, json_output: bool) -> None:
    """Delete a remote file or directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        with spinner(f"Deleting {path}", json_output):
            client.remove(path)
    except ResourceNotFound:
        fail(f"path not found: {path}")
    render_status("deleted", json_output, path=path)


@verbose_option
@json_option
@files.command()
@click.option("--src", required=True, help="Current remote path.")
@click.option("--dst", required=True, help="New remote path.")
def move(src: str, dst: str, json_output: bool) -> None:
    """Move or rename a file."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        with spinner(f"Moving {src} → {dst}", json_output):
            client.move(src, dst)
    except ResourceNotFound:
        fail(f"source not found: {src}")
    render_status("moved", json_output, src=src, dst=dst)


@verbose_option
@json_option
@files.command()
@click.option("--path", required=True, help="Directory to create.")
def mkdir(path: str, json_output: bool) -> None:
    """Create a remote directory."""
    cfg = load()
    client = webdav_client(cfg)
    try:
        with spinner(f"Creating {path}", json_output):
            client.mkdir(path)
    except ResourceAlreadyExists:
        fail(f"already exists: {path}")
    render_status("created", json_output, path=path)


@verbose_option
@json_option
@files.command()
@click.option("--query", required=True, help="Substring to search for in filenames.")
@click.option("--path", default="/", help="Root path to search under.")
def search(query: str, path: str, json_output: bool) -> None:
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
                            "name": base,
                            "path": name,
                            "type": entry["type"],
                            "size": entry.get("content_length") or 0,
                            "size_human": format_size(entry.get("content_length") or 0),
                            "modified": str(entry.get("modified")) if entry.get("modified") else None,
                        }
                    )
                if entry["type"] == "directory" and name.rstrip("/") != current.rstrip("/"):
                    walk(name)
        except ResourceNotFound:
            pass

    with spinner(f"Searching for '{query}' under {path}", json_output):
        walk(path)
    render_files_list(matches, f"matches for '{query}' under {path}", json_output)
