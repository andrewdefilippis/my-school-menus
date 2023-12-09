import pytest
from my_school_menus.api import Menus
from unittest import mock


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


def mocked_requests_menus_get_no_records_found(*args, **kwargs):
    return MockResponse({'data': [], 'message': 'No records found.'}, 200)


def mocked_requests_menus_get_successful(*args, **kwargs):
    return MockResponse({'data': {'menu_info': {'id': 123456, 'menu_title': 'K-7 Lunch Menu', 'public': True,
                                                'published_at': '2023-11-28 14:31:22+00', 'unpublished_at': None,
                                                'menu_avatar_id': None, 'menu_id': 12345, 'organization_id': 1337,
                                                'name': 'K-7 Lunch Menu', 'days_in_week': 5, 'first_day_of_week': 1,
                                                'cycle_days': 15, 'start_date': '2023-08-28', 'end_date': '2024-06-21',
                                                'meal_type': 'Lunch', 'menu_months': '{2023-11-01,2023-12-01}',
                                                'menu_months_array': ['2023-11-01', '2023-12-01'], 'avatar_name': None,
                                                'avatar_url': None, 'avatar_alt': None, 'published_to_public': 1,
                                                'vegetable_category_ids': [3, 5, 7, 8, 9, 13, 15, 17],
                                                'fruit_category_ids': [2, 6], 'entree_category_ids': [1, 11, 93]},
                                  'menu_month': '', 'menu_month_calendar': []}}, 200)


@mock.patch('requests.get', side_effect=mocked_requests_menus_get_no_records_found)
def test_get_menu_non_existent_ids(mock_get):
    with pytest.raises(ValueError):
        Menus().get(0, 0)


@mock.patch('requests.get', side_effect=mocked_requests_menus_get_successful)
def test_get_menu_successful_ids(mock_get):
    menu_info = Menus().get(1337, 12345)
    assert menu_info['data']['menu_info']['menu_id'] == 12345
