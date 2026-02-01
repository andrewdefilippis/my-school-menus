#!/usr/bin/env -S uv run --script
# vim: ts=4 et
# /// script
# dependencies = [
#   "icalendar",
#   "requests",
# ]
# ///

# This is a revision of the original example that produces a
# single ICS file on stdout containing all months, using the newer
# my_school_menus.calendar interface. This interface is more extensive,
# more correct with respect to iCalendar 2.0, and more "pythonic".

import sys
import os
sys.path.append(os.path.pardir)

import my_school_menus
from my_school_menus.msm_api import Menus
from my_school_menus.calendar import Calendar

DISTRICT_ID = 1272
SITE_ID = 10048
MENU_ID = 98201

def main():
    menus = Menus()
    menu = menus.get(district_id=DISTRICT_ID, menu_id=MENU_ID)
    available_dates = menus.menu_months(menu)

    desc = '\n'.join((
        f'Example calendar.'
        f'',
        f'District: {DISTRICT_ID}',
        f'School: {SITE_ID}',
        f'Menu: {MENU_ID}',
    ))
    cal = Calendar(
        vendor='c13',
        product=os.path.basename(__file__),
        version=my_school_menus.__version__,
        lang=None,
        desc=desc,
        name='Example calendar',
    )

    for date in available_dates:
        datemenu = menus.get(
            district_id=DISTRICT_ID, menu_id=MENU_ID, date=date
        )

        events = cal.events(datemenu)
        cal += events
        sys.stdout.write(cal.ical())

if __name__ == '__main__':
    main()
