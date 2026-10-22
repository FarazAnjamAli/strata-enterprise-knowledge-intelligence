import time

import pytest

from app.auth import tokens
from app.auth.local_provider import LocalAuthProvider
from app.auth.passwords import hash_password, password_problems, verify_password
from app.auth.provider import InvalidTokenError
from app.config import get_settings


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(get_settings(), "password_hash_rounds", 4)


def test_password_round_trip():
    h = hash_password("Correct-Horse-9")
    assert verify_password("Correct-Horse-9", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", None)


def test_password_policy():
    assert password_problems("short") != []
    assert password_problems("alllowercaseletters") != []
    assert password_problems("Strong-Passw0rd!") == []


def test_access_token_round_trip():
    tok = tokens.issue_access(7, "a@b.co")
    ident = LocalAuthProvider().verify_token(tok)
    assert ident.user_id == 7 and ident.email == "a@b.co"


def test_refresh_token_not_accepted_as_access():
    tok = tokens.issue_refresh(7, 0)
    with pytest.raises(InvalidTokenError):
        LocalAuthProvider().verify_token(tok)


def test_tampered_token_rejected():
    tok = tokens.issue_access(7, "a@b.co")
    with pytest.raises(InvalidTokenError):
        LocalAuthProvider().verify_token(tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb"))


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(get_settings(), "access_token_minutes", -5)
    tok = tokens.issue_access(7, "a@b.co")
    time.sleep(0.01)
    with pytest.raises(InvalidTokenError):
        LocalAuthProvider().verify_token(tok)


def test_refresh_carries_version():
    claims = tokens.decode(tokens.issue_refresh(3, 4), "refresh")
    assert claims["ver"] == 4 and claims["sub"] == "3"


def test_config_rejects_weak_jwt_secret(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "jwt_secret", "short")
    assert any("JWT_SECRET" in p for p in s.validate_runtime())
