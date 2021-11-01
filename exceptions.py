"""
Application Exceptions
"""


class ManagedObjectNotFoundError(Exception):
    """
    APIC REST managed object not found error.
    """

    pass

class CachedObjectNotFoundError(Exception):
    """
    Application cached object not found error.
    """

    pass
