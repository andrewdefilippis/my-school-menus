class MenusError(Exception):
    """Base class for all my_school_menus errors."""


class UpstreamError(MenusError):
    """The menus service returned a non-2xx status or could not be reached."""


class NotFoundError(MenusError):
    """The service answered but the requested resource has no data."""


class PayloadError(MenusError):
    """The service returned data in a shape this library does not understand."""
