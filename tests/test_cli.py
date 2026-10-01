import os
import stat
from pathlib import Path
from typing import Any

import icalendar
import pytest
import responses

from my_school_menus.cli import _write, main
from my_school_menus.client import DEFAULT_BASE_URL

ORG = f"{DEFAULT_BASE_URL}/organizations/1265"
ARGS = ["--district", "1265", "--site", "12589"]


def mock_school(site_payload: Any, site_menus_payload: Any, lunch_month: Any, breakfast_month: Any) -> None:
    responses.get(f"{ORG}/sites/12589", json=site_payload)
    responses.get(f"{ORG}/sites/12589/menus", json=site_menus_payload)
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", json=lunch_month)
    responses.get(f"{ORG}/menus/125549/year/2026/month/10/date_overwrites", json={"data": None})
    responses.get(f"{ORG}/menus/125546/year/2026/month/09/date_overwrites", json={"data": []})
    responses.get(f"{ORG}/menus/125546/year/2026/month/10/date_overwrites", json=breakfast_month)


def events(path: Path) -> list[icalendar.Event]:
    return list(icalendar.Calendar.from_ical(path.read_bytes()).walk("VEVENT"))


@responses.activate
def test_cli_end_to_end(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--output-dir", str(tmp_path)]) == 0

    assert sorted(p.name for p in tmp_path.iterdir()) == ["1265-12589-breakfast.ics", "1265-12589-lunch.ics"]
    lunch = events(tmp_path / "1265-12589-lunch.ics")
    breakfast = events(tmp_path / "1265-12589-breakfast.ics")
    assert len(lunch) == 3
    assert len(breakfast) == 3
    assert lunch[0]["SUMMARY"] == "Chambers Primary Lunch: Crispy Chicken Nuggets"
    assert breakfast[0]["SUMMARY"].startswith("Chambers Primary Breakfast: ")
    assert "wrote" in capsys.readouterr().err


@responses.activate
def test_cli_single_meal_to_file(
    tmp_path: Path, site_payload: Any, site_menus_payload: Any, lunch_month: Any, breakfast_month: Any
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)
    out = tmp_path / "lunch.ics"

    assert main([*ARGS, "--meal", "lunch", "-o", str(out)]) == 0

    assert [p.name for p in tmp_path.iterdir()] == ["lunch.ics"]
    assert len(events(out)) == 3


@responses.activate
def test_cli_stdout(
    capsysbinary: pytest.CaptureFixture[bytes],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--meal", "lunch", "-o", "-", "--quiet"]) == 0

    captured = capsysbinary.readouterr()
    assert captured.out.startswith(b"BEGIN:VCALENDAR\r\n")
    assert captured.err == b""


@responses.activate
def test_cli_explicit_menu(
    tmp_path: Path, site_payload: Any, site_menus_payload: Any, lunch_month: Any, breakfast_month: Any
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)
    responses.get(f"{ORG}/menus/125549", json={"data": site_menus_payload["data"][1]})

    assert main([*ARGS, "--menu", "125549", "--output-dir", str(tmp_path), "--quiet"]) == 0

    assert [p.name for p in tmp_path.iterdir()] == ["1265-12589-lunch.ics"]


@responses.activate
def test_cli_meal_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, {"data": [site_menus_payload["data"][1]]}, lunch_month, breakfast_month)

    assert main([*ARGS, "--output-dir", str(tmp_path), "--quiet"]) == 0
    assert [p.name for p in tmp_path.iterdir()] == ["1265-12589-lunch.ics"]
    assert "warning: site 12589 in district 1265 has no breakfast menu" in capsys.readouterr().err

    assert main([*ARGS, "--meal", "breakfast", "--output-dir", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "error: site 12589 in district 1265 has no breakfast menu\n"


@responses.activate
def test_cli_creates_output_dir(
    tmp_path: Path, site_payload: Any, site_menus_payload: Any, lunch_month: Any, breakfast_month: Any
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)
    out_dir = tmp_path / "nested" / "feeds"

    assert main([*ARGS, "--output-dir", str(out_dir), "--quiet"]) == 0

    assert sorted(p.name for p in out_dir.iterdir()) == ["1265-12589-breakfast.ics", "1265-12589-lunch.ics"]


@responses.activate
def test_cli_unwritable_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--meal", "lunch", "-o", str(tmp_path / "missing" / "lunch.ics")]) == 1

    assert capsys.readouterr().err.startswith("error: cannot write output: ")


@responses.activate
def test_cli_upstream_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    responses.get(f"{ORG}/sites/12589", status=404)

    assert main([*ARGS, "--output-dir", str(tmp_path)]) == 1

    err = capsys.readouterr().err
    assert err.startswith("error: GET ") and err.count("\n") == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "extra",
    [
        ["-o", "x.ics"],
        ["--meal", "lunch", "--meal", "breakfast", "-o", "x.ics"],
        ["--menu", "1", "--meal", "lunch"],
        ["--meal", "dinner"],
        ["--meal", "lunch", "-o", "x.ics", "--output-dir", "d"],
    ],
)
def test_cli_output_conflicts(extra: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([*ARGS, *extra])
    assert exc.value.code == 2


@pytest.mark.parametrize("bad", ["0", "-5", "12a", "../1"])
def test_cli_rejects_non_positive_ids(bad: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--district", bad, "--site", "12589"])
    assert exc.value.code == 2


@responses.activate
def test_cli_quiet_prints_nothing_on_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--output-dir", str(tmp_path), "--quiet"]) == 0

    assert capsys.readouterr() == ("", "")


@responses.activate
def test_cli_fetches_site_menus_once(
    tmp_path: Path, site_payload: Any, site_menus_payload: Any, lunch_month: Any, breakfast_month: Any
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--output-dir", str(tmp_path), "--quiet"]) == 0

    assert sum(c.request.url == f"{ORG}/sites/12589/menus" for c in responses.calls) == 1


@responses.activate
def test_cli_partial_failure_keeps_written_feeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], site_payload: Any, site_menus_payload: Any, lunch_month: Any
) -> None:
    responses.get(f"{ORG}/sites/12589", json=site_payload)
    responses.get(f"{ORG}/sites/12589/menus", json=site_menus_payload)
    responses.get(f"{ORG}/menus/125546/year/2026/month/09/date_overwrites", status=404)
    responses.get(f"{ORG}/menus/125549/year/2026/month/09/date_overwrites", json=lunch_month)
    responses.get(f"{ORG}/menus/125549/year/2026/month/10/date_overwrites", json={"data": None})

    assert main([*ARGS, "--meal", "lunch", "--meal", "breakfast", "--output-dir", str(tmp_path), "--quiet"]) == 1

    assert [p.name for p in tmp_path.iterdir()] == ["1265-12589-lunch.ics"]
    assert capsys.readouterr().err.startswith("error: GET ")


@responses.activate
def test_cli_duplicate_meal_written_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    site_payload: Any,
    site_menus_payload: Any,
    lunch_month: Any,
    breakfast_month: Any,
) -> None:
    mock_school(site_payload, site_menus_payload, lunch_month, breakfast_month)

    assert main([*ARGS, "--meal", "lunch", "--meal", "lunch", "--output-dir", str(tmp_path)]) == 0

    assert capsys.readouterr().err.count("wrote ") == 1


def test_write_failure_removes_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_replace(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("my_school_menus.cli.os.replace", fail_replace)

    with pytest.raises(OSError, match="disk full"):
        _write(tmp_path / "lunch.ics", b"BEGIN:VCALENDAR")

    assert list(tmp_path.iterdir()) == []


def test_write_respects_umask(tmp_path: Path) -> None:
    previous = os.umask(0o077)
    try:
        _write(tmp_path / "lunch.ics", b"x")
    finally:
        os.umask(previous)

    assert stat.S_IMODE((tmp_path / "lunch.ics").stat().st_mode) == 0o600


def test_write_refuses_non_regular_target(tmp_path: Path) -> None:
    (tmp_path / "dir.ics").mkdir()

    with pytest.raises(OSError, match="not a regular file"):
        _write(tmp_path / "dir.ics", b"x")


@responses.activate
def test_cli_unexpected_error_is_generic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, site_payload: Any
) -> None:
    responses.get(f"{ORG}/sites/12589", json=site_payload)

    def boom(*args: object) -> None:
        raise RuntimeError("Chambers Primary secret detail")

    monkeypatch.setattr("my_school_menus.cli._resolve_menus", boom)

    assert main([*ARGS, "--output-dir", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "error: internal error (RuntimeError)\n"
