"""Operator CLI.

python -m app.cli create-user --email a@b.com --role Admin [--name ..] [--department ..]
python -m app.cli reset-password --email a@b.com
python -m app.cli reindex [--failed-only]
"""

import argparse
import getpass
import sys

from sqlalchemy import func, select

from app.auth.passwords import hash_password, password_problems
from app.auth.rbac import ALL_ROLES
from app.database.db import SessionLocal
from app.database.models import File, User


def _ask_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if problems := password_problems(pw):
            print("Password needs " + ", ".join(problems))
            continue
        if pw != getpass.getpass("Repeat:   "):
            print("Passwords don't match")
            continue
        return pw


def create_user(a: argparse.Namespace) -> int:
    if a.role not in ALL_ROLES:
        print(f"role must be one of: {', '.join(ALL_ROLES)}")
        return 2
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(func.lower(User.email) == a.email.lower())):
            print("user already exists")
            return 1
        pw = a.password or _ask_password()
        if problems := password_problems(pw):
            print("Password needs " + ", ".join(problems))
            return 2
        db.add(
            User(
                email=a.email.lower(),
                full_name=a.name,
                role=a.role,
                department=a.department,
                password_hash=hash_password(pw),
                is_active=True,
            )
        )
        db.commit()
    print(f"created {a.email} ({a.role})")
    return 0


def reset_password(a: argparse.Namespace) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == a.email.lower()))
        if user is None:
            print("no such user")
            return 1
        user.password_hash = hash_password(a.password or _ask_password())
        user.token_version = (user.token_version or 0) + 1
        db.commit()
    print("password updated")
    return 0


def reindex(a: argparse.Namespace) -> int:
    from app.workers.file_processor import process_file

    with SessionLocal() as db:
        stmt = select(File.id)
        if a.failed_only:
            stmt = stmt.where(File.index_status == "failed")
        ids = list(db.scalars(stmt))
    for fid in ids:
        process_file.delay(fid)
    print(f"queued {len(ids)} file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="strata")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("--email", required=True)
    c.add_argument("--role", default="Member")
    c.add_argument("--name")
    c.add_argument("--department")
    c.add_argument("--password", help="omit to be prompted")
    c.set_defaults(fn=create_user)
    r = sub.add_parser("reset-password")
    r.add_argument("--email", required=True)
    r.add_argument("--password")
    r.set_defaults(fn=reset_password)
    x = sub.add_parser("reindex")
    x.add_argument("--failed-only", action="store_true")
    x.set_defaults(fn=reindex)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
