import requests
from datetime import datetime
from dataclasses import dataclass
import socket

# Force IPv4 to avoid IPv6 timeout issues with this API
_orig_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_ipv4_only

DOMAIN = 'menus.healthepro.com'


@dataclass
class RequestParams:
    path: str = None
    headers: dict = None
    exception_message: str = None


class Request:
    @staticmethod
    def url(path) -> str:
        """
        Get the URL for the API.

        :return: URL for the API.
        :rtype: str
        """

        return f"https://{DOMAIN}{path}"

    @staticmethod
    def get(params: RequestParams) -> dict:
        """
        Get a response from the API.

        :param params: Request parameters.

        :return: Response from API.
        :rtype: dict
        """

        url = f"{Request.url(params.path)}"
        response = requests.get(url=url, headers=params.headers, timeout=30)
        if response.status_code != 200:
            raise ValueError(
                f"Endpoint {url} returned status code {response.status_code}: {response.reason}"
            )
        try:
            json = response.json()
            if not json['data']:
                raise ValueError(
                    params.exception_message
                )
        except requests.exceptions.JSONDecodeError:
            raise ValueError(
                f"Unable to decode JSON response"
            )
        return response.json()


class Menus:
    def __init__(self):
        self.path = '/api/organizations'

    def get(self, district_id: int, site_id: int = None, menu_id: int = None, date: datetime.date = None) -> dict:
        """
        Get a menu by district ID, menu ID, and optionally a date.

        :param district_id: District ID.
        :param site_id: Site ID.
        :param menu_id: Menu ID.
        :param date: Date of menu.

        :return: District menu.
        :rtype: dict
        """

        exception_message = f"No menu found for district {district_id}"
        if site_id:
            path = self.path + f"/{district_id}/sites/{site_id}"
        elif menu_id:
            path = self.path + f"/{district_id}/menus/{menu_id}"
            if date:
                path = path + f"/year/{date.strftime('%Y')}/month/{date.strftime('%m')}/date_overwrites"
        else:
            path = self.path
        return Request.get(RequestParams(
            path=path,
            exception_message=exception_message + f", menu {menu_id}{f', and date {date}' if date else ''}" if menu_id else exception_message
        ))

    @staticmethod
    def menu_months(menu: dict) -> list[datetime.date]:
        """
        Get a list of months with available menus.  Does not include all available prior months.

        :param menu: Menu to get months.

        :return: List of months available for a menu.
        :rtype: list
        """

        return [datetime.fromisoformat(date) for date in menu['data']['published_months']]


class Organizations:
    def __init__(self):
        self.path = '/api/organizations'

    def get(self, organization_id: int = None) -> dict:
        """
        Get an organization by organization ID, or return all organizations.

        :param organization_id: Organization ID.

        :return: District organization.
        :rtype: dict
        """

        return Request.get(RequestParams(
            path=self.path + f"/{organization_id}" if organization_id else self.path,
            exception_message=f"No organization found for organization {organization_id}" if organization_id else ""
        ))


class Sites:
    def __init__(self):
        self.path = 'api/organizations'

    def get(self, district_id: int, site_id: int) -> dict:
        """
        Get a site for a given district.

        :param district_id: District ID.
        :param site_id: Site ID.

        :return: District site.
        :rtype: dict
        """

        return Request.get(RequestParams(
            path=self.path + f"/{district_id}/sites/{site_id}",
            exception_message=f"No site found for district {district_id}" + f" and site {site_id}"
        ))
