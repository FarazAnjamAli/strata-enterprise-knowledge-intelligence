"""bcrypt password hashing (local auth)."""

import bcrypt

from app.config import get_settings

# bcrypt only looks at the first 72 bytes; reject longer input instead of
# silently truncating it
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    rounds = get_settings().password_hash_rounds
    return bcrypt.hashpw(password.encode()[:MAX_PASSWORD_BYTES], bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode()[:MAX_PASSWORD_BYTES], hashed.encode())
    except ValueError:
        return False


def password_problems(password: str) -> list[str]:
    s = get_settings()
    problems = []
    if len(password) < s.password_min_length:
        problems.append(f"at least {s.password_min_length} characters")
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        problems.append(f"at most {MAX_PASSWORD_BYTES} bytes")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("three of: lowercase, uppercase, digit, symbol")
    return problems


# constant-time-ish dummy check so unknown emails cost the same as wrong passwords
_DUMMY_HASH = bcrypt.hashpw(b"strata-dummy-password", bcrypt.gensalt(4)).decode()


def burn_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
