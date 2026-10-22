"""Auth provider abstraction.

Endpoints depend only on `get_current_user()`; token verification is
delegated to the active AuthProvider. Adding LDAP/OIDC later means one new
provider class plus a branch in `get_auth_provider()`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    """Verified identity extracted from an access token."""

    email: str
    user_id: int | None = None  # local auth: our own primary key
    external_id: str | None = None  # external IdP subject (Supabase user id)


class InvalidTokenError(Exception):
    pass


class AuthProvider(ABC):
    name: str

    @abstractmethod
    def verify_token(self, token: str) -> Identity:
        """Return the identity an access token proves, or raise InvalidTokenError."""
