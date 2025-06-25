class EventBusError(Exception):
    pass


class InvalidRoute(EventBusError):
    pass


class InvalidProvider(EventBusError):
    pass


class ApplicationError(EventBusError):
    pass
