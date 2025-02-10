import pytest
from my_school_menus.msm_api import Menus
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
    return MockResponse({"data":{"id":12345,"custom_name":"Lunch Menu K-8",
                                 "name":"Lunch Menu K-8","days_in_week":5,
                                 "first_day_of_week":1,"public_name":"Lunch Menu K-8",
                                 "use_menu_name":True,"published_months":["2025-02-01"]},
                                 "message":None}, 200)
#

@mock.patch('requests.get', side_effect=mocked_requests_menus_get_no_records_found)
def test_get_menu_non_existent_ids(mock_get):
    with pytest.raises(ValueError):
        Menus().get(0, 0)


@mock.patch('requests.get', side_effect=mocked_requests_menus_get_successful)
def test_get_menu_successful_ids(mock_get):
    menu_info = Menus().get(1337, 12345)
    assert menu_info['data']['id'] == 12345
