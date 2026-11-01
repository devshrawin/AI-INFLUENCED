"""Command-line admin tasks (run inside the container).

python -m app.cli create-user <username> --role admin|officer
python -m app.cli reset-password <username>
python -m app.cli list-users
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth.passwords import hash_password, password_problem
from app.db.models import ROLES, User
from app.db.session import init_db, new_session


def _ask_password() -> str:
    while True:
        pw = getpass.getpass("New password: ")
        problem = password_problem(pw)
        if problem:
            print(problem)
        elif pw != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
        else:
            return pw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-user")
    p.add_argument("username")
    p.add_argument("--role", choices=ROLES, default="officer")
    p.add_argument("--name", default="")
    p = sub.add_parser("reset-password")
    p.add_argument("username")
    sub.add_parser("list-users")
    args = parser.parse_args(argv)

    init_db()
    with new_session() as db:
        if args.cmd == "list-users":
            for u in db.scalars(select(User).order_by(User.username)):
                print(
                    f"{u.username:20s} {u.role:8s} {'active' if u.is_active else 'disabled'}  {u.auth_source}"
                )
            return 0
        user = db.scalar(select(User).where(User.username == args.username))
        if args.cmd == "create-user":
            if user:
                print("User already exists.")
                return 1
            db.add(User(username=args.username, full_name=args.name, role=args.role,
                        password_hash=hash_password(_ask_password())))  # fmt: skip
        else:
            if not user:
                print("No such user.")
                return 1
            user.password_hash = hash_password(_ask_password())
            user.locked_until = None
            user.failed_logins = 0
        db.commit()
        print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
