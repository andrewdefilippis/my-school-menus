import json
from datetime import date
from typing import Any

import pytest

from my_school_menus.errors import PayloadError
from my_school_menus.models import (
    ItemKind,
    MealType,
    MenuItem,
    Section,
    parse_menu,
    parse_month,
    parse_site,
    parse_site_menus,
)


def day_entry(day: str, display: list[dict[str, Any]], days_off: Any = None) -> dict[str, Any]:
    setting = {"current_display": display, "days_off": [] if days_off is None else days_off}
    return {"id": 1, "day": day, "meal_id": 1, "setting": json.dumps(setting), "overwritten": False}


def item(kind: str, name: str) -> dict[str, Any]:
    return {"item": name, "weight": 0, "name": name, "type": kind}


def test_parse_month_fixture(lunch_month: Any) -> None:
    days = parse_month(lunch_month["data"])

    assert [d.day for d in days] == [date(2026, 9, 3), date(2026, 9, 8), date(2026, 9, 22)]
    pupusa = days[2]
    assert pupusa.headline == ("Birria and Cheese Pupusa", "Bean and Cheese Pupusa")
    assert [s.title for s in pupusa.sections] == ["Lunch Entree", "Vegetables", "Fruit", "Milk"]
    assert pupusa.sections[0].items == (
        MenuItem(ItemKind.RECIPE, "Birria and Cheese Pupusa"),
        MenuItem(ItemKind.TEXT, "Or"),
        MenuItem(ItemKind.RECIPE, "Bean and Cheese Pupusa"),
    )


def test_parse_month_breakfast_fixture(breakfast_month: Any) -> None:
    days = parse_month(breakfast_month["data"])

    assert days[0].day == date(2026, 10, 1)
    assert days[0].headline == (
        "Apple Cinnamon French Toast",
        "Assorted General Mills Cereal Bowls",
        "Benefit Bars",
    )


def test_parse_month_skips_null_and_days_off() -> None:
    raw = [
        None,
        day_entry("2026-09-04", [], days_off={"status": 1, "description": "Labor Day Weekend"}),
        day_entry("2026-09-05", [item("category", "Lunch Entree"), item("text", "No School")]),
        day_entry("2026-09-08", [item("category", "Lunch Entree"), item("recipe", "Nachos")]),
    ]

    days = parse_month(raw)

    assert [d.day for d in days] == [date(2026, 9, 8)]


def test_parse_month_items_before_first_category() -> None:
    days = parse_month(
        [day_entry("2026-09-08", [item("recipe", "Nachos"), item("category", "Milk"), item("recipe", "1%")])]
    )

    assert days[0].sections == (
        Section(None, (MenuItem(ItemKind.RECIPE, "Nachos"),)),
        Section("Milk", (MenuItem(ItemKind.RECIPE, "1%"),)),
    )
    assert days[0].headline == ("Nachos",)


def test_parse_month_unknown_item_type_raises() -> None:
    with pytest.raises(PayloadError, match="unknown item type 'image'"):
        parse_month([day_entry("2026-09-08", [item("image", "x")])])


@pytest.mark.parametrize("missing", ["day", "setting"])
def test_parse_month_missing_key_raises(missing: str) -> None:
    entry = day_entry("2026-09-08", [item("recipe", "Nachos")])
    del entry[missing]

    with pytest.raises(PayloadError, match=f"missing key '{missing}'"):
        parse_month([entry])


def test_parse_month_invalid_setting_json_raises() -> None:
    entry = day_entry("2026-09-08", [])
    entry["setting"] = "{not json"

    with pytest.raises(PayloadError, match="not valid JSON"):
        parse_month([entry])


def test_parse_month_invalid_date_raises() -> None:
    with pytest.raises(PayloadError, match="invalid date"):
        parse_month([day_entry("2026-13-40", [item("recipe", "Nachos")])])


def test_parse_month_rejects_non_list() -> None:
    with pytest.raises(PayloadError, match="expected a list"):
        parse_month({"day": "2026-09-08"})


def test_name_whitespace_collapsed() -> None:
    days = parse_month([day_entry("2026-09-08", [item("recipe", "  Assorted Seasonal Fresh  Fruit ")])])

    assert days[0].headline == ("Assorted Seasonal Fresh Fruit",)


def test_parse_site(site_payload: Any) -> None:
    site = parse_site(site_payload["data"])

    assert (site.id, site.district, site.name) == (12589, 1265, "Chambers Primary")


def test_parse_site_prefers_custom_name() -> None:
    site = parse_site({"id": 1, "organization_id": 2, "name": "Official", "custom_name": " Custom  Name "})

    assert site.name == "Custom Name"


def test_parse_site_rejects_bool_id() -> None:
    with pytest.raises(PayloadError, match="'id' should be int"):
        parse_site({"id": True, "organization_id": 2, "name": "x"})


def test_parse_site_menus(site_menus_payload: Any) -> None:
    menus = parse_site_menus(site_menus_payload["data"])

    assert [(m.id, m.meal_type) for m in menus] == [(125546, MealType.BREAKFAST), (125549, MealType.LUNCH)]
    assert menus[1].published_months == (date(2026, 9, 1), date(2026, 10, 1))


def test_parse_menu_unknown_meal_type_is_none() -> None:
    menu = parse_menu({"id": 7, "name": "Snack", "meal_type_id": 99, "published_months": []})

    assert menu.meal_type is None


def test_parse_menu_bool_meal_type_is_none() -> None:
    menu = parse_menu({"id": 7, "name": "Odd", "meal_type_id": True, "published_months": []})

    assert menu.meal_type is None


def test_parse_month_duplicate_day_raises() -> None:
    entry = day_entry("2026-09-08", [item("recipe", "Nachos")])

    with pytest.raises(PayloadError, match="duplicate entries for 2026-09-08"):
        parse_month([entry, entry])


def test_control_characters_removed() -> None:
    days = parse_month([day_entry("2026-09-08", [item("recipe", "Nach\x00os\x1b[31m\u200b Bowl\u2028X\r\nY")])])

    assert days[0].headline == ("Nachos[31m Bowl X Y",)


def test_parse_month_nested_setting_too_deep_is_payload_error() -> None:
    entry = day_entry("2026-09-08", [])
    entry["setting"] = "[" * 100_000 + "]" * 100_000

    with pytest.raises(PayloadError):
        parse_month([entry])
