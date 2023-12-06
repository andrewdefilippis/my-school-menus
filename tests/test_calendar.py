from my_school_menus.calendar import Calendar
from unittest import TestCase


def menu_data():
    return {'data': {'menu_month_calendar': [
        {'setting': '{"current_display":[{"type":"recipe","recipe_name":"Chicken Nuggets"}]}'}
    ]}}


class Test(TestCase):
    def test_events_missing_menu_data(self):
        with self.assertRaises(ValueError):
            Calendar.events({'data': {'menu_month_calendar': []}})

    def test_events(self):
        Calendar.events(menu_data())

    def test_calendar(self):
        event_data = Calendar.events(menu_data())
        Calendar.calendar(event_data)

    def test_ical(self):
        event_data = Calendar.events(menu_data())
        icalendar_calendar = Calendar.calendar(event_data)
        Calendar.ical(icalendar_calendar)
