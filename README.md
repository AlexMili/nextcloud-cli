# nextcloud-cli

`nxcloud` is a modern command-line client for self-hosted Nextcloud. Manage
files, notes, calendar events, tasks, and contacts from the terminal — over
HTTPS only, no desktop sync client required.

It speaks WebDAV via [`webdav4`](https://pypi.org/project/webdav4/), CalDAV
via [`caldav`](https://pypi.org/project/caldav/), CardDAV via raw `httpx` +
[`vobject`](https://pypi.org/project/vobject/), and the Nextcloud Notes REST
API via `httpx`. Credentials are stored in your OS keyring.

## Features

- **Files** — list, upload, download, move, delete, mkdir, recursive search
- **Notes** — create, read, update, delete (Nextcloud Notes app required)
- **Calendar** — list calendars, list/create/edit/delete events, **with attendees and organizer**
- **Tasks** — list/create/complete/edit/delete VTODO items
- **Contacts** — list address books, list/get/export vCards
- **Login wizard** that validates the credentials with a `PROPFIND` and stores the password in the OS keyring (with a `chmod 0600` JSON fallback)
- **JSON output everywhere** so you can pipe into `jq` and friends
- `-h` / `--help` available on every command and subcommand

## Installation

```bash
pip install nextcloud-cli
```

Or from source:

```bash
git clone https://github.com/AlexMili/nextcloud-cli
cd nextcloud-cli
pip install -e .
```

The installed binary is **`nxcloud`**.

## Login

Create a Nextcloud **app password** first
(`Settings → Security → App passwords`), then:

```bash
nxcloud login
```

You'll only be prompted for what's missing. Values are resolved in this order:

1. CLI flag (`--url`, `--username`, `--password`, `--timezone`)
2. Environment variable (`NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_TOKEN`, `NEXTCLOUD_TIMEZONE`)
3. Interactive prompt

So all of these work:

```bash
# Fully interactive
nxcloud login

# Mixed: URL from env, prompt for the rest
NEXTCLOUD_URL=https://nc.example.com nxcloud login

# Fully non-interactive (no prompts)
nxcloud login \
    --url https://nc.example.com \
    --username alice \
    --password 'app-pass-here' \
    --timezone Europe/Paris
```

You can also skip persistence entirely and rely on environment variables for
every command:

```bash
export NEXTCLOUD_URL=https://nc.example.com
export NEXTCLOUD_USER=alice
export NEXTCLOUD_TOKEN=app-pass-here
export NEXTCLOUD_TIMEZONE=Europe/Paris
nxcloud check
```

To remove stored credentials:

```bash
nxcloud logout
```

## Usage

Every command emits JSON on stdout for easy scripting. Use `-h` on any
command or subcommand for built-in help.

### Connectivity check

```bash
nxcloud check
```

### Files

```bash
nxcloud files list --path /Documents
nxcloud files upload --local ./report.pdf --remote /Documents/report.pdf
nxcloud files download --remote /Documents/report.pdf --local ./report.pdf
nxcloud files move --src /tmp/a.txt --dst /archive/a.txt
nxcloud files mkdir --path /new-folder
nxcloud files delete --path /old.txt
nxcloud files search --query report --limit 20    # OCS unified search (server-side)
```

### Notes (requires the Nextcloud Notes app)

```bash
nxcloud notes list
nxcloud notes list --category Work              # notes in the "Work" folder
nxcloud notes list --category "Work/Projects"   # nested folder (subdirectory)
nxcloud notes list --category=""                # only notes at the Notes/ root (no category)
nxcloud notes list --limit 10                   # cap the number of notes fetched
nxcloud notes get --id 941
nxcloud notes create --title "Meeting" --content "Q3 roadmap." --category Work
nxcloud notes edit --id 941 --title "Updated"
nxcloud notes delete --id 941
```

> In the Nextcloud Notes app, **category = folder**: notes are stored as
> Markdown files under `Notes/<category>/`, and `/` separates subdirectories.
> `--category` matches **exactly** — `--category Work` does not include
> `Work/Projects`. Use `--category=""` to list only notes at the root.

### Calendar

List calendars and events:

```bash
nxcloud calendar list
nxcloud calendar events --calendar Personal --start 2026-05-01 --end 2026-05-31
```

Date-range shortcuts (server-side filtering, in your configured timezone):

```bash
nxcloud calendar events --calendar Personal --today
nxcloud calendar events --calendar Personal --this-week     # current Mon → Mon
nxcloud calendar events --calendar Personal --next-week     # upcoming Mon → Mon
nxcloud calendar events --calendar Personal --this-month    # 1st → 1st of next month
nxcloud calendar events --calendar Personal --next-month
nxcloud calendar events --calendar Personal --next 7d       # also: 48h, 2w
```

> Shortcuts are mutually exclusive with each other and with `--start/--end`.

Create an event with attendees and an organizer:

```bash
nxcloud calendar create \
    --calendar Work \
    --summary "Project sync" \
    --start 2026-07-01T14:00:00 \
    --end   2026-07-01T15:00:00 \
    --location "Room 4B" \
    --description "Quarterly review" \
    --organizer "Alice <alice@example.com>" \
    --attendee "Bob <bob@example.com>" \
    --attendee carol@example.com
```

`--attendee` is repeatable and accepts either a bare email or the
`Name <email>` form.

Edit an event (including adding/removing invitees):

```bash
nxcloud calendar edit --calendar Work --uid <uid> --summary "New title"
nxcloud calendar edit --calendar Work --uid <uid> \
    --add-attendee "Dan <dan@example.com>" \
    --remove-attendee carol@example.com
```

Delete an event:

```bash
nxcloud calendar delete --calendar Work --uid <uid>
```

Search events server-side (CalDAV `text-match`). Combine with date filters:

```bash
nxcloud calendar search --calendar Work --query standup
nxcloud calendar search --calendar Work --query roadmap --in description
nxcloud calendar search --calendar Work --query "1:1" --this-week
# --in: summary | description | location | category | all  (default: summary)
```

### Tasks (VTODO)

```bash
nxcloud tasks list
nxcloud tasks list --include-completed
nxcloud tasks create --summary "Review PR" --due 2026-07-05 --priority 1
nxcloud tasks complete --uid <uid>
nxcloud tasks edit --uid <uid> --summary "Updated summary"
nxcloud tasks delete --uid <uid>
nxcloud tasks search --query "deploy" --include-completed
nxcloud tasks search --query "fix" --in description --list Work
# --in: summary | description | category | all  (default: summary)
```

### Contacts

```bash
nxcloud contacts list
nxcloud contacts cards --addressbook contacts
nxcloud contacts get --addressbook contacts --uid <uid>
nxcloud contacts export --addressbook contacts --uid <uid> --local ./alice.vcf
nxcloud contacts search --addressbook contacts --query alex
nxcloud contacts search --addressbook contacts --query "@example.com" --in email
# --in: name | email | phone | all  (default: all)
```

## Configuration files

| File | Purpose | Permissions |
|------|---------|-------------|
| `~/.config/nextcloud-cli/config.json` | URL, username, timezone | `0600` |
| OS keyring (entry `nextcloud-cli`) | App password | OS-managed |
| `~/.config/nextcloud-cli/secrets.json` | Password fallback when no keyring backend is available | `0600` |

Override the config directory with the `NEXTCLOUD_CLI_HOME` environment variable.

## Help

`-h` and `--help` are wired up at every level:

```bash
nxcloud --help
nxcloud calendar --help
nxcloud calendar create --help
```

## License

MIT
