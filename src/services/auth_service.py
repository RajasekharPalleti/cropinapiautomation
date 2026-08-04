from src.core.auth_manager import AuthManager
from src.core.response_wrapper import ApiResponse
from src.core.session_context import SessionContext


class AuthService:
    """Test-facing wrapper around AuthManager, kept separate so tests never touch
    the underlying HTTP session directly."""

    def __init__(self, auth_manager: AuthManager):
        self._auth_manager = auth_manager

    def request_token(self, token_request: dict) -> ApiResponse:
        """Returns the raw response, for tests asserting status codes/schema directly."""
        return self._auth_manager.request_token(token_request)

    def generate_token(self, token_request: dict) -> SessionContext:
        """Requests a token and stores it on the session for reuse by other services."""
        return self._auth_manager.generate_token(token_request)
