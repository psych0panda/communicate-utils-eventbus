class EventBusError(Exception):
    pass


class InvalidRoute(EventBusError):
    pass


class InvalidProvider(EventBusError):
    pass


class EcosystemException(Exception):
    """Base exception class for all ecosystem exceptions."""
    error_code: str = "UNKNOWN_ERROR"
    origin: str = "unknown"
    data: dict = {}

    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.data = kwargs


class ApplicationError(EcosystemException):
    """Exception raised when application encounters an error."""
    error_code = "APPLICATION_ERROR"
    origin = "application"


class ExceptionConvertor:
    """Base class for exception convertors."""
    def __init__(self, exception: Exception):
        self.exception = exception

    def convert(self, target_exception: type) -> EcosystemException:
        """Convert exception to target exception type."""
        return target_exception(str(self.exception))


class GenericExceptionConvertor(ExceptionConvertor):
    """Generic exception convertor that preserves the original message."""
    pass
