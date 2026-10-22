from app.auth import tokens
from app.auth.provider import AuthProvider, Identity, InvalidTokenError


class LocalAuthProvider(AuthProvider):
    """Verifies access tokens Strata issued itself - no network, no third party."""

    name = "local"

    def verify_token(self, token: str) -> Identity:
        try:
            claims = tokens.decode(token, "access")
            return Identity(email=claims.get("email", ""), user_id=int(claims["sub"]))
        except (tokens.TokenError, ValueError) as exc:
            raise InvalidTokenError(str(exc)) from exc
