"""File operations against the user's Nextcloud WebDAV root."""

from __future__ import annotations

from pathlib import Path

import click
from webdav4.client import ResourceAlreadyExists, ResourceNotFound

from nextcloud_cli.client import http_client, webdav_client
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
@click.option("--query", required=True, help="Substring to match (server-side, OCS unified search).")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Max number of matches.")
def search(query: str, limit: int | None, json_output: bool) -> None:
    """Server-side filename search via the OCS unified search API."""
    cfg = load()
    url = f"{cfg.url.rstrip('/')}/ocs/v2.php/search/providers/files/search"
    params: dict[str, str | int] = {"term": query}
    if limit is not None:
        params["limit"] = limit
    with spinner(f"Searching for '{query}'", json_output):
        with http_client(cfg) as http:
            response = http.get(url, params=params)
    if response.status_code >= 400:
        fail(f"search failed: {response.status_code}: {response.text}")
    payload = response.json().get("ocs", {}).get("data", {})
    entries = payload.get("entries", []) or []
    matches = [
        {
            "name": entry.get("title"),
            "path": entry.get("attributes", {}).get("path") or entry.get("subline") or "",
            "resourceUrl": entry.get("resourceUrl"),
            "fileId": entry.get("attributes", {}).get("fileId"),
            "icon": entry.get("icon"),
        }
        for entry in entries
    ]
    if limit is not None:
        matches = matches[:limit]
    render_files_list(matches, f"matches for '{query}'", json_output)
