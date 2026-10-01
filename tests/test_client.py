import subprocess
import sys
from typing import Any

import pytest
import requests
import responses

from my_school_menus.client import DEFAULT_BASE_URL, IPV4_SOURCE_ADDRESS, MAX_RESPONSE_BYTES, Client, _IPv4Adapter
from my_school_menus.errors import MenusError, NotFoundError, PayloadError, UpstreamError
from my_school_menus.models import DistrictId, MealType, MenuDay, MenuId, SiteId, parse_menu

D = DistrictId(1265)
S = SiteId(12589)
ORG = f"{DEFAULT_BASE_URL}/organizations/1265"


def no_retry_client() -> Client:
    client = Client()
    for adapter in client._session.adapters.values():
        adapter.max_retries.total = 0  # type: ignore[attr-defined]
    return client


@responses.activate
def test_client_urls(site_payload: Any, site_menus_payload: Any, lunch_month: Any) -> None:
    responses.get(f"{ORG}/sites/12589", json=site_payload)
    responses.get(f"{ORG}/sites/12589/menus", json=site_menus_payload)
    responses.get(f"{ORG}/menus/125549", json={"data": site_menus_payload["data"][1]})
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", json=lunch_month)

    with Client() as client:
        assert client.site(D, S).name == "Chambers Primary"
        assert len(client.site_menus(D, S)) == 2
        assert client.menu(D, MenuId(125549)).meal_type is MealType.LUNCH
        assert len(client.month(D, MenuId(125549), 2026, 9)) == 3

    assert [c.request.url for c in responses.calls] == [
        f"{ORG}/sites/12589",
        f"{ORG}/sites/12589/menus",
        f"{ORG}/menus/125549",
        f"{ORG}/menus/125549/year/2026/month/09/date_overwrites",
    ]
    assert responses.calls[0].request.headers["User-Agent"].startswith("my-school-menus/")


@responses.activate
@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"status": 404}, UpstreamError, "404"),
        ({"status": 500}, UpstreamError, "500"),
        ({"body": "<html>"}, PayloadError, "invalid JSON"),
        ({"json": ["no", "data"]}, PayloadError, "no 'data' field"),
        ({"json": {"data": None}}, NotFoundError, "returned no data"),
        ({"json": {"data": []}}, NotFoundError, "returned no data"),
    ],
)
def test_client_errors(kwargs: dict[str, Any], error: type[Exception], match: str) -> None:
    responses.get(f"{ORG}/sites/12589", **kwargs)

    with no_retry_client() as client, pytest.raises(error, match=match):
        client.site(D, S)


@responses.activate
def test_client_connection_error_is_upstream_error() -> None:
    with no_retry_client() as client, pytest.raises(UpstreamError, match="failed"):
        client.site(D, S)


@responses.activate
def test_client_retries(site_payload: Any) -> None:
    responses.get(f"{ORG}/sites/12589", status=503)
    responses.get(f"{ORG}/sites/12589", json=site_payload)
    client = Client()
    for adapter in client._session.adapters.values():
        adapter.max_retries.backoff_factor = 0  # type: ignore[attr-defined]

    with client:
        assert client.site(D, S).id == 12589

    assert len(responses.calls) == 2


@responses.activate
@pytest.mark.parametrize(("meal", "menu_id"), [(MealType.LUNCH, 125549), (MealType.BREAKFAST, 125546)])
def test_find_menu(site_menus_payload: Any, meal: MealType, menu_id: int) -> None:
    responses.get(f"{ORG}/sites/12589/menus", json=site_menus_payload)

    with Client() as client:
        assert client.find_menu(D, S, meal).id == menu_id


@responses.activate
def test_find_menu_none(site_menus_payload: Any) -> None:
    responses.get(f"{ORG}/sites/12589/menus", json={"data": [site_menus_payload["data"][1]]})

    with Client() as client, pytest.raises(NotFoundError, match="no breakfast menu"):
        client.find_menu(D, S, MealType.BREAKFAST)


@responses.activate
def test_find_menu_several(site_menus_payload: Any) -> None:
    lunch = site_menus_payload["data"][1]
    responses.get(f"{ORG}/sites/12589/menus", json={"data": [lunch, {**lunch, "id": 1, "name": "Other Lunch"}]})

    with Client() as client, pytest.raises(MenusError, match=r"several lunch menus: 125549 .*, 1 \(Other Lunch\)"):
        client.find_menu(D, S, MealType.LUNCH)


def test_force_ipv4_adapter_binds_ipv4_source() -> None:
    with Client(force_ipv4=True) as client:
        adapter = client._session.get_adapter("https://menus.healthepro.com/")
        assert isinstance(adapter, _IPv4Adapter)
        assert adapter.poolmanager.connection_pool_kw["source_address"] == IPV4_SOURCE_ADDRESS

    with Client() as client:
        assert not isinstance(client._session.get_adapter("https://menus.healthepro.com/"), _IPv4Adapter)


