"""Rich renderers for human-friendly CLI output.

Every renderer accepts ``json_output``: when True, the function delegates to
``emit`` so the legacy machine-readable format is preserved untouched.
"""

from __future__ import annotations

from typing import Any, Iterable

from rich.box import ROUNDED, SIMPLE_HEAD
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nextcloud_cli.utils import console, emit, format_size


def _truncate(value: str, limit: int = 60) -> str:
    if value is None:
        return ""
    value = str(value).replace("\n", " ").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_status(message: str, json_output: bool, **fields: Any) -> None:
    """Success/result line. JSON mode emits a {status, ...} object."""
    if json_output:
        emit({"status": message, **fields})
        return
    body = Text(message, style="bold green")
    if fields:
        body.append("\n")
        for k, v in fields.items():
            body.append(f"\n  {k}: ", style="dim")
            body.append(str(v), style="white")
    console.print(Panel(body, border_style="green", box=ROUNDED, expand=False))


def render_files_list(items: list[dict], path: str, json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(
        title=f"[bold]{path}[/bold]",
        box=SIMPLE_HEAD,
        header_style="bold magenta",
        title_justify="left",
    )
    table.add_column("", width=2)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right", style="green")
    table.add_column("Modified", style="dim")
    for entry in items:
        icon = "📁" if entry.get("type") == "directory" else "📄"
        size = "—" if entry.get("type") == "directory" else entry.get("size_human") or "0 B"
        table.add_row(icon, entry["name"], size, entry.get("modified") or "")
    console.print(table)
    console.print(f"[dim]{len(items)} item(s)[/dim]")


def render_notes_list(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="📝 Notes", title_justify="left")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Modified", style="dim")
    for n in items:
        table.add_row(
            str(n.get("id", "")),
            _truncate(n.get("title") or "(untitled)", 50),
            n.get("category") or "—",
            str(n.get("modified") or ""),
        )
    console.print(table)
    console.print(f"[dim]{len(items)} note(s)[/dim]")


def render_note(note: dict, json_output: bool) -> None:
    if json_output:
        emit(note)
        return
    title = note.get("title") or "(untitled)"
    category = note.get("category") or ""
    header = f"[bold cyan]{title}[/bold cyan]"
    if category:
        header += f"  [yellow]·[/yellow] [yellow]{category}[/yellow]"
    body = note.get("content", "") or "[dim](empty)[/dim]"
    console.print(Panel(body, title=header, border_style="cyan", box=ROUNDED))


def render_calendars(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="📅 Calendars", title_justify="left")
    table.add_column("Name", style="cyan")
    table.add_column("URL", style="dim")
    for c in items:
        table.add_row(c["name"], c.get("url", ""))
    console.print(table)
    console.print(f"[dim]{len(items)} calendar(s)[/dim]")


def render_events(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="📆 Events", title_justify="left")
    table.add_column("Start", style="green")
    table.add_column("End", style="dim")
    table.add_column("Summary", style="cyan")
    table.add_column("Location", style="yellow")
    table.add_column("Attendees", justify="right", style="magenta")
    for e in items:
        table.add_row(
            e.get("start") or "",
            e.get("end") or "",
            _truncate(e.get("summary") or "", 50),
            _truncate(e.get("location") or "", 25),
            str(len(e.get("attendees") or [])),
        )
    console.print(table)
    console.print(f"[dim]{len(items)} event(s)[/dim]")


_TASK_STATUS_STYLE = {
    "COMPLETED": ("✓", "green"),
    "NEEDS-ACTION": ("○", "yellow"),
    "IN-PROCESS": ("◐", "cyan"),
    "CANCELLED": ("✗", "red"),
}


def render_tasks(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="✅ Tasks", title_justify="left")
    table.add_column("", width=1)
    table.add_column("Summary", style="cyan")
    table.add_column("Due", style="green")
    table.add_column("Priority", justify="right")
    table.add_column("List", style="dim")
    for t in items:
        status = (t.get("status") or "").upper()
        glyph, style = _TASK_STATUS_STYLE.get(status, ("·", "white"))
        prio = t.get("priority")
        prio_str = str(prio) if prio else "—"
        summary = _truncate(t.get("summary") or "", 50)
        if status == "COMPLETED":
            summary = f"[strike dim]{summary}[/strike dim]"
        table.add_row(f"[{style}]{glyph}[/{style}]", summary, t.get("due") or "—", prio_str, t.get("list") or "")
    console.print(table)
    console.print(f"[dim]{len(items)} task(s)[/dim]")


def render_addressbooks(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="📇 Address books", title_justify="left")
    table.add_column("Name", style="cyan")
    table.add_column("Display name", style="white")
    table.add_column("Href", style="dim")
    for b in items:
        table.add_row(b["name"], b.get("displayname", ""), b.get("href", ""))
    console.print(table)
    console.print(f"[dim]{len(items)} address book(s)[/dim]")


def render_contacts(items: list[dict], json_output: bool) -> None:
    if json_output:
        emit(items)
        return
    table = Table(box=SIMPLE_HEAD, header_style="bold magenta", title="👥 Contacts", title_justify="left")
    table.add_column("Name", style="cyan")
    table.add_column("Emails", style="green")
    table.add_column("Phones", style="yellow")
    table.add_column("UID", style="dim")
    for c in items:
        emails = ", ".join(c.get("emails") or []) or "—"
        phones = ", ".join(c.get("phones") or []) or "—"
        table.add_row(c.get("fn") or "(no name)", _truncate(emails, 40), _truncate(phones, 30), _truncate(c.get("uid") or "", 20))
    console.print(table)
    console.print(f"[dim]{len(items)} contact(s)[/dim]")


def render_contact(card: dict, json_output: bool) -> None:
    if json_output:
        emit(card)
        return
    body = Text()
    body.append(card.get("fn") or "(no name)", style="bold cyan")
    body.append("\n\n")
    body.append("Emails:\n", style="bold")
    for e in card.get("emails") or []:
        body.append(f"  • {e}\n", style="green")
    if not card.get("emails"):
        body.append("  —\n", style="dim")
    body.append("\nPhones:\n", style="bold")
    for p in card.get("phones") or []:
        body.append(f"  • {p}\n", style="yellow")
    if not card.get("phones"):
        body.append("  —\n", style="dim")
    body.append(f"\nUID: ", style="dim")
    body.append(card.get("uid") or "—", style="dim")
    console.print(Panel(body, border_style="cyan", box=ROUNDED, expand=False))


def render_check(results: dict, json_output: bool) -> None:
    if json_output:
        emit(results)
        return
    header = Text()
    header.append("URL: ", style="bold")
    header.append(f"{results['url']}\n")
    header.append("User: ", style="bold")
    header.append(f"{results['username']}\n")
    header.append("Timezone: ", style="bold")
    header.append(f"{results['timezone']}")
    console.print(Panel(header, title="🔌 Connectivity check", border_style="cyan", box=ROUNDED, expand=False))

    table = Table(box=SIMPLE_HEAD, header_style="bold magenta")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Method", style="dim")
    table.add_column("Status", justify="right")
    table.add_column("Time", justify="right", style="green")
    table.add_column("URL", style="dim")
    all_ok = True
    for label, info in results["endpoints"].items():
        ok = info.get("ok")
        if not ok:
            all_ok = False
        if ok:
            status_cell = f"[green]✓ {info.get('status')}[/green]"
        else:
            status_cell = f"[red]✗ {info.get('status') or info.get('error_type', 'ERR')}[/red]"
        table.add_row(label, info["method"], status_cell, f"{info['elapsed_ms']} ms", info["url"])
    console.print(table)
    if all_ok:
        console.print("[bold green]✓ all endpoints reachable[/bold green]")
    else:
        console.print("[bold red]✗ some endpoints failed[/bold red]")
