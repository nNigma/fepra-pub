"""CLI первого запуска: выдать ссылку-приглашение прямо на сервере.

    PYTHONPATH=src python -m tj.services.auth_cli invite --role user [--existing-id N] [--admin]

Админа без Telegram не бывает, поэтому первую ссылку владелец получает здесь.
"""
from __future__ import annotations

import argparse
import sys

from tj.services import auth
from tj.services.urls import invite_url
from tjbot import db as botdb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="auth_cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("invite", help="создать приглашение")
    inv.add_argument("--role", default="user", choices=auth.INVITE_ROLES)
    inv.add_argument("--admin", action="store_true", help="сокращение для --role admin")
    inv.add_argument("--existing-id", type=int, default=None,
                     help="привязать к существующему user_id (старый Telegram-аккаунт)")
    inv.add_argument("--gym", default=None, help="зал (для роли coach)")
    inv.add_argument("--ttl-hours", type=float, default=72)
    inv.add_argument("--note", default="cli")
    a = ap.parse_args(argv)

    role = "admin" if a.admin else a.role
    con = botdb.connect(botdb.default_db_path())
    try:
        botdb.init_schema(con)
        try:
            token = auth.create_invite(con, None, role, a.gym, a.existing_id, a.ttl_hours, a.note)
        except ValueError as e:
            print(f"ошибка: {e}", file=sys.stderr)
            return 2
    finally:
        con.close()
    print(invite_url(token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
