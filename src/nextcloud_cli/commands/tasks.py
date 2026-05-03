"""Tasks (VTODO) operations on a CalDAV task list."""

from __future__ import annotations

import uuid
from datetime import datetime

import click
from icalendar import Calendar as ICal
from icalendar import Todo

from nextcloud_cli.client import caldav_principal
from nextcloud_cli.config import load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, fail, parse_datetime, verbose_option


@click.group(context_settings=CONTEXT_SETTINGS)
def tasks() -> None:
    """Manage tasks (VTODO) via CalDAV."""


def _find_task_list(principal, name: str | None):
    candidates = []
    for cal in principal.calendars():
        comps = []
        try:
            comps = list(cal.components or [])
        except Exception:
            pass
        if "VTODO" in comps or name and cal.name == name:
            candidates.append(cal)
    if name:
        for cal in candidates:
            if cal.name == name:
                return cal
        fail(f"task list not found: {name}")
    if not candidates:
        fail("no task lists found on the server")
    return candidates[0]


@verbose_option
@tasks.command("list")
@click.option("--list", "list_name", default=None, help="Specific task list name.")
@click.option("--include-completed", is_flag=True)
def list_(list_name: str | None, include_completed: bool) -> None:
    """List tasks."""
    cfg = load()
    out = []
    with caldav_principal(cfg) as principal:
        cal = _find_task_list(principal, list_name)
        for todo in cal.todos(include_completed=include_completed):
            ical = ICal.from_ical(todo.data)
            for component in ical.walk("VTODO"):
                out.append(
                    {
                        "uid": str(component.get("UID")),
                        "summary": str(component.get("SUMMARY", "")),
                        "due": component.decoded("DUE").isoformat() if component.get("DUE") else None,
                        "status": str(component.get("STATUS", "")),
                        "priority": int(component.get("PRIORITY", 0)) or None,
                        "list": cal.name,
                    }
                )
    emit(out)


@verbose_option
@tasks.command()
@click.option("--list", "list_name", default=None)
@click.option("--summary", required=True)
@click.option("--due", default=None, help="ISO 8601 due date.")
@click.option("--priority", default=None, type=int, help="0 (none) - 9 (lowest); 1 highest.")
@click.option("--description", default="")
def create(
    list_name: str | None,
    summary: str,
    due: str | None,
    priority: int | None,
    description: str,
) -> None:
    """Create a new task."""
    cfg = load()
    ical = ICal()
    ical.add("prodid", "-//nextcloud-cli//EN")
    ical.add("version", "2.0")
    todo = Todo()
    uid = str(uuid.uuid4())
    todo.add("uid", uid)
    todo.add("summary", summary)
    todo.add("status", "NEEDS-ACTION")
    if due:
        todo.add("due", parse_datetime(due, cfg.timezone))
    if priority is not None:
        todo.add("priority", priority)
    if description:
        todo.add("description", description)
    ical.add_component(todo)

    with caldav_principal(cfg) as principal:
        cal = _find_task_list(principal, list_name)
        cal.save_todo(ical.to_ical().decode())
    emit({"status": "created", "uid": uid})


@verbose_option
@tasks.command()
@click.option("--list", "list_name", default=None)
@click.option("--uid", required=True)
def complete(list_name: str | None, uid: str) -> None:
    """Mark a task as completed."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cal = _find_task_list(principal, list_name)
        try:
            todo = cal.todo_by_uid(uid)
        except Exception:
            fail(f"task not found: {uid}")
        ical = ICal.from_ical(todo.data)
        for component in ical.walk("VTODO"):
            component["STATUS"] = "COMPLETED"
            component["COMPLETED"] = datetime.utcnow()
            component["PERCENT-COMPLETE"] = 100
        todo.data = ical.to_ical().decode()
        todo.save()
    emit({"status": "completed", "uid": uid})


@verbose_option
@tasks.command()
@click.option("--list", "list_name", default=None)
@click.option("--uid", required=True)
@click.option("--summary", default=None)
@click.option("--due", default=None)
@click.option("--priority", default=None, type=int)
@click.option("--description", default=None)
def edit(
    list_name: str | None,
    uid: str,
    summary: str | None,
    due: str | None,
    priority: int | None,
    description: str | None,
) -> None:
    """Update fields of an existing task."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cal = _find_task_list(principal, list_name)
        try:
            todo = cal.todo_by_uid(uid)
        except Exception:
            fail(f"task not found: {uid}")
        ical = ICal.from_ical(todo.data)
        for component in ical.walk("VTODO"):
            if summary is not None:
                component["SUMMARY"] = summary
            if due is not None:
                if "DUE" in component:
                    component["DUE"].dt = parse_datetime(due, cfg.timezone)
                else:
                    component.add("due", parse_datetime(due, cfg.timezone))
            if priority is not None:
                component["PRIORITY"] = priority
            if description is not None:
                component["DESCRIPTION"] = description
        todo.data = ical.to_ical().decode()
        todo.save()
    emit({"status": "updated", "uid": uid})


@verbose_option
@tasks.command()
@click.option("--list", "list_name", default=None)
@click.option("--uid", required=True)
def delete(list_name: str | None, uid: str) -> None:
    """Delete a task."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cal = _find_task_list(principal, list_name)
        try:
            todo = cal.todo_by_uid(uid)
        except Exception:
            fail(f"task not found: {uid}")
        todo.delete()
    emit({"status": "deleted", "uid": uid})
