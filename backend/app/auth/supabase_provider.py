"""Supabase Auth as the identity provider (AUTH_PROVIDER=supabase).

Access tokens are verified locally against the project's JWKS (asymmetric
keys, cached) or the legacy shared secret (HS256). Password sign-in and
refresh are proxied through Strata so the frontend has one auth flow
regardless of provider.
"""

import httpx
import jwt
from jwt import PyJWKClient

from app.auth.provider import AuthProvider, Identity, InvalidTokenError
from app.config import get_settings


class SupabaseError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class SupabaseAuthProvider(AuthProvider):
    name = "supabase"

    def __init__(self, supabase_url: str, jwt_secret: str):
        self._url = supabase_url.rstrip("/")
        self._jwks = PyJWKClient(f"{self._url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)
        self._legacy_secret = jwt_secret

    def verify_token(self, token: str) -> Identity:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            key = self._legacy_secret if alg == "HS256" else self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
                leeway=60,
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc
        email = claims.get("email")
        if not email:
            raise InvalidTokenError("token has no email claim")
        return Identity(email=email, external_id=claims["sub"])

    # ---- token endpoints (proxied so the browser never talks to Supabase) ----

    def _token(self, grant: str, body: dict) -> dict:
        s = get_settings()
        try:
            r = httpx.post(
                f"{self._url}/auth/v1/token",
                params={"grant_type": grant},
                headers={"apikey": s.supabase_publishable_key},
                json=body,
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise SupabaseError(503, "Identity provider unreachable") from exc
        if r.status_code >= 400:
            raise SupabaseError(401, "Invalid credentials")
        return r.json()

    def password_login(self, email: str, password: str) -> dict:
        return self._token("password", {"email": email, "password": password})

    def refresh(self, refresh_token: str) -> dict:
        return self._token("refresh_token", {"refresh_token": refresh_token})
