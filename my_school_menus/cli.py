from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .__meta__ import __version__
from .calendar import build_calendar, feed_filename
from .client import Client, select_menu
from .errors import MenusError, NotFoundError
from .models import DistrictId, MealType, Menu, MenuId, SiteId

STDOUT = "-"


@dataclass(frozen=True, slots=True)
class Options:
    district: DistrictId
    site: SiteId
    meals: tuple[MealType, ...]  # empty: every meal the school publishes
    menu: MenuId | None
    output: str | None  # a file path or STDOUT; None: write into output_dir
    output_dir: Path
    quiet: bool
    force_ipv4: bool


def _meal(value: str) -> MealType:
    try:
        return MealType[value.upper()]
    except KeyError:
        raise argparse.ArgumentTypeError(f"invalid meal {value!r}") from None


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be positive: {value!r}")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="my-school-menus",
        description="Export Health-e Pro (My School Menus) menus as iCalendar (.ics) feeds.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--district", type=_positive_int, required=True, help="district (organization) ID")
    parser.add_argument("--site", type=_positive_int, required=True, help="school (site) ID")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--meal",
        dest="meals",
        type=_meal,
        action="append",
        metavar="{" + ",".join(m.name.lower() for m in MealType) + "}",
        help="meal to export; repeatable (default: all meals the school publishes)",
    )
    source.add_argument("--menu", type=_positive_int, help="explicit menu ID instead of discovering it by meal")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("-o", "--output", help="output file, or '-' for stdout (only with a single feed)")
    output.add_argument("--output-dir", type=Path, default=Path("."), help="directory for feeds (default: .)")
    parser.add_argument("--quiet", action="store_true", help="do not report written files")
    parser.add_argument("--force-ipv4", action="store_true", help="connect over IPv4 only")
    return parser


def parse_args(argv: Sequence[str] | None) -> Options:
    parser = _parser()
    args = parser.parse_args(argv)
    meals = tuple(dict.fromkeys(args.meals or ()))
    menu = MenuId(args.menu) if args.menu is not None else None
    single_feed = menu is not None or len(meals) == 1
    if args.output is not None and not single_feed:
        parser.error("-o/--output needs exactly one feed: pass a single --meal or --menu")
    return Options(
        district=DistrictId(args.district),
        site=SiteId(args.site),
        meals=meals,
        menu=menu,
        output=args.output,
        output_dir=args.output_dir,
        quiet=args.quiet,
        force_ipv4=args.force_ipv4,
    )


def _write(target: str | Path, content: bytes) -> None:
    if target == STDOUT:
        sys.stdout.buffer.write(content)
        sys.stdout.buffer.flush()
        return
    path = Path(target)
    if path.exists() and not path.is_file():
        raise OSError(f"{path} exists and is not a regular file")
    umask = os.umask(0)
    os.umask(umask)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
            if hasattr(os, "fchmod"):
                os.fchmod(f.fileno(), 0o666 & ~umask)
            else:
                os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _resolve_menus(client: Client, options: Options) -> list[Menu]:
    if options.menu is not None:
        return [client.menu(options.district, options.menu)]
    available = client.site_menus(options.district, options.site)
    if options.meals:
        return [select_menu(available, meal, options.district, options.site) for meal in options.meals]
    menus = []
    for meal in MealType:
        try:
            menus.append(select_menu(available, meal, options.district, options.site))
        except NotFoundError as e:
            print(f"warning: {e}", file=sys.stderr)
    if not menus:
        raise NotFoundError(f"site {options.site} in district {options.district} publishes no menus")
    return menus


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        if options.output is None:
            options.output_dir.mkdir(parents=True, exist_ok=True)
        with Client(force_ipv4=options.force_ipv4) as client:
            site = client.site(options.district, options.site)
            for menu in _resolve_menus(client, options):
                days = client.days(options.district, menu)
                target = (
                    options.output if options.output is not None else options.output_dir / feed_filename(site, menu)
                )
                _write(target, build_calendar(site, menu, days).to_ical())
                if not options.quiet:
                    print(f"wrote {target} ({len(days)} days)", file=sys.stderr)
    except MenusError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: cannot write output: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: internal error ({type(e).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
