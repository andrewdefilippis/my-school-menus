from my_school_menus.api import Menus
from my_school_menus.calendar import Calendar
import os

DISTRICT_ID = 1265
SITE_ID = 12589
MENU_ID = 76222
FILE_SUFFIX = 'school-lunch-calendar.ics'


def main():
    menus = Menus()
    menu = menus.get(district_id=DISTRICT_ID, menu_id=MENU_ID)
    available_dates = menus.menu_months(menu)
    for date in available_dates:
        filepath = f"{os.path.dirname(os.path.realpath(__file__))}/{date.year}-{date.month:02}-{FILE_SUFFIX}"
        calendar_menu = menu if menus.menu_month(menu) == date else menus.get(
            district_id=DISTRICT_ID, menu_id=MENU_ID, date=date
        )
        cal = Calendar()
        events = cal.events(calendar_menu)
        calendar = cal.calendar(events)
        ical = cal.ical(calendar)
        print(f"Writing calendar file to {filepath}")
        with open(filepath, 'w') as f:
            f.write(ical)
        print('Calendar file written successfully!')


if __name__ == '__main__':
    main()
