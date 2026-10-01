import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def lunch_month() -> Any:
    return load_fixture("lunch_2026_09.json")


@pytest.fixture
def breakfast_month() -> Any:
    return load_fixture("breakfast_2026_10.json")


@pytest.fixture
def site_payload() -> Any:
    return load_fixture("site.json")


@pytest.fixture
def site_menus_payload() -> Any:
    return load_fixture("site_menus.json")
