from __future__ import annotations

"""
Application-specific exceptions.

These are raised by services and caught by FastAPI exception handlers
to produce consistent, well-structured error responses.

Using typed exceptions instead of raw HTTPExceptions keeps business logic
decoupled from the HTTP layer — services don't need to know about status codes.
"""


class SwingDoctorError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "An unexpected error occurred") -> None:
        self.message = message
        super().__init__(self.message)


# ── Auth errors ──

class AuthenticationError(SwingDoctorError):
    """Invalid credentials, expired token, etc."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class AuthorizationError(SwingDoctorError):
    """User lacks permission for the requested action."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message)


# ── Resource errors ──

class NotFoundError(SwingDoctorError):
    """Requested resource does not exist."""

    def __init__(self, resource: str = "Resource", identifier: str = "") -> None:
        detail = f"{resource} not found" if not identifier else f"{resource} '{identifier}' not found"
        super().__init__(detail)


class ConflictError(SwingDoctorError):
    """Resource already exists (duplicate email, duplicate session file, etc.)."""

    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message)


class ValidationError(SwingDoctorError):
    """Business rule validation failed (not Pydantic schema validation)."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(message)


# ── Subscription errors ──

class SubscriptionRequiredError(SwingDoctorError):
    """Feature requires a paid subscription tier."""

    def __init__(self, required_tier: str = "pro", message: str | None = None) -> None:
        self.required_tier = required_tier
        super().__init__(message or f"This feature requires a {required_tier} subscription")


# ── Parser errors ──

class ParseError(SwingDoctorError):
    """CSV file could not be parsed (unrecognized format, corrupt data)."""

    def __init__(self, message: str = "Unable to parse file") -> None:
        super().__init__(message)


class UnsupportedFormatError(ParseError):
    """CSV format not recognized as any supported launch monitor export."""

    def __init__(self, message: str = "Unrecognized file format") -> None:
        super().__init__(message)
