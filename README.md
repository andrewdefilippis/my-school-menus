# My School Menus

Turn your school's [Health-e Pro / My School Menus](https://menus.healthepro.com) breakfast and lunch menus into
iCalendar (`.ics`) feeds you can subscribe to in Apple Calendar, Google Calendar, or anything else that reads iCalendar.

- One calendar per school and meal, e.g. **Example Elementary Lunch**, with one all-day event per school day:
  `Example Elementary Lunch: Popcorn Chicken or Bean and Cheese Pupusa`. The full menu is in the event notes.
- Days without a menu (holidays, days off) get no event.
- Event IDs are stable, so re-importing or refreshing updates events in place instead of creating duplicates.
- The current menu is looked up from the school each run, so nothing needs editing when the school year changes.

Requires Python 3.11+.

## Install

```sh
uv tool install my-school-menus    # or: pipx install my-school-menus
```

## Find your IDs

Open your school's menu on [menus.healthepro.com](https://menus.healthepro.com). The URL contains the IDs:

```
https://menus.healthepro.com/organizations/<district>/sites/<site>/menus/<menu>
```

You need `<district>` and `<site>`. `<menu>` is only needed to override automatic lookup.

## Command line

```sh
# Breakfast and lunch for one school, written to ./<district>-<site>-breakfast.ics and ./<district>-<site>-lunch.ics
my-school-menus --district 1000 --site 2000

# Only lunch, into a directory
my-school-menus --district 1000 --site 2000 --meal lunch --output-dir feeds/

# Only lunch, to a specific file (or "-" for stdout)
my-school-menus --district 1000 --site 2000 --meal lunch -o lunch.ics

# Use a specific menu ID instead of looking it up
my-school-menus --district 1000 --site 2000 --menu 3000 -o lunch.ics
```

| Option | Meaning |
|---|---|
| `--meal {breakfast,lunch}` | Repeatable. Default: every meal the school publishes (a missing meal is a warning). Naming a meal that doesn't exist is an error. |
| `--menu ID` | Skip lookup and use this menu. Can't be combined with `--meal`. |
| `-o FILE` | Write to this file (`-` for stdout). Only when exactly one feed is produced. |
| `--output-dir DIR` | Directory for feeds, created if missing (default: current directory). Can't be combined with `-o`. |
| `--quiet` | Don't print the files written. Errors are still printed. |
| `--force-ipv4` | Connect over IPv4 only, for networks with broken IPv6. |

The command exits with status 1 and prints a one-line `error:` message if the service is unreachable or returns
something unexpected.

Filenames are built from IDs only (`<district>-<site>-<meal>.ics`). If the district renames a school, the calendar and
event names change, but the filename and therefore any subscription URL stay the same.

## Library

```python
from my_school_menus import Client, DistrictId, MealType, SiteId, build_calendar, feed_filename

district, site_id = DistrictId(1000), SiteId(2000)
with Client() as client:
    site = client.site(district, site_id)
    menu = client.find_menu(district, site_id, MealType.LUNCH)
    days = client.days(district, menu)  # every published month; months without data are skipped

with open(feed_filename(site, menu), "wb") as f:
    f.write(build_calendar(site, menu, days).to_ical())
```

All errors derive from `my_school_menus.MenusError`:

- `UpstreamError`: an HTTP failure or the service is unreachable.
- `NotFoundError`: the service returned no data.
- `PayloadError`: the response has a shape this library doesn't understand.

## Subscription feeds (GitHub Actions + Gist)

The [`menu-feeds`](.github/workflows/menu-feeds.yml) workflow rebuilds the feeds every night and publishes them to a
**secret Gist**. Your calendars subscribe to the Gist's raw URLs and pick up menu changes automatically. It costs
nothing: about a minute of Actions time per day.

### One-time setup

1. **Create a secret Gist** at <https://gist.github.com> with any placeholder file (e.g. `README.md`). Note its ID,
   the last part of the URL.
