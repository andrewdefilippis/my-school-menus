import requests
from datetime import datetime
from dataclasses import dataclass

DOMAIN = 'myschoolmenus.com'


@dataclass
class RequestParams:
    path: str = None
    headers: dict = None
    exception_message: str = None


class Request:
    def __init__(self):
        pass

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
        response = requests.get(url=url, headers=params.headers)
        if response.status_code != 200:
            raise ValueError(
                f"Endpoint returned status code {response.status_code}: {response.reason}"
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
        self.path = '/api/public/menus'

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
            path = self.path + f"/?site={site_id}"
        elif menu_id:
            path = self.path + f"/{menu_id}"
            if date:
                path = path + f"?menu_month={date.strftime('%Y-%m-01')}"
        else:
            path = self.path
        return Request.get(RequestParams(
            path=path,
            headers={'x-district': str(district_id)},
            exception_message=exception_message + f", menu {menu_id}{f', and date {date}' if date else ''}" if menu_id else exception_message
        ))

    @staticmethod
    def menu_month(menu: dict) -> datetime.date:
        """
        Get month for menu in date format.

        :param menu: Menu to get date.

        :return: List of months available for a menu.
        :rtype: datetime.date
        """

        return datetime.fromisoformat(menu['data']['menu_month'])

    @staticmethod
    def menu_months(menu: dict) -> list[datetime.date]:
        """
        Get a list of months with available menus.  Does not include all available prior months.

        :param menu: Menu to get months.

        :return: List of months available for a menu.
        :rtype: list
        """

        return [datetime.fromisoformat(date) for date in menu['data']['menu_info']['menu_months_array']]


class Organizations:
    def __init__(self):
        self.path = '/api/public/organizations'

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


class Settings:
    def __init__(self):
        self.path = '/api/settings'

    def get(self) -> dict:
        """
        Get settings data.

        :return: Settings data.
        :rtype: dict
        """

        return Request.get(RequestParams(
            path=self.path,
            exception_message=f"No settings found"
        ))


class Sites:
    def __init__(self):
        self.path = '/api/public/sites'

    def get(self, district_id: int, site_id: int = None) -> dict:
        """
        Get a list of sites by district ID.

        :param district_id: District ID.
        :param site_id: Site ID.

        :return: District sites.
        :rtype: dict
        """

        return Request.get(RequestParams(
            path=self.path + f"/{site_id}" if site_id else self.path,
            headers={'x-district': str(district_id)},
            exception_message=f"No sites found for district {district_id}" + f" and site {site_id}" if site_id else ""
        ))


class Statics:
    def __init__(self):
        self.path = '/api/statics'

    def get(self, organization_id: str = None) -> dict:
        """
        Get statics data.

        :return: Statics data.
        :rtype: dict
        """

        return Request.get(RequestParams(
            path=self.path + f"?organization={organization_id}" if organization_id else self.path,
            exception_message=f"No statics found"
        ))
