"""Calendar (CalDAV) operations."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import click
from icalendar import Calendar as ICal
from icalendar import Event as IEvent
from icalendar import vCalAddress, vText

from nextcloud_cli.client import caldav_principal
from nextcloud_cli.config import load
from nextcloud_cli.rendering import render_calendars, render_events, render_status
from nextcloud_cli.utils import (
    CONTEXT_SETTINGS,
    fail,
    json_option,
    parse_datetime,
    spinner,
    verbose_option,
)


@click.group(context_settings=CONTEXT_SETTINGS)
def calendar() -> None:
    """Manage calendars and events via CalDAV."""


def _find_calendar(principal, name: str):
    for cal in principal.calendars():
        if cal.name == name:
            return cal
    fail(f"calendar not found: {name}")


def _attendee_property(spec: str) -> vCalAddress:
    """Build an ATTENDEE property from a ``Name <email>`` or ``email`` string."""
    name = None
    email = spec.strip()
    if "<" in spec and ">" in spec:
        name = spec.split("<", 1)[0].strip().strip('"')
        email = spec.split("<", 1)[1].split(">", 1)[0].strip()

    addr = vCalAddress(f"mailto:{email}")
    if name:
        addr.params["CN"] = vText(name)
    addr.params["ROLE"] = vText("REQ-PARTICIPANT")
    addr.params["PARTSTAT"] = vText("NEEDS-ACTION")
    addr.params["RSVP"] = vText("TRUE")
    return addr


@verbose_option
@json_option
@calendar.command("list")
def list_calendars(json_output: bool) -> None:
    """List all calendars."""
    cfg = load()
    with spinner("Fetching calendars", json_output):
        with caldav_principal(cfg) as principal:
            cals = [
                {
                    "name": cal.name,
                    "url": str(cal.url),
                }
                for cal in principal.calendars()
            ]
    render_calendars(cals, json_output)


def _shortcut_range(
    today: bool,
    this_week: bool,
    next_week: bool,
    this_month: bool,
    next_month: bool,
    nxt: str | None,
    tz: str,
) -> tuple[datetime, datetime] | None:
    """Resolve a date-range shortcut to (start, end) in the configured timezone.

    Returns None if no shortcut was selected. Raises via ``fail`` on conflicts
    or malformed values.
    """
    chosen = [
        name
        for name, on in (
            ("--today", today),
            ("--this-week", this_week),
            ("--next-week", next_week),
            ("--this-month", this_month),
            ("--next-month", next_month),
            ("--next", bool(nxt)),
        )
        if on
    ]
    if len(chosen) > 1:
        fail(f"shortcuts are mutually exclusive: {', '.join(chosen)}")
    if not chosen:
        return None

    try:
        zone = ZoneInfo(tz)
    except Exception:
        zone = ZoneInfo("UTC")
    now = datetime.now(zone)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _first_of_next_month(d: datetime) -> datetime:
        return (d.replace(day=28) + timedelta(days=4)).replace(day=1)

    if today:
        return midnight, midnight + timedelta(days=1)
    if this_week:
        monday = midnight - timedelta(days=midnight.weekday())
        return monday, monday + timedelta(days=7)
    if next_week:
        next_monday = midnight - timedelta(days=midnight.weekday()) + timedelta(days=7)
        return next_monday, next_monday + timedelta(days=7)
    if this_month:
        first = midnight.replace(day=1)
        return first, _first_of_next_month(first)
    if next_month:
        first_next = _first_of_next_month(midnight.replace(day=1))
        return first_next, _first_of_next_month(first_next)
    # --next Xd / Xh / Xw
    match = re.fullmatch(r"\s*(\d+)\s*([dhw])\s*", nxt or "", re.IGNORECASE)
    if not match:
        fail("--next expects a value like '7d', '48h' or '2w'")
    n, unit = int(match.group(1)), match.group(2).lower()
    delta = {"d": timedelta(days=n), "h": timedelta(hours=n), "w": timedelta(weeks=n)}[unit]
    return now, now + delta


@verbose_option
@json_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--start", default=None, help="ISO 8601 start of range.")
@click.option("--end", default=None, help="ISO 8601 end of range.")
@click.option("--today", is_flag=True, help="Events from today (00:00 → 24:00, local TZ).")
@click.option("--this-week", is_flag=True, help="Events from this week (Monday → Monday).")
@click.option("--next-week", is_flag=True, help="Events from next week (upcoming Monday → Monday after).")
@click.option("--this-month", is_flag=True, help="Events from the current calendar month.")
@click.option("--next-month", is_flag=True, help="Events from the next calendar month.")
@click.option("--next", "next_", default=None, metavar="Xd|Xh|Xw", help="Events from now to now + duration (e.g. 7d, 48h, 2w).")
def events(
    calendar_name: str,
    start: str | None,
    end: str | None,
    today: bool,
    this_week: bool,
    next_week: bool,
    this_month: bool,
    next_month: bool,
    next_: str | None,
    json_output: bool,
) -> None:
    """List events in a calendar, optionally within a date range."""
    cfg = load()
    shortcut = _shortcut_range(today, this_week, next_week, this_month, next_month, next_, cfg.timezone)
    if shortcut and (start or end):
        fail("--start/--end cannot be combined with shortcut flags (--today, --this-week, --next-week, --this-month, --next-month, --next)")

    out: list[dict] = []
    with spinner(f"Fetching events from {calendar_name}", json_output):
        with caldav_principal(cfg) as principal:
            cal = _find_calendar(principal, calendar_name)
            if shortcut:
                start_dt, end_dt = shortcut
                results = cal.search(start=start_dt, end=end_dt, event=True, expand=True)
            elif start or end:
                start_dt = parse_datetime(start, cfg.timezone) if start else None
                end_dt = parse_datetime(end, cfg.timezone) if end else None
                results = cal.search(start=start_dt, end=end_dt, event=True, expand=True)
            else:
                results = cal.events()

            for event in results:
                ical = ICal.from_ical(event.data)
                for component in ical.walk("VEVENT"):
                    out.append(_vevent_to_dict(component))
    render_events(out, json_output)


def _vevent_to_dict(component) -> dict:
    attendees = []
    raw = component.get("ATTENDEE")
    raw_list = raw if isinstance(raw, list) else [raw] if raw else []
    for prop in raw_list:
        if prop is None:
            continue
        email = str(prop).replace("mailto:", "", 1)
        attendees.append(
            {
                "email": email,
                "cn": str(prop.params.get("CN", "")),
                "partstat": str(prop.params.get("PARTSTAT", "")),
            }
        )
    return {
        "uid": str(component.get("UID")),
        "summary": str(component.get("SUMMARY", "")),
        "start": component.decoded("DTSTART").isoformat() if component.get("DTSTART") else None,
        "end": component.decoded("DTEND").isoformat() if component.get("DTEND") else None,
        "location": str(component.get("LOCATION", "")),
        "description": str(component.get("DESCRIPTION", "")),
        "organizer": str(component.get("ORGANIZER", "")).replace("mailto:", "", 1) or None,
        "attendees": attendees,
    }


_EVENT_SEARCH_FIELDS = {
    "summary": ("summary",),
    "description": ("description",),
    "location": ("location",),
    "category": ("category",),
    "all": ("summary", "description", "location"),
}


@verbose_option
@json_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--query", required=True, help="Substring to match (case-insensitive, server-side).")
@click.option(
    "--in",
    "field",
    type=click.Choice(list(_EVENT_SEARCH_FIELDS.keys())),
    default="summary",
    help="Which iCalendar property to search (default: summary).",
)
@click.option("--start", default=None, help="ISO 8601 start of range.")
@click.option("--end", default=None, help="ISO 8601 end of range.")
@click.option("--today", is_flag=True)
@click.option("--this-week", is_flag=True)
@click.option("--next-week", is_flag=True)
@click.option("--this-month", is_flag=True)
@click.option("--next-month", is_flag=True)
@click.option("--next", "next_", default=None, metavar="Xd|Xh|Xw")
def search(
    calendar_name: str,
    query: str,
    field: str,
    start: str | None,
    end: str | None,
    today: bool,
    this_week: bool,
    next_week: bool,
    this_month: bool,
    next_month: bool,
    next_: str | None,
    json_output: bool,
) -> None:
    """Server-side text search over events (CalDAV text-match)."""
    cfg = load()
    shortcut = _shortcut_range(today, this_week, next_week, this_month, next_month, next_, cfg.timezone)
    if shortcut and (start or end):
        fail("--start/--end cannot be combined with shortcut flags")

    if shortcut:
        start_dt, end_dt = shortcut
    else:
        start_dt = parse_datetime(start, cfg.timezone) if start else None
        end_dt = parse_datetime(end, cfg.timezone) if end else None

    fields = _EVENT_SEARCH_FIELDS[field]
    seen: set[str] = set()
    out: list[dict] = []
    with spinner(f"Searching '{query}' in {calendar_name}", json_output):
        with caldav_principal(cfg) as principal:
            cal = _find_calendar(principal, calendar_name)
            for f in fields:
                kwargs = {f: query, "event": True}
                if start_dt or end_dt:
                    kwargs.update(start=start_dt, end=end_dt, expand=True)
                for ev in cal.search(**kwargs):
                    ical = ICal.from_ical(ev.data)
                    for component in ical.walk("VEVENT"):
                        uid = str(component.get("UID"))
                        if uid in seen:
                            continue
                        seen.add(uid)
                        out.append(_vevent_to_dict(component))
    render_events(out, json_output)


@verbose_option
@json_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--summary", required=True)
@click.option("--start", required=True, help="ISO 8601 start datetime.")
@click.option("--end", default=None, help="ISO 8601 end datetime (defaults to start +1h).")
@click.option("--location", default="")
@click.option("--description", default="")
@click.option(
    "--attendee",
    "attendees",
    multiple=True,
    help='Invitee email or "Name <email>". Repeatable.',
)
@click.option("--organizer", default=None, help='Organizer email or "Name <email>".')
def create(
    calendar_name: str,
    summary: str,
    start: str,
    end: str | None,
    location: str,
    description: str,
    attendees: tuple[str, ...],
    organizer: str | None,
    json_output: bool,
) -> None:
    """Create a new event."""
    cfg = load()
    start_dt = parse_datetime(start, cfg.timezone)
    end_dt = parse_datetime(end, cfg.timezone) if end else start_dt + timedelta(hours=1)

    ical = ICal()
    ical.add("prodid", "-//nxcloud//EN")
    ical.add("version", "2.0")
    event = IEvent()
    uid = str(uuid.uuid4())
    event.add("uid", uid)
    event.add("summary", summary)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)

    if organizer:
        org = _attendee_property(organizer)
        event.add("organizer", org)
    for spec in attendees:
        event.add("attendee", _attendee_property(spec), encode=0)

    ical.add_component(event)

    with spinner(f"Creating event '{summary}'", json_output):
        with caldav_principal(cfg) as principal:
            cal = _find_calendar(principal, calendar_name)
            saved = cal.save_event(ical.to_ical().decode())
    render_status(
        "event created",
        json_output,
        uid=uid,
        url=str(saved.url),
        attendees=", ".join(str(a).replace("mailto:", "", 1) for a in (event.get("ATTENDEE") or []) if a) or "—",
    )


@verbose_option
@json_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--uid", required=True)
@click.option("--summary", default=None)
@click.option("--start", default=None)
@click.option("--end", default=None)
@click.option("--location", default=None)
@click.option("--description", default=None)
@click.option("--add-attendee", "add_attendees", multiple=True, help="Add an invitee. Repeatable.")
@click.option("--remove-attendee", "remove_attendees", multiple=True, help="Remove an invitee by email. Repeatable.")
def edit(
    calendar_name: str,
    uid: str,
    summary: str | None,
    start: str | None,
    end: str | None,
    location: str | None,
    description: str | None,
    add_attendees: tuple[str, ...],
    remove_attendees: tuple[str, ...],
    json_output: bool,
) -> None:
    """Update fields of an existing event."""
    cfg = load()
    with spinner(f"Updating event {uid}", json_output):
        with caldav_principal(cfg) as principal:
            cal = _find_calendar(principal, calendar_name)
            try:
                event = cal.event_by_uid(uid)
            except Exception:
                fail(f"event not found: {uid}")
            ical = ICal.from_ical(event.data)
            for component in ical.walk("VEVENT"):
                if summary is not None:
                    component["SUMMARY"] = summary
                if start is not None:
                    component["DTSTART"].dt = parse_datetime(start, cfg.timezone)
                if end is not None:
                    component["DTEND"].dt = parse_datetime(end, cfg.timezone)
                if location is not None:
                    component["LOCATION"] = location
                if description is not None:
                    component["DESCRIPTION"] = description

                if remove_attendees:
                    kept = []
                    existing = component.get("ATTENDEE")
                    if existing is not None:
                        existing_list = existing if isinstance(existing, list) else [existing]
                        for prop in existing_list:
                            email = str(prop).replace("mailto:", "", 1)
                            if email not in remove_attendees:
                                kept.append(prop)
                    del component["ATTENDEE"]
                    for prop in kept:
                        component.add("attendee", prop, encode=0)
                for spec in add_attendees:
                    component.add("attendee", _attendee_property(spec), encode=0)

            event.data = ical.to_ical().decode()
            event.save()
    render_status("event updated", json_output, uid=uid)


@verbose_option
@json_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--uid", required=True)
def delete(calendar_name: str, uid: str, json_output: bool) -> None:
    """Delete an event."""
    cfg = load()
    with spinner(f"Deleting event {uid}", json_output):
        with caldav_principal(cfg) as principal:
            cal = _find_calendar(principal, calendar_name)
            try:
                event = cal.event_by_uid(uid)
            except Exception:
                fail(f"event not found: {uid}")
            event.delete()
    render_status("deleted", json_output, uid=uid)
