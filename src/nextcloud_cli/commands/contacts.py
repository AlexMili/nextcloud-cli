"""Contacts (CardDAV) operations."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import click
import vobject

from nextcloud_cli.client import http_client
from nextcloud_cli.config import Config, load
from nextcloud_cli.rendering import (
    render_addressbooks,
    render_contact,
    render_contacts,
    render_status,
)
from nextcloud_cli.utils import CONTEXT_SETTINGS, fail, json_option, spinner, verbose_option

CARDDAV_NS = {"d": "DAV:", "card": "urn:ietf:params:xml:ns:carddav"}

PROPFIND_ADDRESSBOOKS = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>"""

REPORT_ADDRESSBOOK_QUERY = """<?xml version="1.0" encoding="utf-8"?>
<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:getetag/>
    <card:address-data/>
  </d:prop>
</card:addressbook-query>"""


@click.group(context_settings=CONTEXT_SETTINGS)
def contacts() -> None:
    """Manage contacts via CardDAV."""


def _abook_url(cfg: Config, name: str) -> str:
    return f"{cfg.carddav_principal.rstrip('/')}/{name}/"


def _vcard_to_dict(card: vobject.base.Component) -> dict:
    fn = getattr(card, "fn", None)
    emails = [e.value for e in card.contents.get("email", [])]
    tels = [t.value for t in card.contents.get("tel", [])]
    return {
        "uid": getattr(card, "uid", None).value if hasattr(card, "uid") else None,
        "fn": fn.value if fn else None,
        "emails": emails,
        "phones": tels,
    }


