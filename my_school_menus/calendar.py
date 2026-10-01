from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import icalendar
from icalendar.enums import TRANSP

from .models import Menu, MenuDay, Site, clean_text

PRODID = "-//andrewdefilippis//my-school-menus//EN"
UID_DOMAIN = "my-school-menus"
DEFAULT_REFRESH_INTERVAL = timedelta(hours=12)


def meal_label(menu: Menu) -> str:
    return menu.meal_type.name.title() if menu.meal_type else "Menu"


def _meal_key(menu: Menu) -> str:
    return menu.meal_type.name.lower() if menu.meal_type else f"menu-{menu.id}"


def event_uid(site: Site, menu: Menu, day: MenuDay) -> str:
    return f"{site.id}-{menu.id}-{day.day.isoformat()}@{UID_DOMAIN}"


def calendar_uid(site: Site, menu: Menu) -> str:
    return f"{site.district}-{site.id}-{_meal_key(menu)}@{UID_DOMAIN}"


def calendar_name(site: Site, menu: Menu) -> str:
    return f"{site.name} {meal_label(menu)}"


def feed_filename(site: Site, menu: Menu) -> str:
    """Built only from IDs and our own enum so the subscription URL survives renames upstream."""
    return f"{site.district}-{site.id}-{_meal_key(menu)}.ics"


def summary(site: Site, menu: Menu, day: MenuDay) -> str:
    name = calendar_name(site, menu)
    return f"{name}: {' or '.join(day.headline)}" if day.headline else name


def description(day: MenuDay) -> str:
    blocks = []
    for section in day.sections:
        lines = [f"{section.title}:"] if section.title else []
        lines += [item.name for item in section.items]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_calendar(
    site: Site,
    menu: Menu,
    days: Iterable[MenuDay],
    *,
    name: str | None = None,
    stamp: datetime | None = None,
    refresh_interval: timedelta = DEFAULT_REFRESH_INTERVAL,
) -> icalendar.Calendar:
    stamp = stamp or datetime.now(UTC)
    ordered = sorted(days, key=lambda d: d.day)
    for previous, current in pairwise(ordered):
        if previous.day == current.day:
            raise ValueError(f"duplicate menu day {current.day.isoformat()}: event UIDs must be unique")
    events = [
        icalendar.Event.new(
            uid=event_uid(site, menu, day),
            stamp=stamp,
            start=day.day,
            summary=summary(site, menu, day),
            description=description(day),
            transparency=TRANSP.TRANSPARENT,
        )
        for day in ordered
    ]
    return icalendar.Calendar.new(
        prodid=PRODID,
        name=clean_text(name or "") or calendar_name(site, menu),
        uid=calendar_uid(site, menu),
        refresh_interval=refresh_interval,
        subcomponents=events,
    )
