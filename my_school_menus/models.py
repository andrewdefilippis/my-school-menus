from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import IntEnum, StrEnum
from typing import NewType, TypeVar

from .errors import PayloadError

DistrictId = NewType("DistrictId", int)
SiteId = NewType("SiteId", int)
MenuId = NewType("MenuId", int)

T = TypeVar("T")


class MealType(IntEnum):
    BREAKFAST = 1
    LUNCH = 2


class ItemKind(StrEnum):
    CATEGORY = "category"
    RECIPE = "recipe"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Site:
    id: SiteId
    district: DistrictId
    name: str


@dataclass(frozen=True, slots=True)
class Menu:
    id: MenuId
    name: str
    meal_type: MealType | None
    published_months: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class MenuItem:
    kind: ItemKind
    name: str


@dataclass(frozen=True, slots=True)
class Section:
    title: str | None
    items: tuple[MenuItem, ...]


@dataclass(frozen=True, slots=True)
class MenuDay:
    day: date
    sections: tuple[Section, ...]

    @property
    def headline(self) -> tuple[str, ...]:
        """Recipe names of the first section that has any recipes (the entrée choices)."""
        for section in self.sections:
            recipes = tuple(item.name for item in section.items if item.kind is ItemKind.RECIPE)
            if recipes:
                return recipes
        return ()


def clean_text(text: str) -> str:
    """Drop control, format and lone surrogate characters (invalid in iCalendar TEXT) and collapse whitespace."""
    kept = "".join(ch for ch in text if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf", "Cs"))
    return " ".join(kept.split())


def _object(raw: object, context: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise PayloadError(f"{context}: expected an object, got {type(raw).__name__}")
    return raw


def _list(raw: object, context: str) -> list[object]:
    if not isinstance(raw, list):
        raise PayloadError(f"{context}: expected a list, got {type(raw).__name__}")
    return raw


def _field(raw: object, key: str, kind: type[T], context: str) -> T:
    obj = _object(raw, context)
    if key not in obj:
        raise PayloadError(f"{context}: missing key {key!r}")
    value = obj[key]
    # bool is a subclass of int; reject it where an int is expected.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise PayloadError(f"{context}: {key!r} should be {kind.__name__}, got {type(value).__name__}")
    return value


def _date(value: str, context: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as e:
        raise PayloadError(f"{context}: invalid date {value!r}") from e


def _meal_type(value: object) -> MealType | None:
    if type(value) is not int:
        return None
    try:
        return MealType(value)
    except ValueError:
        return None


def parse_site(raw: object) -> Site:
    context = "site"
    custom_name = _object(raw, context).get("custom_name")
    name = custom_name if isinstance(custom_name, str) and custom_name.strip() else _field(raw, "name", str, context)
    return Site(
        id=SiteId(_field(raw, "id", int, context)),
        district=DistrictId(_field(raw, "organization_id", int, context)),
        name=clean_text(name),
    )


def parse_menu(raw: object) -> Menu:
    menu_id = _field(raw, "id", int, "menu")
    context = f"menu {menu_id}"
    months: list[date] = []
    published: list[object] = _field(raw, "published_months", list, context)
    for month in published:
        if not isinstance(month, str):
            raise PayloadError(f"{context}: 'published_months' should contain strings")
        months.append(_date(month, context))
    return Menu(
        id=MenuId(menu_id),
        name=clean_text(_field(raw, "name", str, context)),
        meal_type=_meal_type(_object(raw, context).get("meal_type_id")),
        published_months=tuple(months),
    )


def parse_site_menus(raw: object) -> tuple[Menu, ...]:
    return tuple(parse_menu(entry) for entry in _list(raw, "site menus"))


def _parse_item(raw: object, context: str) -> MenuItem:
    kind = _field(raw, "type", str, context)
    try:
        item_kind = ItemKind(kind)
    except ValueError as e:
        raise PayloadError(f"{context}: unknown item type {kind!r}") from e
    return MenuItem(kind=item_kind, name=clean_text(_field(raw, "name", str, context)))


def _parse_sections(items: list[MenuItem]) -> tuple[Section, ...]:
    sections: list[Section] = []
    title: str | None = None
    current: list[MenuItem] = []
    for item in items:
        if item.kind is ItemKind.CATEGORY:
            if title is not None or current:
                sections.append(Section(title=title, items=tuple(current)))
            title, current = item.name, []
        else:
            current.append(item)
    if title is not None or current:
        sections.append(Section(title=title, items=tuple(current)))
    return tuple(sections)


def _parse_day(raw: object) -> MenuDay | None:
    day = _date(_field(raw, "day", str, "menu day"), "menu day")
    context = f"menu day {day.isoformat()}"
    try:
        setting: object = json.loads(_field(raw, "setting", str, context))
    except (ValueError, RecursionError) as e:
        raise PayloadError(f"{context}: 'setting' is not valid JSON") from e
    display: list[object] = _field(setting, "current_display", list, context)
    items = [_parse_item(item, context) for item in display]
    if not any(item.kind is ItemKind.RECIPE for item in items):
        return None
    return MenuDay(day=day, sections=_parse_sections(items))


def parse_month(raw: object) -> tuple[MenuDay, ...]:
    """Return only days that serve at least one recipe; skip null entries and days off."""
    days: dict[date, MenuDay] = {}
    for entry in _list(raw, "month"):
        if entry is None:
            continue
        day = _parse_day(entry)
        if day is None:
            continue
        if day.day in days:
            raise PayloadError(f"month: duplicate entries for {day.day.isoformat()}")
        days[day.day] = day
    return tuple(days.values())
