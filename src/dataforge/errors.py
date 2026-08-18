class DataForgeError(Exception):
    """Base exception for expected application failures."""


class NotFoundError(DataForgeError):
    """Requested domain object does not exist."""


class ValidationError(DataForgeError):
    """Input or state transition is invalid."""


class AuthenticationError(DataForgeError):
    """A serving request did not provide a valid application credential."""


class EngineUnavailableError(DataForgeError):
    """The requested processing engine cannot be loaded."""