def test_import_has_no_side_effects() -> None:
    code = (
        "import socket; before = socket.getaddrinfo; "
        "import my_school_menus, my_school_menus.client, my_school_menus.cli; "
        "assert socket.getaddrinfo is before"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@responses.activate
def test_days_skips_empty_months(site_menus_payload: Any, lunch_month: Any) -> None:
    menu = parse_menu(site_menus_payload["data"][1])
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", json=lunch_month)
    responses.get(f"{ORG}/menus/125549/year/2026/month/10/date_overwrites", json={"data": None})

    with Client() as client:
        days: tuple[MenuDay, ...] = client.days(D, menu)

    assert [d.day.isoformat() for d in days] == ["2026-09-03", "2026-09-08", "2026-09-22"]


@responses.activate
def test_days_propagates_other_errors(site_menus_payload: Any) -> None:
    menu = parse_menu(site_menus_payload["data"][1])
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", status=500)

    with no_retry_client() as client, pytest.raises(UpstreamError):
        client.days(D, menu)


@responses.activate
def test_injected_session_is_not_modified_or_closed(site_payload: Any) -> None:
    responses.get(f"{ORG}/sites/12589", json=site_payload)
    session = requests.Session()
    session.headers["User-Agent"] = "caller/1.0"
    adapter = session.get_adapter("https://menus.healthepro.com/")

    with Client(session=session) as client:
        client.site(D, S)

    assert session.headers["User-Agent"] == "caller/1.0"
    assert session.get_adapter("https://menus.healthepro.com/") is adapter
    assert responses.calls[0].request.headers["User-Agent"] == "caller/1.0"
    closed = []
    session.close = lambda: closed.append(True)  # type: ignore[method-assign]
    Client(session=session).close()
    assert closed == []


def test_injected_session_rejects_force_ipv4() -> None:
    with pytest.raises(ValueError, match="force_ipv4"):
        Client(session=requests.Session(), force_ipv4=True)


def test_owned_session_is_closed() -> None:
    client = Client()
    closed = []
    client._session.close = lambda: closed.append(True)  # type: ignore[method-assign]

    client.close()

    assert closed == [True]


@responses.activate
@pytest.mark.parametrize("location", ["http://evil.example/x", "https://menus.healthepro.com/elsewhere"])
def test_redirects_are_rejected(location: str) -> None:
    responses.get(f"{ORG}/sites/12589", status=302, headers={"Location": location})
    responses.get(location, json={"data": {"id": 12589, "organization_id": 1265, "name": "Spoofed"}})

    with no_retry_client() as client, pytest.raises(UpstreamError, match="unexpected redirect"):
        client.site(D, S)

    assert len(responses.calls) == 1


def test_base_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="https"):
        Client(base_url="http://menus.healthepro.com/api")


@responses.activate
def test_oversized_response_rejected() -> None:
    responses.get(f"{ORG}/sites/12589", body=b" " * (MAX_RESPONSE_BYTES + 1), content_type="application/json")

    with no_retry_client() as client, pytest.raises(PayloadError, match="exceeds"):
        client.site(D, S)


@responses.activate
@pytest.mark.parametrize(
    "body",
    ["[" * 100_000 + "]" * 100_000, '{"data": ' + "9" * 5000 + "}"],
    ids=["deep-nesting", "huge-int"],
)
def test_hostile_json_is_payload_error(body: str) -> None:
    """Depending on the Python version these fail to decode or decode to the wrong shape; never a crash."""
    responses.get(f"{ORG}/sites/12589", body=body, content_type="application/json")

    with no_retry_client() as client, pytest.raises(PayloadError):
        client.site(D, S)


@responses.activate
@pytest.mark.parametrize("override", [{"id": 1}, {"organization_id": 1}])
def test_site_response_must_match_request(site_payload: Any, override: dict[str, int]) -> None:
    responses.get(f"{ORG}/sites/12589", json={"data": {**site_payload["data"], **override}})

    with Client() as client, pytest.raises(PayloadError, match="different site"):
        client.site(D, S)


@responses.activate
def test_menu_response_must_match_request(site_menus_payload: Any) -> None:
    responses.get(f"{ORG}/menus/125549", json={"data": site_menus_payload["data"][0]})

    with Client() as client, pytest.raises(PayloadError, match="different menu"):
        client.menu(D, MenuId(125549))


def test_retry_does_not_honor_retry_after() -> None:
    with Client() as client:
        retry = client._session.get_adapter("https://menus.healthepro.com/").max_retries

    assert retry.respect_retry_after_header is False
    assert retry.backoff_max == 10.0
    assert client._timeout == (10.0, 30.0)


@responses.activate
def test_3xx_without_location_rejected(site_payload: Any) -> None:
    responses.get(f"{ORG}/sites/12589", status=300, json=site_payload)

    with no_retry_client() as client, pytest.raises(UpstreamError, match=r"unexpected redirect \(300\)"):
        client.site(D, S)


@responses.activate
def test_days_rejects_day_outside_requested_month(site_menus_payload: Any, lunch_month: Any) -> None:
    menu = parse_menu(site_menus_payload["data"][1])
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", json=lunch_month)
    responses.get(f"{ORG}/menus/125549/year/2026/month/10/date_overwrites", json=lunch_month)

    with Client() as client, pytest.raises(PayloadError, match="month 2026-10: contains 2026-09-03 from another month"):
        client.days(D, menu)
