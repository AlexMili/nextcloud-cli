"""Calendar (CalDAV) operations."""

from __future__ import annotations

import uuid
from datetime import timedelta

import click
from icalendar import Calendar as ICal
from icalendar import Event as IEvent
from icalendar import vCalAddress, vText

from nextcloud_cli.client import caldav_principal
from nextcloud_cli.config import load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, fail, parse_datetime, verbose_option


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
@calendar.command("list")
def list_calendars() -> None:
    """List all calendars."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cals = [
            {
                "name": cal.name,
                "url": str(cal.url),
            }
            for cal in principal.calendars()
        ]
    emit(cals)


@verbose_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--start", default=None, help="ISO 8601 start of range.")
@click.option("--end", default=None, help="ISO 8601 end of range.")
def events(calendar_name: str, start: str | None, end: str | None) -> None:
    """List events in a calendar, optionally within a date range."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cal = _find_calendar(principal, calendar_name)
        if start or end:
            start_dt = parse_datetime(start, cfg.timezone) if start else None
            end_dt = parse_datetime(end, cfg.timezone) if end else None
            results = cal.search(start=start_dt, end=end_dt, event=True, expand=True)
        else:
            results = cal.events()

        out = []
        for event in results:
            ical = ICal.from_ical(event.data)
            for component in ical.walk("VEVENT"):
                attendees = []
                for prop in component.get("ATTENDEE", []) if isinstance(component.get("ATTENDEE"), list) else [component.get("ATTENDEE")] if component.get("ATTENDEE") else []:
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
                out.append(
                    {
                        "uid": str(component.get("UID")),
                        "summary": str(component.get("SUMMARY", "")),
                        "start": component.decoded("DTSTART").isoformat() if component.get("DTSTART") else None,
                        "end": component.decoded("DTEND").isoformat() if component.get("DTEND") else None,
                        "location": str(component.get("LOCATION", "")),
                        "description": str(component.get("DESCRIPTION", "")),
                        "organizer": str(component.get("ORGANIZER", "")).replace("mailto:", "", 1) or None,
                        "attendees": attendees,
                    }
                )
    emit(out)


@verbose_option
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
) -> None:
    """Create a new event.

    \b
    Example with invitees:
        nxcloud calendar create \\
            --calendar Work \\
            --summary "Project sync" \\
            --start 2026-07-01T14:00:00 \\
            --end   2026-07-01T15:00:00 \\
            --location "Room 4B" \\
            --organizer "Alice <alice@example.com>" \\
            --attendee "Bob <bob@example.com>" \\
            --attendee carol@example.com
    """
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
        # Organizer uses ORGANIZER property, not ATTENDEE.
        event.add("organizer", org)
    for spec in attendees:
        event.add("attendee", _attendee_property(spec), encode=0)

    ical.add_component(event)

    with caldav_principal(cfg) as principal:
        cal = _find_calendar(principal, calendar_name)
        saved = cal.save_event(ical.to_ical().decode())
    emit(
        {
            "status": "created",
            "uid": uid,
            "url": str(saved.url),
            "attendees": [str(a).replace("mailto:", "", 1) for a in (event.get("ATTENDEE") or []) if a],
        }
    )


@verbose_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--uid", required=True)
@click.option("--summary", default=None)
@click.option("--start", default=None)
@click.option("--end", default=None)
@click.option("--location", default=None)
@click.option("--description", default=None)
@click.option(
    "--add-attendee",
    "add_attendees",
    multiple=True,
    help='Add an invitee. Repeatable.',
)
@click.option(
    "--remove-attendee",
    "remove_attendees",
    multiple=True,
    help="Remove an invitee by email. Repeatable.",
)
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
) -> None:
    """Update fields of an existing event."""
    cfg = load()
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
    emit({"status": "updated", "uid": uid})


@verbose_option
@calendar.command()
@click.option("--calendar", "calendar_name", required=True)
@click.option("--uid", required=True)
def delete(calendar_name: str, uid: str) -> None:
    """Delete an event."""
    cfg = load()
    with caldav_principal(cfg) as principal:
        cal = _find_calendar(principal, calendar_name)
        try:
            event = cal.event_by_uid(uid)
        except Exception:
            fail(f"event not found: {uid}")
        event.delete()
    emit({"status": "deleted", "uid": uid})
