"""Nextcloud Notes app — REST/JSON API."""

from __future__ import annotations

import click
import httpx

from nextcloud_cli.client import http_client
from nextcloud_cli.config import load
from nextcloud_cli.rendering import render_note, render_notes_list, render_status
from nextcloud_cli.utils import CONTEXT_SETTINGS, fail, json_option, spinner, verbose_option


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
@json_option
@notes.command("list")
@click.option("--category", default=None, help="Filter by category.")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Max number of notes to fetch.")
def list_(category: str | None, limit: int | None, json_output: bool) -> None:
    """List all notes."""
    cfg = load()
    params: dict[str, str | int] = {}
    if category is not None:
        params["category"] = category
    if limit is not None:
        params["chunkSize"] = limit
    with spinner("Fetching notes", json_output):
        with http_client(cfg) as http:
            data = _handle(http.get(cfg.notes_api_url, params=params or None))
    notes_list = data if isinstance(data, list) else [data]
    if limit is not None:
        notes_list = notes_list[:limit]
    render_notes_list(notes_list, json_output)


@verbose_option
@json_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
def get(note_id: int, json_output: bool) -> None:
    """Fetch a single note by ID."""
    cfg = load()
    with spinner(f"Fetching note {note_id}", json_output):
        with http_client(cfg) as http:
            data = _handle(http.get(f"{cfg.notes_api_url}/{note_id}"))
    render_note(data if isinstance(data, dict) else {}, json_output)


@verbose_option
@json_option
@notes.command()
@click.option("--title", required=True)
@click.option("--content", default="", help="Body of the note.")
@click.option("--category", default="", help="Category folder.")
def create(title: str, content: str, category: str, json_output: bool) -> None:
    """Create a new note."""
    cfg = load()
    payload = {"title": title, "content": content, "category": category}
    with spinner(f"Creating note '{title}'", json_output):
        with http_client(cfg) as http:
            data = _handle(http.post(cfg.notes_api_url, json=payload))
    if json_output:
        from nextcloud_cli.utils import emit

        emit(data)
    else:
        render_status("note created", json_output, id=data.get("id"), title=data.get("title"))


@verbose_option
@json_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
@click.option("--title", default=None)
@click.option("--content", default=None)
@click.option("--category", default=None)
def edit(note_id: int, title: str | None, content: str | None, category: str | None, json_output: bool) -> None:
    """Update an existing note. Only provided fields change."""
    cfg = load()
    payload = {k: v for k, v in {"title": title, "content": content, "category": category}.items() if v is not None}
    if not payload:
        fail("nothing to update — provide at least one of --title/--content/--category")
    with spinner(f"Updating note {note_id}", json_output):
        with http_client(cfg) as http:
            data = _handle(http.put(f"{cfg.notes_api_url}/{note_id}", json=payload))
    if json_output:
        from nextcloud_cli.utils import emit

        emit(data)
    else:
        render_status("note updated", json_output, id=note_id)


@verbose_option
@json_option
@notes.command()
@click.option("--id", "note_id", required=True, type=int)
def delete(note_id: int, json_output: bool) -> None:
    """Delete a note."""
    cfg = load()
    with spinner(f"Deleting note {note_id}", json_output):
        with http_client(cfg) as http:
            _handle(http.delete(f"{cfg.notes_api_url}/{note_id}"))
    render_status("deleted", json_output, id=note_id)
