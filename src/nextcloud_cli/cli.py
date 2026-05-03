"""Top-level Click entry point."""

from __future__ import annotations

import click

from nextcloud_cli import __version__
from nextcloud_cli.commands.calendar import calendar
from nextcloud_cli.commands.check import check
from nextcloud_cli.commands.contacts import contacts
from nextcloud_cli.commands.files import files
from nextcloud_cli.commands.notes import notes
from nextcloud_cli.commands.setup import login, logout
from nextcloud_cli.commands.tasks import tasks
from nextcloud_cli.utils import CONTEXT_SETTINGS, verbose_option


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, prog_name="nxcloud")
@verbose_option
def main() -> None:
    """nxcloud — modern command-line client for Nextcloud."""


main.add_command(login)
main.add_command(logout)
main.add_command(check)
main.add_command(files)
main.add_command(notes)
main.add_command(calendar)
main.add_command(tasks)
main.add_command(contacts)


if __name__ == "__main__":
    main()
