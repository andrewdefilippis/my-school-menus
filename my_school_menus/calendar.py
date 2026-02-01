# vim: ts=4 et

import os
import icalendar
import json
from datetime import datetime, timezone
from . import __meta__

from typing import Iterator, Self

class Calendar(object):
    '''New MSM Calendar interface'''

    def __init__(
            self,
            vendor=None,
            product=None,
            version=None,
            lang=None,
            desc=None,
            name=None,
            tz='UTC',
        ):
        vendor = vendor or 'andrewdefilippis/my-school-menus'
        product = product or os.path.basename(__file__)
        version = version or __meta__.__version__
        lang = lang or 'EN'

        self.cal = icalendar.Calendar()
        self.cal['prodid'] = '//'.join(('-', vendor, f'{product} {version}', lang))
        self.cal['version'] = '2.0'
        if name:
            self.cal['x-wr-calname'] = name
        if tz:
            self.cal['x-wr-timezone'] = tz
        if desc:
            self.cal['x-wr-caldesc'] = desc


    def events(self, menu: json) -> Iterator[icalendar.Event]:
        """
        Generate a list of events from a menu

        :param menu: json menu.

        :return: Iterator of events.
        :rtype: Iterator
        """

        if not menu['data']:
            raise ValueError(f"Missing menu data.")

        now = datetime.now(timezone.utc)
        for entry in menu['data']:
            if not entry:
                continue

            event = icalendar.Event()
            eventuid = f'eventid-{entry["id"]}@myschoolmenus.com'
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
                event.add('uid', eventuid)
                event.add('dtstamp', now)
                event.add('summary', summary)
                event.add('description', description)
                event.add('dtstart', datetime.fromisoformat(entry['day']).date())
                event.add('alarms', [])
                yield event
            except KeyError:
                continue

    def append(self, event):
        self.cal.add_component(event)

    def extend(self, events: list):
        for event in events:
            self.cal.add_component(event)

    def __iadd__(self, event_s) -> Self:
        if isinstance(event_s, icalendar.Event):
            self.append(event_s)
        else:
            self.extend(event_s)
        return self

    def ical(self) -> str:
        """
        Get the menu as an iCal bytes object.

        :param icalendar_calendar: iCalendar calendar.

        :return: Decoded iCal file.
        :rtype: str
        """
        return self.cal.to_ical().decode('utf-8')
