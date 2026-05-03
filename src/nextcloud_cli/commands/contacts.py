"""Contacts (CardDAV) operations.

Address books are listed via PROPFIND. Cards are fetched via REPORT and
parsed with vobject for stable field access.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import click
import vobject

from nextcloud_cli.client import http_client
from nextcloud_cli.config import Config, load
from nextcloud_cli.utils import CONTEXT_SETTINGS, emit, fail, verbose_option

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


def _vcard_to_dict(card: "vobject.base.Component") -> dict:
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
@contacts.command("list")
def list_addressbooks() -> None:
    """List address books."""
    cfg = load()
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
    emit(books)


@verbose_option
@contacts.command()
@click.option("--addressbook", required=True)
def cards(addressbook: str) -> None:
    """List contacts in an address book."""
    cfg = load()
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
    emit(out)


@verbose_option
@contacts.command()
@click.option("--addressbook", required=True)
@click.option("--uid", required=True)
def get(addressbook: str, uid: str) -> None:
    """Fetch a single contact by UID."""
    cfg = load()
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
            emit(_vcard_to_dict(card))
            return
    fail(f"contact not found: {uid}")


@verbose_option
@contacts.command()
@click.option("--addressbook", required=True)
@click.option("--uid", required=True)
@click.option("--local", "local", required=True, type=click.Path(dir_okay=False))
def export(addressbook: str, uid: str, local: str) -> None:
    """Export a contact as a vCard file."""
    cfg = load()
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
            emit({"status": "exported", "uid": uid, "path": local})
            return
    fail(f"contact not found: {uid}")
