from __future__ import annotations

import json
from collections.abc import Iterable
from types import TracebackType
from typing import Any, Self

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .__meta__ import __version__
from .errors import MenusError, NotFoundError, PayloadError, UpstreamError
from .models import (
    DistrictId,
    MealType,
    Menu,
    MenuDay,
    MenuId,
    Site,
    SiteId,
    parse_menu,
    parse_month,
    parse_site,
    parse_site_menus,
)

DEFAULT_BASE_URL = "https://menus.healthepro.com/api"
DEFAULT_CONNECT_TIMEOUT_S = 10.0
DEFAULT_READ_TIMEOUT_S = 30.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
IPV4_SOURCE_ADDRESS = ("0.0.0.0", 0)


class _IPv4Adapter(HTTPAdapter):
    """Bind outgoing sockets to an IPv4 source so only A records are used. Scoped to one session."""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        kwargs["source_address"] = IPV4_SOURCE_ADDRESS
        super().init_poolmanager(*args, **kwargs)


class Client:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
        force_ipv4: bool = False,
        session: requests.Session | None = None,
    ) -> None:
        """A caller-supplied ``session`` is used as-is and left open; its headers, adapters and retries are the
        caller's responsibility, so it cannot be combined with ``force_ipv4``."""
        if session is not None and force_ipv4:
            raise ValueError("force_ipv4 cannot be combined with a caller-supplied session")
        if not base_url.startswith("https://"):
            raise ValueError("base_url must use https://")
        self._base_url = base_url.rstrip("/")
        self._timeout = (connect_timeout_s, read_timeout_s)
        self._owns_session = session is None
        self._session = session if session is not None else self._default_session(force_ipv4)

    @staticmethod
    def _default_session(force_ipv4: bool) -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = f"my-school-menus/{__version__}"
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            backoff_max=10.0,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=False,
            raise_on_status=False,
        )
        adapter = _IPv4Adapter(max_retries=retry) if force_ipv4 else HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        return session

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def site(self, district: DistrictId, site: SiteId) -> Site:
        parsed = parse_site(self._get_data(f"/organizations/{district:d}/sites/{site:d}"))
        if (parsed.district, parsed.id) != (district, site):
            raise PayloadError(f"site {site} in district {district}: response is for a different site")
        return parsed

    def site_menus(self, district: DistrictId, site: SiteId) -> tuple[Menu, ...]:
        return parse_site_menus(self._get_data(f"/organizations/{district:d}/sites/{site:d}/menus"))

    def menu(self, district: DistrictId, menu: MenuId) -> Menu:
        parsed = parse_menu(self._get_data(f"/organizations/{district:d}/menus/{menu:d}"))
        if parsed.id != menu:
            raise PayloadError(f"menu {menu}: response is for a different menu")
        return parsed

    def month(self, district: DistrictId, menu: MenuId, year: int, month: int) -> tuple[MenuDay, ...]:
        path = f"/organizations/{district:d}/menus/{menu:d}/year/{year:d}/month/{month:02d}/date_overwrites"
        return parse_month(self._get_data(path))

    def days(self, district: DistrictId, menu: Menu) -> tuple[MenuDay, ...]:
        """All serving days across the menu's published months; months published without data are skipped."""
        days: list[MenuDay] = []
        for month in menu.published_months:
            try:
                fetched = self.month(district, menu.id, month.year, month.month)
            except NotFoundError:
                continue
            for day in fetched:
                if (day.day.year, day.day.month) != (month.year, month.month):
                    raise PayloadError(
                        f"menu {menu.id} month {month:%Y-%m}: contains {day.day.isoformat()} from another month"
                    )
            days.extend(fetched)
        return tuple(days)

    def find_menu(self, district: DistrictId, site: SiteId, meal: MealType) -> Menu:
        """Resolve the site's current menu for a meal type. Raises if there are zero or several."""
        return select_menu(self.site_menus(district, site), meal, district, site)

    def _get_data(self, path: str) -> object:
        url = f"{self._base_url}{path}"
        try:
            with self._session.get(url, timeout=self._timeout, allow_redirects=False, stream=True) as response:
                if 300 <= response.status_code < 400:
                    raise UpstreamError(f"GET {url} failed: unexpected redirect ({response.status_code})")
                response.raise_for_status()
                content = _read_limited(response, url)
        except requests.RequestException as e:
            raise UpstreamError(f"GET {url} failed: {e}") from e
        try:
            body: object = json.loads(content)
        except (ValueError, RecursionError) as e:
            raise PayloadError(f"GET {url} returned invalid JSON") from e
        if not isinstance(body, dict) or "data" not in body:
            raise PayloadError(f"GET {url} has no 'data' field")
        if not body["data"]:
            raise NotFoundError(f"GET {url} returned no data")
        return body["data"]


def select_menu(menus: Iterable[Menu], meal: MealType, district: DistrictId, site: SiteId) -> Menu:
    """Pick the single menu for ``meal``. Raises NotFoundError if there is none, MenusError if there are several."""
    matches = [m for m in menus if m.meal_type is meal]
    if not matches:
        raise NotFoundError(f"site {site} in district {district} has no {meal.name.lower()} menu")
    if len(matches) > 1:
        candidates = ", ".join(f"{m.id} ({m.name})" for m in matches)
        raise MenusError(
            f"site {site} in district {district} has several {meal.name.lower()} menus: {candidates}; "
            "pass an explicit menu ID"
        )
    return matches[0]


def _read_limited(response: requests.Response, url: str) -> bytes:
    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_RESPONSE_BYTES:
            raise PayloadError(f"GET {url} response exceeds {MAX_RESPONSE_BYTES} bytes")
    return bytes(content)
