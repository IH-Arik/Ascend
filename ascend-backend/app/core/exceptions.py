"""Application exception types."""


class AscendBaseError(Exception):
    """Base exception for domain and application errors."""


class ConfigurationError(AscendBaseError):
    """Raised when required configuration is missing or invalid."""
