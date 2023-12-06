import icalendar
import json
from datetime import datetime


class Calendar:
    @staticmethod
    def events(menu: json) -> list:
        """
        Generate a list of events from a menu

        :param menu: json menu.

        :return: List of events.
        :rtype: list
        """
        event_list = []
        menu_month_calendar = menu['data']['menu_month_calendar']
        if not menu_month_calendar:
            raise ValueError(
                f"Missing menu data."
            )

        for entry in menu_month_calendar:
            if entry is None:
                continue
            event = icalendar.Event()
            description = ''
            summary = ''
            recipe_count = 0
            category_count = 0
            try:
                for item in json.loads(entry['setting'])['current_display']:
                    if item['type'] == 'recipe' and recipe_count == 0:
                        recipe_count += 1
                        summary = f"Lunch: {item['name']}"
                    if item['type'] == 'category' and category_count == 0:
                        category_count += 1
                        description = f"{description}{item['name']}:\n"
                    elif item['type'] == 'category':
                        description = f"{description}\n{item['name']}:\n"
                    else:
                        description = f"{description}{item['name']}\n"
                if summary == '':
                    continue
                event.add('summary', summary)
                event.add('description', description)
                event.add('dtstart', datetime.fromisoformat(entry['day']).date())
                event.add('alarms', [])
                event_list.append(event)
            except KeyError:
                continue

        return event_list

    @staticmethod
    def calendar(cal_events: list) -> icalendar.Calendar:
        """
        Generate a calendar from a menu

        :param cal_events: list of events.

        :return: iCalendar calendar.
        :rtype: icalendar.Calendar
        """
        cal = icalendar.Calendar()
        for event in cal_events:
            cal.add_component(event)
        return cal

    @staticmethod
    def ical(icalendar_calendar: icalendar.Calendar) -> str:
        """
        Get the menu as an iCal bytes object.

        :param icalendar_calendar: iCalendar calendar.

        :return: Decoded iCal file.
        :rtype: str
        """
        return icalendar_calendar.to_ical().decode('utf-8')
