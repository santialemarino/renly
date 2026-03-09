# Domain errors, raised by services; the HTTP layer maps them to status codes and responses.


class NotFoundError(Exception):
    """Resource not found or not owned by the current user. Mapped to 404 by the API."""

    def __init__(self, message: str = "Not found") -> None:
        self.message = message
        super().__init__(message)