2. **Create a fine-grained personal access token**
   (*Settings → Developer settings → Fine-grained tokens*):
   - Repository access: *Public repositories (read-only)*. It doesn't need any repository.
   - Account permissions: **Gists → Read and write**. Nothing else.
   - This permission can't be limited to one Gist: the token can edit or delete **every** Gist on the account. For
     the tightest scope, create the Gist and token under a separate GitHub account used only for the feeds.
   - Set a short expiration (e.g. 90 days), and put a reminder in your calendar to rotate it. When it expires, the
     workflow fails and GitHub emails you.
3. **Add repository secrets** (*Settings → Secrets and variables → Actions*):

   | Secret | Value |
   |---|---|
   | `MSM_SCHOOLS` | One `district site` pair per line, e.g. `1000 2000`. Lines starting with `#` are ignored. |
   | `MENU_GIST_ID` | The Gist ID from step 1 |
   | `MENU_GIST_TOKEN` | The token from step 2 |

4. **Run it once:** *Actions → Menu feeds → Run workflow*.
5. **Subscribe:** open the Gist and use each file's *Raw* URL **without** the revision hash:
   `https://gist.githubusercontent.com/<user>/<gist-id>/raw/<district>-<site>-<meal>.ics`.
   The `X-WR-CALNAME` line near the top of each file shows which school and meal it is.
   - Apple Calendar (macOS): *File → New Calendar Subscription…*, paste the URL, set **Location: iCloud** so it syncs
     to your iPhone, and set **Auto-refresh: Every day**.
   - Google Calendar: *Other calendars → + → From URL*. Google refreshes on its own schedule, typically within a day.

### Adding a school

Add another `district site` line to `MSM_SCHOOLS`, run the workflow, and subscribe to the new files. A school that
fails to build doesn't stop the others from updating, but the run is marked failed. Each school has a one-minute limit.

The workflow never deletes Gist files. When you remove a school, delete its files from the Gist yourself. Older
revisions stay in the Gist's history.

### When a run fails

To keep the public logs free of school details, the log only says which school failed by its line number in
`MSM_SCHOOLS` (e.g. `MSM_SCHOOLS line 2 failed to build`). To see the actual error, run the same command locally:
`my-school-menus --district <district> --site <site> --output-dir /tmp/feeds`.

### Changing the schedule or timezone

The workflow runs daily at 03:17 in `America/Los_Angeles`. Edit `cron` and `timezone` in
`.github/workflows/menu-feeds.yml` for your area. The feeds themselves don't depend on timezone: events are all-day
dates.

### Privacy

A secret Gist is unlisted but not private. Anyone with the URL can read the menus and see the school names, including
older revisions in its history.

The run logs of a public repository are public. The workflow masks the district and site IDs and discards the
command's error output, which can contain menu IDs and names. The log shows only counts and the failing school's line
number.

### Keeping it running

GitHub disables scheduled workflows in public repositories after 60 days without repository activity, and Gist
updates don't count. Each run calls GitHub's "enable workflow" API on itself as a keepalive. That's a common
workaround, but GitHub doesn't document it as resetting the timer. If the schedule ever stops, re-enable it on the
Actions tab, or push any commit.

## Upgrading from 0.1.x

0.2.0 is a rewrite with a new API:

| 0.1.x | 0.2.0 |
|---|---|
| `my_school_menus.msm_api.Menus().get(...)` | `Client().menu(...)`, `Client().month(...)`, `Client().find_menu(...)` |
| `my_school_menus.msm_api.Sites().get(...)` | `Client().site(...)` |
| `my_school_menus.msm_api.Organizations` | removed |
| `my_school_menus.msm_calendar.Calendar` | `build_calendar(site, menu, days)` |
| `example/generate_ics_files.py` (one file per month) | `my-school-menus` command (one file per meal, all months) |
| `ValueError` | `MenusError` and its subclasses |
| Importing forced IPv4 for the whole process | `Client(force_ipv4=True)` / `--force-ipv4`, scoped to the client |

Calendars imported from 0.1.x files have no stable IDs. Delete those events (or that calendar) before importing or
subscribing to 0.2.0 feeds to avoid seeing meals twice.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```
