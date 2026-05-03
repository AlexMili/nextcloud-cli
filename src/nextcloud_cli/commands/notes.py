"""Nextcloud Notes app — REST/JSON API."""

from __future__ import annotations

import click
import httpx

from nextcloud_cli.client import http_client
from nextcloud_cli.config import load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, fail, verbose_option


@click.group(context_settings=CONTEXT_SETTINGS)
def notes() -> None:
    """Manage notes (requires the Nextcloud Notes app)."""


def _handle(response: httpx.Response) -> dict | list:
    if response.status_code == 404:
        fail("note not found")
    if response.status_code == 401:
        fail("unauthorized — check your app password")
    if response.status_code >= 400:
        fail(f"notes API error {response.status_code}: {response.text}")
    return response.json() if response.content else {}


@verbose_option
@notes.command("list")
@click.option("--category", default=None, help="Filter by category.")
def list_(category: str | None) -> None:
    """List all notes."""
    cfg = load()
    with http_client(cfg) as http:
        params = {"category": category} if category else None
        data = _handle(http.get(cfg.notes_api_url, params=params))
    emit(data)


@verbose_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
def get(note_id: int) -> None:
    """Fetch a single note by ID."""
    cfg = load()
    with http_client(cfg) as http:
        data = _handle(http.get(f"{cfg.notes_api_url}/{note_id}"))
    emit(data)


@verbose_option
@notes.command()
@click.option("--title", required=True)
@click.option("--content", default="", help="Body of the note.")
@click.option("--category", default="", help="Category folder.")
def create(title: str, content: str, category: str) -> None:
    """Create a new note."""
    cfg = load()
    payload = {"title": title, "content": content, "category": category}
    with http_client(cfg) as http:
        data = _handle(http.post(cfg.notes_api_url, json=payload))
    emit(data)


@verbose_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
@click.option("--title", default=None)
@click.option("--content", default=None)
@click.option("--category", default=None)
def edit(note_id: int, title: str | None, content: str | None, category: str | None) -> None:
    """Update an existing note. Only provided fields change."""
    cfg = load()
    payload = {k: v for k, v in {"title": title, "content": content, "category": category}.items() if v is not None}
    if not payload:
        fail("nothing to update — provide at least one of --title/--content/--category")
    with http_client(cfg) as http:
        data = _handle(http.put(f"{cfg.notes_api_url}/{note_id}", json=payload))
    emit(data)


@verbose_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
def delete(note_id: int) -> None:
    """Delete a note."""
    cfg = load()
    with http_client(cfg) as http:
        _handle(http.delete(f"{cfg.notes_api_url}/{note_id}"))
    emit({"status": "deleted", "id": note_id})