@verbose_option
@json_option
@contacts.command("list")
def list_addressbooks(json_output: bool) -> None:
    """List address books."""
    cfg = load()
    with spinner("Fetching address books", json_output):
        with http_client(cfg, accept="application/xml") as http:
            response = http.request(
                "PROPFIND",
                cfg.carddav_principal,
                content=PROPFIND_ADDRESSBOOKS,
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
    if response.status_code >= 400:
        fail(f"PROPFIND failed: {response.status_code}")

    root = ET.fromstring(response.text)
    books = []
    for resp in root.findall("d:response", CARDDAV_NS):
        href = resp.findtext("d:href", "", CARDDAV_NS)
        if href.rstrip("/") == cfg.carddav_principal.rstrip("/").split(cfg.url, 1)[-1].rstrip("/"):
            continue
        display = resp.findtext(".//d:displayname", "", CARDDAV_NS)
        if display:
            books.append({"name": Path(href.rstrip("/")).name, "displayname": display, "href": href})
    render_addressbooks(books, json_output)


_PROP_FIELDS = {
    "name": ("FN",),
    "email": ("EMAIL",),
    "phone": ("TEL",),
    "all": ("FN", "EMAIL", "TEL"),
}


def _build_search_report(query: str, fields: tuple[str, ...]) -> str:
    """Build a CardDAV addressbook-query REPORT body with text-match filters."""
    safe = xml_escape(query)
    filters = "\n".join(
        f'    <card:prop-filter name="{f}">'
        f'      <card:text-match collation="i;unicode-casemap" match-type="contains">{safe}</card:text-match>'
        f'    </card:prop-filter>'
        for f in fields
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:getetag/>
    <card:address-data/>
  </d:prop>
  <card:filter test="anyof">
{filters}
  </card:filter>
</card:addressbook-query>"""


@verbose_option
@json_option
@contacts.command()
@click.option("--addressbook", required=True)
@click.option("--query", required=True, help="Substring to match (case-insensitive).")
@click.option(
    "--in",
    "field",
    type=click.Choice(list(_PROP_FIELDS.keys())),
    default="all",
    help="Which vCard property to search (default: all).",
)
def search(addressbook: str, query: str, field: str, json_output: bool) -> None:
    """Server-side search across contacts in an address book (CardDAV text-match)."""
    cfg = load()
    body = _build_search_report(query, _PROP_FIELDS[field])
    with spinner(f"Searching '{query}' in {addressbook}", json_output):
        with http_client(cfg, accept="application/xml") as http:
            response = http.request(
                "REPORT",
                _abook_url(cfg, addressbook),
                content=body,
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
    if response.status_code >= 400:
        fail(f"REPORT failed: {response.status_code}: {response.text}")

    root = ET.fromstring(response.text)
    out = []
    for resp in root.findall("d:response", CARDDAV_NS):
        href = resp.findtext("d:href", "", CARDDAV_NS)
        data = resp.findtext(".//card:address-data", "", CARDDAV_NS)
        if not data:
            continue
        try:
            card = vobject.readOne(data)
        except Exception:
            continue
        item = _vcard_to_dict(card)
        item["href"] = href
        out.append(item)
    render_contacts(out, json_output)


@verbose_option
@json_option
@contacts.command()
@click.option("--addressbook", required=True)
def cards(addressbook: str, json_output: bool) -> None:
    """List contacts in an address book."""
    cfg = load()
    with spinner(f"Fetching contacts from {addressbook}", json_output):
        with http_client(cfg, accept="application/xml") as http:
            response = http.request(
                "REPORT",
                _abook_url(cfg, addressbook),
                content=REPORT_ADDRESSBOOK_QUERY,
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
    if response.status_code >= 400:
        fail(f"REPORT failed: {response.status_code}")

    root = ET.fromstring(response.text)
    out = []
    for resp in root.findall("d:response", CARDDAV_NS):
        href = resp.findtext("d:href", "", CARDDAV_NS)
        data = resp.findtext(".//card:address-data", "", CARDDAV_NS)
        if not data:
            continue
        try:
            card = vobject.readOne(data)
        except Exception:
            continue
        item = _vcard_to_dict(card)
        item["href"] = href
        out.append(item)
    render_contacts(out, json_output)


@verbose_option
@json_option
@contacts.command()
@click.option("--addressbook", required=True)
@click.option("--uid", required=True)
def get(addressbook: str, uid: str, json_output: bool) -> None:
    """Fetch a single contact by UID."""
    cfg = load()
    with spinner(f"Fetching contact {uid}", json_output):
        with http_client(cfg, accept="application/xml") as http:
            response = http.request(
                "REPORT",
                _abook_url(cfg, addressbook),
                content=REPORT_ADDRESSBOOK_QUERY,
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
    if response.status_code >= 400:
        fail(f"REPORT failed: {response.status_code}")

    root = ET.fromstring(response.text)
    for resp in root.findall("d:response", CARDDAV_NS):
        data = resp.findtext(".//card:address-data", "", CARDDAV_NS)
        if not data:
            continue
        try:
            card = vobject.readOne(data)
        except Exception:
            continue
        if hasattr(card, "uid") and card.uid.value == uid:
            render_contact(_vcard_to_dict(card), json_output)
            return
    fail(f"contact not found: {uid}")


@verbose_option
@json_option
@contacts.command()
@click.option("--addressbook", required=True)
@click.option("--uid", required=True)
@click.option("--local", "local", required=True, type=click.Path(dir_okay=False))
def export(addressbook: str, uid: str, local: str, json_output: bool) -> None:
    """Export a contact as a vCard file."""
    cfg = load()
    with spinner(f"Exporting contact {uid}", json_output):
        with http_client(cfg, accept="application/xml") as http:
            response = http.request(
                "REPORT",
                _abook_url(cfg, addressbook),
                content=REPORT_ADDRESSBOOK_QUERY,
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
    if response.status_code >= 400:
        fail(f"REPORT failed: {response.status_code}")

    root = ET.fromstring(response.text)
    for resp in root.findall("d:response", CARDDAV_NS):
        data = resp.findtext(".//card:address-data", "", CARDDAV_NS)
        if not data:
            continue
        try:
            card = vobject.readOne(data)
        except Exception:
            continue
        if hasattr(card, "uid") and card.uid.value == uid:
            Path(local).write_text(card.serialize())
            render_status("exported", json_output, uid=uid, path=local)
            return
    fail(f"contact not found: {uid}")
